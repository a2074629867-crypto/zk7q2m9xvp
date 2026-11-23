# -*- coding: utf-8 -*-
"""_refpick.py —— 从 _refs_new/meas.json 里按「角色 × 情绪档」挑参考音。

为什么不能只靠 emotion2vec 的 top-1
-----------------------------------
e2v 八类是**离散情绪**，而这套档位里有一半不是情绪：
  `loud`（抬高音量）、`wary`（警惕：低唤醒+紧张）、`defiant`（对抗：介于生气和顶撞）
e2v 会把 loud 判成 angry、把 wary 判成 neutral，按 top-1 挑必然挑错。
所以每档用「e2v 概率 + 相对声学量」的复合分：
  relF0 = 该段 F0 / 该角色档库 F0 中位      （音量/紧张度代理）
  relE  = 该段有声 RMS / 该角色档库 RMS 中位 （力度代理）
  rate  = 词数/秒（用 cue 文本词数估）

门槛（硬）：margin ≥ 0.16（留一法 77/77 的 p10）、MOS ≥ 2.2、有声 ≥0.55
排序：档内复合分，同分看 MOS。
"""
import collections
import json
import os
import sys

import numpy as np
import soundfile as sf

HERE = "G:/_setup"
OUT = os.path.join(HERE, "_refs_new")
MEAS = os.path.join(OUT, "meas.json")

# 每个目标档的复合分权重：e2v 标签 → 权重，声学量 → 权重
TIERS = {
    # 档名: (e2v 标签权重 dict, relF0 目标区间, relE 目标, 说明)
    "angry":    ({"生气/angry": 1.0}, (1.10, 2.0), 1.15, "生气：高 F0 + 高力度"),
    "excited":  ({"开心/happy": 1.0}, (1.10, 2.0), 1.10, "兴奋：高 F0 + 高力度 + happy"),
    "defiant":  ({"生气/angry": 0.7, "其他/other": 0.2}, (1.00, 1.6), 1.10, "对抗：中高 F0 + 顶撞口气"),
    "nervous":  ({"恐惧/fearful": 1.0}, (1.05, 1.8), 0.95, "紧张：F0 抬高但力度不大"),
    "wary":     ({"恐惧/fearful": 0.5, "中立/neutral": 0.3}, (0.90, 1.20), 0.90, "警惕：低唤醒、压低力度"),
    "loud":     ({"生气/angry": 0.4}, (1.20, 2.2), 1.30, "抬高音量：F0 和力度都高"),
    "begging":  ({"难过/sad": 1.0}, (0.85, 1.15), 0.90, "求饶：低力度 + sad"),
    "wronged":  ({"难过/sad": 0.8}, (0.85, 1.15), 0.95, "委屈：低力度 + sad"),
    "soft":     ({"难过/sad": 0.4, "中立/neutral": 0.3}, (0.75, 1.05), 0.85, "低声"),
    "calm":     ({"中立/neutral": 1.0}, (0.85, 1.10), 1.00, "平静"),
}

# 只补这几档（v18 的 ref_poor / ref_fallback 缺口）
WANT = [("Thomas", "loud"), ("Thomas", "wary"), ("Thomas", "defiant"),
        ("Thomas", "excited"), ("Thomas", "begging"),
        ("Charles", "nervous"), ("Charles", "angry"), ("Charles", "defiant"),
        ("Charles", "excited")]

MARGIN_MIN = 0.16
MOS_MIN = 2.2
VOICED_MIN = 0.55


