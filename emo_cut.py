# -*- coding: utf-8 -*-
"""emo_cut.py —— 一条命令从视频里自动切出「某角色某情绪」的参考音色候选。

为什么要它
----------
之前这套是散的：`cut_cues.py` 切条、`find_soft.py` 只给 Charles/soft 找补、
`check_cand.py` 做硬检查、`dialog_gate.py` 判角色，**中间靠人看 json 串**。
换个角色、换个情绪就得改脚本（`find_soft` 里 Charles/soft 是写死的）。

这里把四段串成一条：切条 → 判角色 → 五类情绪打分 → 硬检查 → 出候选表。

为什么不自动入库（这是刻意的，不是没做完）
------------------------------------------
纯指标筛会把两种垃圾排在最前面，两条都有实测反例：
  ① **静音刷分**：`1−A` 和 RMS 强相关，静音多 → 能量低 → 委屁值虚高。
     本片前 5 名候选静音占 65–91%（c262 3.41s 只有 0.32s 有声，1−A=0.910）。
  ② **说话人错**：指标最高的 c106（1−A=0.522）经上下文查证是 Thomas 说的。
     「Il va t'arriver quelque chose, **Charles**.」也不是 Charles 说的。
一条指标高的音频，可能既不是这个人、也不是完整一句话。
所以本脚本产出**带证据的候选表 + 两档标签**，最后一米留给人眼：
  [入库]  指标过 P25 + 硬检查全过 + 角色差 ≥ 0.4
  [人耳]  其余（指标过线但证据不足）

用法
----
  # 整片扫（先建好声纹库）
  python emo_cut.py --video film.mkv --srt film.srt --out work/emo --top 5

  # 只切情绪、不分角色（没有声纹库时；素材标注为 role="?"）
  python emo_cut.py --video film.mkv --srt film.srt --out work/emo --no-role

  # 已经切好条了，直接从 cues.json 起跑
  python emo_cut.py --cues work/emo/cues.json --out work/emo --e2v

  # 只要某一类
  python emo_cut.py --video film.mkv --srt film.srt --out work/emo --emotion 委屈

产出
----
  <out>/cues/           音频 + cues.json（cut_cues 的产物）
  <out>/candidates.json 全量 + 证据（时长/静音/语速/角色 z/情绪值/分位/标签）
  终端表格              role × emotion 的 top N

环境：**G:/Python310**（唯一同时有 onnxruntime + torch + parselmouth）
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.join(HERE, "emo_bench"), "G:/voice_lib"):
    sys.path.insert(0, p)

from cut_cues import parse_srt, merge_fragments, cut as cut_one, FF
from check_cand import analyze as hards
import verdict as V

REF_STATS = os.path.join(HERE, "emo_bench", "out", "ref_stats.json")

# 硬检查红线（都是踩过坑定下来的，见 check_cand.py 抬头）
SIL_MAX = 0.35          # 静音占比上限
LONG_SIL_MAX = 1.0      # 最长连续静音（秒）
WPM_MIN, WPM_MAX = 1.5, 4.5   # 词/有声秒
ROLE_GAP_OK = 0.4       # 角色差 ≥ 0.4 才认（与 dialog_gate 同一口径）


def load_stats():
    return json.load(open(REF_STATS, encoding="utf-8"))


def emo_values(sc):
    """一条 wav 的 VAD → 五个判据值（与 verdict.PRIMARY 对齐）。"""
    return {
        "兴奋": V.vox_feat(sc, "a_x_v"),
        "激动反抗": V.vox_feat(sc, "d"),
        "委屈": V.vox_feat(sc, "neg_a"),
        "紧张": V.vox_feat(sc, "a_x_nd"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video")
    ap.add_argument("--srt")
    ap.add_argument("--cues", help="已有 cues.json 就用它，跳过切条")
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=5, help="每角色每情绪报几条")
    ap.add_argument("--min-dur", type=float, default=1.5)
    ap.add_argument("--max-dur", type=float, default=10.0)
    ap.add_argument("--emotion", help="只处理这一类")
    ap.add_argument("--no-role", action="store_true", help="不判角色（没有声纹库时）")
    ap.add_argument("--e2v", action="store_true", help="额外跑 emotion2vec（警惕判据需要，慢）")
    ap.add_argument("--merge-frag", action="store_true")
    ap.add_argument("--lib", default="G:/_setup/_emo_refs.json")
    ap.add_argument("--bg", default="G:/_setup/out_sv/cues_znorm2.json")
    ap.add_argument("--ffmpeg", default=FF)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    stats = load_stats()
    emos = [a.emotion] if a.emotion else list(V.PRIMARY)
    if "警惕" in emos and not a.e2v:
        print("⚠ 警惕 的判据是 emotion2vec disgusted，没给 --e2v 就跳过这一类")
        emos = [e for e in emos if e != "警惕"]

    # ① 切条
    cues_path = a.cues or os.path.join(a.out, "cues", "cues.json")
    if not a.cues:
        if not (a.video and a.srt):
            sys.exit("给 --video + --srt，或 --cues")
        cues = parse_srt(a.srt)
        if a.merge_frag:
            cues = merge_fragments(cues, max_dur=a.max_dur)
        cdir = os.path.join(a.out, "cues")
        os.makedirs(cdir, exist_ok=True)
        keep, skip = [], []
        for c in cues:
            if not (a.min_dur <= c["dur"] <= a.max_dur):
                continue
            if c.get("sfx") or c.get("multi"):
                skip.append(c)
                continue
            dst = os.path.join(cdir, "c%03d_%06.1f_%06.1f.wav" % (c["i"], c["t0"], c["t1"]))
            if cut_one(a.video, c["t0"], c["t1"], dst, 0.12, 0.20, ffmpeg=a.ffmpeg):
                c = dict(c)
                c["path"] = dst
                keep.append(c)
        json.dump(keep, open(cues_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("切出 %d 条 → %s（跳过 sfx/多人 %d 条）" % (len(keep), cdir, len(skip)))
    else:
        keep = [c for c in json.load(open(cues_path, encoding="utf-8"))
                if not (c.get("sfx") or c.get("multi"))]
        print("读入 %d 条 cue" % len(keep))

    # ② 角色
    ev = None
    if not a.no_role:
        from chain_check import EmoVoice
        ev = EmoVoice(lib=a.lib, bg=a.bg)
        print("声纹模板 %d 条（1-NN + Z-norm，soft 只做情绪参考）" % len(ev.keys))

    # ③ 逐条打分
    import ser as S
    vox = S.VoxDim()
    e2v = None
    if "警惕" in emos:
        e2v = S.E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large")

    rows = []
    for i, c in enumerate(keep):
        p, text = c["path"], (c.get("text") or "").strip()
        h = hards(p)
        if not h:
            continue
        sc = vox.score(p) or {}
        vals = emo_values(sc)
        if e2v is not None:
            s2 = e2v.score(p) or {}
            vals["警惕"] = float(s2.get("厌恶/disgusted", 0.0))

        role, gap, z1 = "?", None, None
        if ev is not None:
            r = ev.check(p, role_blind=("soft",))
            zr = r.get("z_role") or r["z_all"]
            zm = {}
            for k, v in zr.items():
                zm.setdefault(k.split("/")[0], []).append(v)
            mx = {k: max(v) for k, v in zm.items()}
            role = r["role"]
            z1 = r["z1"]
            others = [v for k, v in mx.items() if k != role]
            gap = round(mx[role] - (max(others) if others else 0.0), 2)

        words = len([w for w in text.split() if w])
        wpm = round(words / h["voiced"], 2) if h["voiced"] > 0.3 and words else None
        bad = []
        if h["sil_ratio"] > SIL_MAX:
            bad.append("静音%.0f%%" % (h["sil_ratio"] * 100))
        if h["longest_sil"] > LONG_SIL_MAX:
            bad.append("连续静音%.1fs" % h["longest_sil"])
        if h["head_db"] < -45:
            bad.append("首端切偏")
        if wpm is not None and not (WPM_MIN <= wpm <= WPM_MAX):
            bad.append("语速%.1f词/秒" % wpm)
        if gap is not None and gap < ROLE_GAP_OK:
            bad.append("角色差%+.2f" % gap)

        rows.append({"id": "c%03d" % c["i"], "path": p, "text": text[:70],
                     "role": role, "gap": gap, "z1": z1,
                     "dur": h["dur"], "sil": h["sil_ratio"],
                     "long_sil": h["longest_sil"], "wpm": wpm,
                     "vals": {k: round(float(v), 4) for k, v in vals.items()},
                     "bad": bad})
        if (i + 1) % 20 == 0:
            print("  %d/%d" % (i + 1, len(keep)), flush=True)

    # ④ 排序 + 两档
    table = {}
    for emo in emos:
        src, key = V.PRIMARY[emo]
        st = stats[emo]["signals"]["%s:%s" % (src, key)]
        p25, p10 = st["pos"]["p25"], st["pos"]["p10"]
        for r in rows:
            v = r["vals"].get(emo)
            if v is None:
                continue
            r.setdefault("emo", {})[emo] = {
                "value": round(float(v), 4), "p25": p25, "p10": p10,
                "tier": "到位" if v >= p25 else ("勉强" if v >= p10 else "未达"),
                "ok": (not r["bad"]) and v >= p25,
            }
        cand = [r for r in rows if r.get("emo", {}).get(emo, {}).get("tier") != "未达"]
        cand.sort(key=lambda r: -r["emo"][emo]["value"])
        for role in sorted({r["role"] for r in cand}):
            table[(role, emo)] = [r for r in cand if r["role"] == role][:a.top]

    # ⑤ 输出
    json.dump(rows, open(os.path.join(a.out, "candidates.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    n_ok = sum(1 for r in rows if any(e.get("ok") for e in r.get("emo", {}).values()))
    print("\n=== 候选（%d 条 cue 中，可直接入库 %d 条 / 全量见 candidates.json）===" % (len(rows), n_ok))
    for (role, emo), lst in sorted(table.items()):
        if not lst:
            continue
        print("\n[%s] %s  (P25=%.3f)" % (
            role, emo, stats[emo]["signals"]["%s:%s" % V.PRIMARY[emo]]["pos"]["p25"]))
        print("  %-6s %6s %6s %6s %7s %s" % ("id", "值", "档", "角色差", "时长", "标签 / 问题"))
        for r in lst:
            e = r["emo"][emo]
            print("  %-6s %6.3f %6s %6s %6.2fs %s" % (
                r["id"], e["value"], e["tier"],
                "%+.2f" % r["gap"] if r["gap"] is not None else "-",
                r["dur"],
                "[入库]" if e["ok"] else "[人耳] " + ("; ".join(r["bad"]) or "-")))

    print("\n两档口径：[入库] = 指标过 P25 + 硬检查全过 + 角色差 ≥ %.1f；"
          "其余 [人耳]。\n"
          "不自动入库的原因见脚本抬头（静音刷分 / 说话人错）。" % ROLE_GAP_OK)


if __name__ == "__main__":
    main()
