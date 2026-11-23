# -*- coding: utf-8 -*-
"""_spk_margin.py —— 用「同批对照归一化」替代裸余弦阈值。

为什么必须换：`_spk_calib.py` 实测同一人不同句子的裸余弦中位只有 0.536、最低 −0.139，
同一句前半 vs 后半最低 0.346。裸余弦在 7 秒级短句上的噪声底 ≈ ±0.5，
用它当 0.55 的及格线等于随机淘汰。

改法（说话人验证里的 T-norm / cohort score normalization）：
    s_same   候选 take 与「它自己那一句交付版」的余弦   —— 同文本同人
    cohort   候选 take 与「其它 N 句交付版」的余弦中位   —— 同人不同文本
    margin   s_same − cohort
    z        (s_same − mean(cohort)) / sd(cohort)
同一个人：同文本的相似度必须**显著高于**不同文本 ⇒ margin 明显为正、z 很大。
真换了人：两者一起掉到同一水平 ⇒ margin ≈ 0、z ≈ 0。
这样阈值就和「绝对音色」解耦了，只比较相对关系。
"""
import glob
import json
import os
import statistics as S
import sys

sys.path.insert(0, "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab")
import spk_embed as SP

ROOT = "G:/_setup"
N_COHORT = 14

# 本轮全部候选：8 条 WATCH × 各 seed
CAND = {
    "N0219": ["2031", "2033", "2035"],
    "N0301": ["2031"],
    "N0480": ["2031"],
    "N0602": ["2031"],
    "N0627": ["2031", "2033", "2035"],
    "N0634": ["2031", "2033", "2035"],
    "N0666": ["2031"],
    "N0824": ["2031", "2033"],
}
# 上一批（s2025/2027/2029）里的几个争议 take
OLD = [("N0347", "2025"), ("N0542", "2025"), ("N0627", "2027"), ("N0627", "2025"),
       ("N0419", "2025"), ("N0829", "2029")]


def main():
    st = json.load(open(os.path.join(ROOT, "_mt_adv_state.json"), encoding="utf-8"))["units"]
    pool = {}
    for u in sorted(st):
        p = os.path.join(ROOT, "_mt_pick", u + ".wav")
        if os.path.exists(p):
            pool[u] = p
    print("交付池 %d 条" % len(pool))

    emb, cache = {}, {}

    def E(p):
        if p not in cache:
            cache[p] = SP.embed(p)
        return cache[p]

    for u, p in pool.items():
        try:
            emb[u] = E(p)
        except Exception:
            pass

    other_units = sorted(emb)
    rows = []

    def score(uid, wav):
        if uid not in emb:
            return None
        x = E(wav)
        s_same = SP.cos(emb[uid], x)
        # cohort：固定取「按 uid 排序、跳过自己、均匀抽样」，保证可复现
        idx = [(i * 7) % len(other_units) for i in range(len(other_units) * 2)]
        cohort = []
        for i in idx:
            v = other_units[i]
            if v == uid or len(cohort) >= N_COHORT:
                continue
            cohort.append(SP.cos(emb[v], x))
        if len(cohort) < 5:
            return None
        med = S.median(cohort)
        mean = sum(cohort) / len(cohort)
        sd = S.pstdev(cohort) or 1e-6
        return dict(s_same=s_same, cohort=med, margin=s_same - med,
                    z=(s_same - mean) / sd)

    for uid, seeds in CAND.items():
        for sd in seeds:
            w = os.path.join(ROOT, "_mt_adv_s%s" % sd, uid + ".wav")
            if not os.path.exists(w):
                continue
            r = score(uid, w)
            if r:
                r.update(uid=uid, seed=sd, batch="本轮")
                rows.append(r)
    for uid, sd in OLD:
        w = os.path.join(ROOT, "_mt_adv_s%s" % sd, uid + ".wav")
        if not os.path.exists(w):
            continue
        r = score(uid, w)
        if r:
            r.update(uid=uid, seed=sd, batch="上批")
            rows.append(r)

    rows.sort(key=lambda r: r["margin"])
    print("\n%-7s %-6s %-6s %-8s %-8s %-8s %s"
          % ("uid", "seed", "批次", "裸余弦", "cohort", "margin", "z"))
    for r in rows:
        flag = "  ← 换人?" if r["margin"] < 0.05 else ""
        print("%-7s %-6s %-6s %-8.3f %-8.3f %+8.3f %+8.1f%s"
              % (r["uid"], r["seed"], r["batch"], r["s_same"], r["cohort"],
                 r["margin"], r["z"], flag))

    ms = [r["margin"] for r in rows]
    print("\nmargin 分布：n=%d 中位 %+.3f 最低 %+.3f  为负的 %d 个"
          % (len(ms), S.median(ms), min(ms), sum(1 for m in ms if m < 0)))
    json.dump(rows, open(os.path.join(ROOT, "_spk_margin.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("写出 _spk_margin.json")


if __name__ == "__main__":
    main()