def voiced_rms(p):
    y, sr = sf.read(p, dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    f = int(0.02 * sr)
    n = len(y) // f
    if not n:
        return -99.0
    db = np.array([20 * np.log10(np.sqrt(np.mean(y[j * f:(j + 1) * f] ** 2)) + 1e-12)
                   for j in range(n)])
    thr = max(db.max() - 30, -60)
    mask = np.repeat(db > thr, f)
    if len(mask) < len(y):
        mask = np.concatenate([mask, np.zeros(len(y) - len(mask), bool)])
    v = y[mask[:len(y)]]
    if not len(v):
        return -99.0
    return float(20 * np.log10(np.sqrt(np.mean(v ** 2)) + 1e-12))


def lib_stats():
    """该角色现有档库的 F0 / RMS 中位，作为 relF0 / relE 的分母。"""
    lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
    import parselmouth
    st = collections.defaultdict(lambda: {"f0": [], "e": []})
    for role, emos in lib.items():
        if role not in ("Thomas", "Charles"):
            continue
        for emo, items in emos.items():
            if emo == "begging" and role == "Thomas":
                continue      # 已知污染（F0 67~463），不能当分母
            for it in items:
                p = it["path"] if isinstance(it, dict) else it
                if not os.path.exists(p):
                    continue
                snd = parselmouth.Sound(p)
                pit = snd.to_pitch_ac(0.01, 60, 500).selected_array["frequency"]
                pit = pit[pit > 0]
                if len(pit):
                    st[role]["f0"].append(float(np.median(pit)))
                st[role]["e"].append(voiced_rms(p))
    return {r: {"f0": float(np.median(v["f0"])), "e": float(np.median(v["e"])),
                "n": len(v["f0"])} for r, v in st.items()}


def pick(want_tier, rows, st, topn=3):
    role, emo = want_tier
    w_e2v, f0_band, e_tgt, _ = TIERS[emo]
    base_f0 = st[role]["f0"]
    base_e = st[role]["e"]
    pool = [r for r in rows if r["role"] == role and r["margin"] >= MARGIN_MIN
            and (r["mos"] or 0) >= MOS_MIN and r["voiced"] >= VOICED_MIN]
    if not pool:
        return []
    scored = []
    for r in pool:
        relF0 = r["f0"] / base_f0 if base_f0 else 0
        relE = r["e_db"] - base_e          # 用 dB 差更稳（线性比值对 dB 不敏感）
        # 声学分：落在目标区间内给 1，越远线性衰减
        lo, hi = f0_band
        if lo <= relF0 <= hi:
            s_f0 = 1.0
        else:
            d = (lo - relF0) if relF0 < lo else (relF0 - hi)
            s_f0 = max(0.0, 1 - d / 0.35)
        s_e = max(0.0, 1 - abs(relE - (e_tgt - 1) * 8) / 8)   # e_tgt 是线性比，转成 dB 偏移
        s_emo = sum(w * r["eprob"] for lab, w in w_e2v.items() if r["e2v"] == lab)
        score = 0.42 * s_f0 + 0.28 * s_e + 0.30 * s_emo
        scored.append((round(score, 3), r, round(relF0, 2), round(relE, 1)))
    scored.sort(key=lambda x: (-x[0], -(x[1]["mos"] or 0)))
    return scored[:topn]


def main():
    rows = json.load(open(MEAS, encoding="utf-8"))
    for r in rows:
        r["e_db"] = round(voiced_rms(os.path.join(OUT, "cand", r["cid"] + ".wav")), 1)
    json.dump(rows, open(os.path.join(OUT, "meas2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    st = lib_stats()
    print("档库分母：", {k: {"F0": round(v["f0"]), "RMS": round(v["e"], 1), "n": v["n"]}
                       for k, v in st.items()})
    print()
    out = {}
    for t in WANT:
        picks = pick(t, rows, st)
        out["%s/%s" % t] = [{"cid": p[1]["cid"], "score": p[0], "relF0": p[2], "relE": p[3],
                             "f0": p[1]["f0"], "mos": p[1]["mos"], "margin": p[1]["margin"],
                             "e2v": p[1]["e2v"], "eprob": p[1]["eprob"],
                             "dur": p[1]["dur"], "text": p[1]["text"]} for p in picks]
        print("== %s/%s  (%s)" % (t[0], t[1], TIERS[t[1]][3]))
        if not picks:
            print("   ⚠ 无合格候选（角色池=%d）" %
                  len([r for r in rows if r["role"] == t[0]]))
            continue
        for p in picks:
            r = p[1]
            print("   %-11s score %.2f | relF0 %.2f relE %+.1fdB | F0 %3.0f | MOS %.2f | "
                  "margin %.2f | %s %.2f | %.1fs | %s"
                  % (r["cid"], p[0], p[2], p[3], r["f0"], r["mos"] or 0, r["margin"],
                     (r["e2v"] or "-")[:6], r["eprob"], r["dur"], r["text"][:38]))
        print()
    json.dump(out, open(os.path.join(OUT, "picks.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
