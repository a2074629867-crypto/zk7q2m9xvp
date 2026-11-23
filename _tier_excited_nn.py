# -*- coding: utf-8 -*-
"""Thomas excited 激烈档：在 Thomas 自己的 28 条参考里挑「情绪空间最近 + 强度更高」的一条。

为什么不是「补切」：用户明确要求「找个最相近的」。
Thomas 的参考池是 9 种情绪 28 条，excited 只有 1 条（arousal 0.76）。
激烈档要的不是「再切一条 excited」，而是**同一角色、最接近 excited 的那个更高唤醒状态**。
所以按 vox 情绪向量（valence/dominance/arousal）算距离，只在 arousal 更高的条目里取最近邻。

用法：python _tier_excited_nn.py [--write]
"""
import json
import os
import sys

import numpy as np

HERE = "G:/_setup"
LIB = os.path.join(HERE, "_emo_refs_all.json")
TIER = os.path.join(HERE, "_ref_tier2.json")
OUT = os.path.join(HERE, "_tier_excited_nn.json")
ROLE, EMO = "Thomas", "excited"

sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "emo_bench"))


def vec(p):
    """归一到 voiced RMS −24dBFS 后取 vox 情绪向量（与 _tier_split.py 同口径）。"""
    import mt_seg_drift as D
    import soundfile as sf
    import ser as S

    a, sr = D.read_wav(p)
    Sr = D.series(a, sr)
    arr = np.asarray(Sr.get("rms") if Sr.get("rms") is not None else [], dtype=float)
    arr = arr[np.isfinite(arr)]
    rms = None
    if len(arr):
        thr = float(np.percentile(arr, 25))
        vr = arr[arr > thr]
        rms = float(np.median(vr if len(vr) else arr))

    tmp_dir = os.path.join(HERE, "_tier_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    y = a.astype(np.float32)
    if rms is not None:
        y = y * (10 ** ((-24.0 - rms) / 20.0))
    tmp = os.path.join(tmp_dir, "nn_" + os.path.basename(p))
    sf.write(tmp, np.clip(y, -1.0, 1.0), sr, subtype="PCM_16")
    sc = S.VoxDim().score(tmp) or {}
    # 清掉临时文件，别在盘上堆
    try:
        os.remove(tmp)
    except OSError:
        pass
    return {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in sc.items()}


def main():
    write = "--write" in sys.argv
    if "--from-cache" in sys.argv:
        # 特征算一次要 4 分钟（WavLM-large 首次加载 + 28 条前向），改选规则的调参没必要重算
        d = json.load(open(OUT, encoding="utf-8"))
        rows = d["ranked"]
        b_aro = next((x["arousal"] - x["d_aro"] for x in rows), None)
        cand = [x for x in rows if x["d_aro"] >= 0.08] or rows[:1]
        pick = min(cand, key=lambda x: x["dist"])
        print("从缓存重选：%s (%s) d=%.4f Δaro=%+.4f" %
              (pick["name"], pick["emo"], pick["dist"], pick["d_aro"]))
        return _write_back(pick, b_aro, write)

    lib = json.load(open(LIB, encoding="utf-8"))
    refs = []
    for e, arr in lib[ROLE].items():
        for x in arr:
            nm = x.get("name") or os.path.basename(x["path"])[:-4]
            refs.append(dict(name=nm, emo=e, path=x["path"],
                             text=(x.get("text") or "")[:80]))
    print("Thomas 参考 %d 条" % len(refs), flush=True)

    for r in refs:
        if not os.path.exists(r["path"]):
            r["err"] = "missing"
            continue
        try:
            r["v"] = vec(r["path"])
        except Exception as exc:  # noqa: BLE001
            r["err"] = str(exc)[:80]
        print("  %-22s %-9s %s" % (r["name"], r["emo"],
                                   "ERR " + r.get("err", "") if r.get("err")
                                   else "aro=%.4f val=%.4f dom=%.4f" % (
                                       r["v"].get("arousal") or -9,
                                       r["v"].get("valence") or -9,
                                       r["v"].get("dominance") or -9)), flush=True)

    ok = [r for r in refs if r.get("v") and r["v"].get("arousal") is not None]
    base = [r for r in ok if r["name"] == "Thomas_excited_1"]
    if not base:
        print("!! 找不到基准 Thomas_excited_1")
        return 1
    b = base[0]["v"]
    print("\n基准 %s: aro=%.4f val=%.4f dom=%.4f" %
          ("Thomas_excited_1", b["arousal"], b.get("valence") or 0, b.get("dominance") or 0))

    rows = []
    for r in ok:
        if r["name"] == "Thomas_excited_1":
            continue
        v = r["v"]
        if (v.get("arousal") or 0) <= b["arousal"]:
            continue
        d = float(np.hypot((v.get("valence") or 0) - (b.get("valence") or 0),
                           (v.get("dominance") or 0) - (b.get("dominance") or 0)))
        rows.append(dict(name=r["name"], emo=r["emo"], path=r["path"], text=r["text"],
                         arousal=v["arousal"], valence=v.get("valence"),
                         dominance=v.get("dominance"), dist=round(d, 4),
                         d_aro=round(v["arousal"] - b["arousal"], 4)))
    rows.sort(key=lambda x: x["dist"])
    print("\n== arousal 更高的候选，按情绪空间距离排序 ==")
    for x in rows:
        print("  %-22s %-9s d(val,dom)=%.4f  aro %.3f (%+.3f)  %s" %
              (x["name"], x["emo"], x["dist"], x["arousal"], x["d_aro"], x["text"][:40]))

    if not rows:
        print("!! 没有 arousal 更高的 Thomas 参考")
        return 1

    # ★ 先过「强度差门槛」再取最近，不是先取最近再看强度（2026-11-15 12:2x 修）
    #   第一版按「d>=0.15 且 Δaro>=0.15」顺延，结果一个都不满足 ⇒ 退回 rows[0]，
    #   选中的是 loud d=0.074 但 Δaro 只有 +0.013 —— 强度几乎没差，等于没分档。
    #   实测 Thomas 池子的上限就在这：最激动的一条 arousal 0.857，只比 excited_1 高 0.097。
    #   ⇒ 门槛按「面板里已接受的最弱档」定：Charles wronged +0.05 / Fielding excited +0.10 都算两档，
    #     所以取 Δaro >= 0.08（arousal 单位）为下限，再在同门槛内取情绪空间最近的。
    MIN_D_ARO = 0.08
    cand = [x for x in rows if x["d_aro"] >= MIN_D_ARO]
    if not cand:
        cand = rows[:1]
        print("!! Thomas 池子里没有 Δaro>=%.2f 的候选，退回最近邻（强度差不足，只能当代理）" % MIN_D_ARO)
    pick = min(cand, key=lambda x: x["dist"])
    print("\n选定 intense = %s (%s)  d=%.4f  Δaro=%+.4f  aro=%.4f（门槛 Δaro>=%.2f 内最近）" %
          (pick["name"], pick["emo"], pick["dist"], pick["d_aro"], pick["arousal"], MIN_D_ARO))

    out = dict(role=ROLE, emo=EMO, base="Thomas_excited_1",
               pick=pick, ranked=rows[:8],
               rule="arousal 更高 + (valence,dominance) 欧氏距离最小；"
                    "若最近邻 d<0.15 且 Δaro<0.15 则顺延（听不出强度差等于没分档）")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s" % OUT)
    return _write_back(pick, b["arousal"], write)


def _write_back(pick, b_aro, write):
    print("待写回：intense = %s（%s），bench arousal %.4f" % (pick["name"], pick["emo"], b_aro))
    if not write:
        print("（未加 --write，只预览）")
        return 0
    t = json.load(open(TIER, encoding="utf-8"))
    node = t[ROLE][EMO]
    node["intense"] = dict(path=pick["path"], name=pick["name"],
                           arousal=pick["arousal"], src_emo=pick["emo"],
                           text=pick["text"], note="最近邻代理档（非原生 excited）")
    node["note"] = ("excited 只有 1 条原生参考；激烈档用 Thomas 自身 %s 的 %s 代理，"
                    "情绪空间距离 %.3f、唤醒度 %+.3f（arousal %.3f vs %.3f）"
                    % (pick["emo"], pick["name"], pick["dist"], pick["d_aro"],
                       pick["arousal"], b_aro))
    json.dump(t, open(TIER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已写回 %s" % TIER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
