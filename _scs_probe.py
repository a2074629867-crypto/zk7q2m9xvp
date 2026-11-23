# -*- coding: utf-8 -*-
"""_scs_probe.py —— 在 239 条对白上算角色级 SCS，看 z 分布与离群条目。

口径照 ch123_scs.py（SceneTTS-Bench §3.3）：角色内稳健中心（迭代剔除 10%）+
z-score 惩罚，但声纹模型换成本轮实测更可靠的 r34 / eres2net（CAM++ EER 44.6%，r34 23.2%）。
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/_setup")


def load(model):
    z = np.load("G:/_setup/_utt_emb/%s.npz" % model)
    return list(z["ids"]), list(z["whos"]), z["embs"]


def nrm(v):
    return v / (np.linalg.norm(v) + 1e-9)


def robust_centroid(E, drop=0.10, iters=8, floor=0.6):
    idx = np.ones(len(E), dtype=bool)
    for _ in range(iters):
        C = nrm(E[idx].mean(0))
        s = E @ C
        if idx.sum() <= max(3, int(len(E) * floor)):
            break
        thr = np.quantile(s[idx], drop)
        new = idx & (s >= thr)
        if new.sum() == idx.sum():
            break
        idx = new
    return nrm(E[idx].mean(0)), idx


def main():
    plan = {}
    for l in open("G:/_setup/_dlg_plan_v2.jsonl", encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l); plan[o["id"]] = o
    for model in ("r34", "eres2net"):
        ids, whos, E = load(model)
        print("=" * 70)
        print("模型", model, "n=", len(ids))
        cen = {}
        out = {}
        for w in sorted(set(whos)):
            m = np.array([x == w for x in whos])
            if m.sum() < 6:
                print("  %-8s n=%d 太少，跳过" % (w, m.sum())); continue
            C, core = robust_centroid(E[m])
            cen[w] = C
            s = E[m] @ C
            mu, sd = float(s[core].mean()), float(s[core].std() + 1e-9)
            z = (mu - s) / sd
            print("  %-8s n=%3d 核心%3d | cos 均值 %.3f σ %.3f 最低 %.3f | z p50 %.2f p90 %.2f p95 %.2f max %.2f"
                  % (w, m.sum(), core.sum(), mu, sd, s.min(),
                     *np.percentile(z, [50, 90, 95]), z.max()))
            for k, zz in zip(np.array(ids)[m], z):
                out[k] = float(zz)
        zs = np.array(list(out.values()))
        print("  全体 z: p50 %.2f p90 %.2f p95 %.2f p99 %.2f max %.2f"
              % (*np.percentile(zs, [50, 90, 95, 99]), zs.max()))
        # top-1 角色归属（最近中心）
        names = list(cen)
        Cm = np.stack([cen[n] for n in names])
        top1 = {}
        for i, k in enumerate(ids):
            sc = Cm @ E[i]
            top1[k] = (names[int(np.argmax(sc))], float(np.max(sc)),
                       names[int(np.argsort(-sc)[1])], float(np.sort(sc)[-2]))
        flip = [k for k in ids if top1[k][0] != plan[k]["who"]]
        print("  top-1 角色 != 标注角色: %d 条" % len(flip))
        hi = sorted(out.items(), key=lambda x: -x[1])[:12]
        print("  z 最高 12 条：")
        for k, zz in hi:
            t = top1[k]
            print("    %-8s %-8s %-7s z=%5.2f | top1 %s %.3f (2nd %s %.3f)%s"
                  % (k, plan[k]["who"], plan[k]["emo"], zz, t[0], t[1], t[2], t[3],
                     "  <== 归属翻" if t[0] != plan[k]["who"] else ""))
        json.dump({"z": out, "top1": {k: v for k, v in top1.items()}},
                  open("G:/_setup/_scs_%s.json" % model, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
