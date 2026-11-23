# -*- coding: utf-8 -*-
"""_scs_calib.py —— 标定「档内一致性」判据：同 voice 档内部，某条与同档其他条的余弦。

思路：SCS 的 z-score 判据在本语料上不成立（Joseph 核心簇 σ=0.017 ⇒ z 爆到 29σ，
但 top-1 归属仍是 Joseph，不是换人）。改用**档内相对一致性**：
同一档同一参考生成的句子，彼此应当比「同角色不同档」更像我（r34 intra p50 0.346）。
"""
import json, sys
import numpy as np

sys.path.insert(0, "G:/_setup")
AUD = "G:/_setup/_audio_ch123/out"


def main():
    plan = {}
    for l in open("G:/_setup/_dlg_plan_v2.jsonl", encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l); plan[o["id"]] = o
    import soundfile as sf
    dur = {}
    for k in plan:
        try:
            dur[k] = sf.info("%s/%s.wav" % (AUD, k)).duration
        except Exception:
            dur[k] = 0.0
    for model in ("r34", "eres2net"):
        z = np.load("G:/_setup/_utt_emb/%s.npz" % model)
        ids, whos, E = list(z["ids"]), list(z["whos"]), z["embs"]
        print("=" * 74)
        print("模型", model)
        groups = {}
        for i, k in enumerate(ids):
            groups.setdefault(plan[k]["voice"], []).append(i)
        rows = []
        for v, idxs in groups.items():
            if len(idxs) < 3:
                continue
            S = E[idxs]
            C = S @ S.T
            for a, i in enumerate(idxs):
                oth = np.delete(C[a], a)
                rows.append((float(np.median(oth)), float(np.min(oth)), ids[i],
                             v, plan[ids[i]]["who"], dur["%s" % ids[i]], len(idxs)))
        rows.sort()
        print("档内中位 cos 分布（仅 ≥3 句的档，n=%d）：" % len(rows))
        v = [r[0] for r in rows]
        print("   p1 %.3f p5 %.3f p10 %.3f p25 %.3f p50 %.3f"
              % tuple(np.percentile(v, [1, 5, 10, 25, 50])))
        print("   ≥2.0s 的条：p5 %.3f p10 %.3f p50 %.3f（n=%d）"
              % (*np.percentile([r[0] for r in rows if r[5] >= 2.0], [5, 10, 50]),
                 len([r for r in rows if r[5] >= 2.0])))
        print("   最低 15 条：" )
        for m, mn, k, vo, who, d, n in rows[:15]:
            print("     %-8s %-22s %-8s %5.2fs 档内中位 %.3f min %.3f (档 n=%d)"
                  % (k, vo, who, d, m, mn, n))
        # 档级汇总
        print("   档级中位（哪些档整体散）：")
        byv = {}
        for m, mn, k, vo, who, d, n in rows:
            byv.setdefault(vo, []).append(m)
        for vo, ms in sorted(byv.items(), key=lambda x: np.median(x[1])):
            print("     %-22s 中位 %.3f  n=%d" % (vo, np.median(ms), len(ms)))


if __name__ == "__main__":
    main()
