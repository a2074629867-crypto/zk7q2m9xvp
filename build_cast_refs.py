# -*- coding: utf-8 -*-
"""build_cast_refs.py —— 从 emo_cut 的候选表里挑条，建「角色 × 情绪档」参考库。

为什么不直接取每个情绪 top1
--------------------------
emo_cut 的抬头已经写了两种反例：静音刷分、说话人错。这里再加两条实测：
  - 同一段音频在多个情绪里都排前面（判据互相相关），全取 top1 会拿到重复素材；
  - 只看指标会选到长句里的半句（首端切偏 / 尾端被切），当参考音就是坏模板。
所以逐档挑条要过四道：硬检查全过 → 未在其它档用过 → 时长 2.0–9.0s → 档内不重复。

留一法（LOO）给的是**跨角色版**：拿掉这条，用同角色其它条算组内最高余弦，
再跟「别的角色的参考库」比。只有组内 > 跨角色才算这条有辨识度。
"""
import argparse
import collections
import json
import os
import shutil
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")


def f0_stats(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=450)
    f = pit.selected_array["frequency"]
    f = f[f > 0]
    if not len(f):
        return 0.0, 0.0
    return float(np.median(f)), float(np.std(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", required=True)
    ap.add_argument("--role", required=True)
    ap.add_argument("--src", default="")
    ap.add_argument("--refdir", default="G:/_setup/refs_cast")
    ap.add_argument("--out", required=True)
    ap.add_argument("--slots", default="excited:兴奋,defiant:激动反抗,wronged:委屈,wary:警惕,nervous:紧张")
    ap.add_argument("--per-slot", type=int, default=2)
    ap.add_argument("--max-sil", type=float, default=0.35)
    ap.add_argument("--max-long-sil", type=float, default=1.0)
    ap.add_argument("--min-dur", type=float, default=2.0)
    ap.add_argument("--max-dur", type=float, default=9.0)
    ap.add_argument("--other", nargs="*", default=[])
    a = ap.parse_args()

    cand = json.load(open(a.cand, encoding="utf-8"))
    slots = collections.OrderedDict()
    for s in a.slots.split(","):
        k, cn = s.split(":")
        slots[k] = cn

    from chain_check import EmoVoice
    m = EmoVoice().m

    used = set()
    lib = collections.defaultdict(dict)
    for slot, cn in slots.items():
        pool = [c for c in cand if cn in (c.get("vals") or {})]
        pool.sort(key=lambda c: -(c["vals"][cn] or 0))
        take = []
        for c in pool:
            if len(take) >= a.per_slot:
                break
            if c["id"] in used:
                continue
            if c["sil"] > a.max_sil or c["long_sil"] > a.max_long_sil:
                continue
            if not (a.min_dur <= c["dur"] <= a.max_dur):
                continue
            # 不再看 `bad` 列表：那张表用的是 emo_cut 的旧阈值（静音 0.35），对「单句
            # 自然停顿」太严——正常一句话有 40–55% 静音是常态。这里只按上面的参数判。
            take.append(c)
        if not take:
            print("!! %-8s 没有过硬的候选" % cn)
            continue
        os.makedirs(a.refdir, exist_ok=True)
        items = []
        for c in take:
            dst = os.path.join(a.refdir, "%s_%s_%s.wav" % (a.role, slot, c["id"]))
            shutil.copy2(c["path"], dst)
            f0, sd = f0_stats(dst)
            # emo_cut 的 candidates.json 不带 t0，从文件名 c045_00513.5_00518.6.wav 里取
            t0 = c.get("t0")
            if t0 is None:
                try:
                    t0 = float(os.path.basename(c["path"]).split("_")[1])
                except (IndexError, ValueError):
                    t0 = 0.0
            items.append({"path": dst.replace("\\", "/"), "t0": round(float(t0), 2), "dur": c["dur"],
                          "f0": round(f0, 1), "f0_sd": round(sd, 1),
                          "emo_val": round(float(c["vals"][cn]), 3),
                          "src": a.src, "id": c["id"], "text": c["text"]})
            used.add(c["id"])
        lib[a.role][slot] = items
        print("%-8s(%-8s) %d 条：%s" % (
            a.role, slot, len(items),
            " | ".join("%s %.2f %.1fs %s" % (it["id"], it["emo_val"], it["dur"], it["text"][:44])
                       for it in items)))

    keys, E = [], []
    for role, sl in lib.items():
        for slot, items in sl.items():
            for it in items:
                keys.append((role, slot, it["id"]))
                E.append(m.embed(it["path"]))
    if not keys:
        raise SystemExit("一条都没选上")
    E = np.array(E, dtype=np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9

    for i, (role, slot, cid) in enumerate(keys):
        same = [j for j, k in enumerate(keys) if k[0] == role and j != i]
        if same:
            v = float(np.mean([float(E[i] @ E[j]) for j in same]))
            for it in lib[role][slot]:
                if it["id"] == cid:
                    it["pure"] = round(v, 3)

    other_E = []
    for p in a.other:
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        for role, sl in d.items():
            for slot, items in sl.items():
                for it in items:
                    if os.path.exists(it["path"]):
                        e = m.embed(it["path"])
                        other_E.append(e / (np.linalg.norm(e) + 1e-9))
    print("\n留一法（组内 vs 跨角色）：")
    ok = n = 0
    for i, (role, slot, cid) in enumerate(keys):
        same = [j for j, k in enumerate(keys) if k[0] == role and j != i]
        bs = max(float(E[i] @ E[j]) for j in same) if same else 0.0
        bo = max(float(E[i] @ e) for e in other_E) if other_E else 0.0
        good = (bs > bo) if other_E else True
        ok += good
        n += 1
        print("  %-8s %-9s %-6s 组内 %.3f | 跨角色 %.3f %s" % (
            role, slot, cid, bs, bo, "OK" if good else "✗"))

    json.dump(lib, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s（%d 档 %d 条）  留一法 %d/%d" % (
        a.out, sum(len(v) for v in lib.values()), len(keys), ok, n))


if __name__ == "__main__":
    main()
