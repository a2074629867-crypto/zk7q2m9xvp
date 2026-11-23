# -*- coding: utf-8 -*-
"""_voice_split.py —— 按 voice 档分组，检验「同一角色的不同情绪档是不是同一个音色」。

这是 SCS 高分条目的根因排查：若 Joseph 的 normal 档 cos 0.93、nervous/defiant 档 0.5，
那不是「个别句子离群」，而是**参考库档间本身不同源**（素材问题，重生成修不好）。
判据：组内 cos（同档多句）应接近 1；组间 cos（不同档）若显著低 ⇒ 档间换人。
"""
import json, sys
import numpy as np

sys.path.insert(0, "G:/_setup")


def nrm(v):
    return v / (np.linalg.norm(v) + 1e-9)


def main():
    plan = {}
    for l in open("G:/_setup/_dlg_plan_v2.jsonl", encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l); plan[o["id"]] = o
    for model in ("r34", "eres2net"):
        z = np.load("G:/_setup/_utt_emb/%s.npz" % model)
        ids, whos, E = list(z["ids"]), list(z["whos"]), z["embs"]
        print("=" * 78)
        print("模型", model)
        for who in ("Joseph", "Thomas", "Charles", "Helena"):
            idx = [i for i, w in enumerate(whos) if w == who]
            if len(idx) < 6:
                continue
            groups = {}
            for i in idx:
                groups.setdefault(plan[ids[i]]["voice"], []).append(i)
            groups = {k: v for k, v in groups.items() if len(v) >= 2}
            if len(groups) < 2:
                continue
            print("\n-- %s（%d 条，%d 个档有≥2句）" % (who, len(idx), len(groups)))
            names = list(groups)
            cen = {k: nrm(E[groups[k]].mean(0)) for k in names}
            # 组内
            for k in names:
                S = E[groups[k]]
                cs = []
                for a in range(len(S)):
                    for b in range(a + 1, len(S)):
                        cs.append(float(S[a] @ S[b]))
                print("   %-22s n=%2d 组内 cos p50 %.3f  min %.3f"
                      % (k, len(S), np.median(cs) if cs else 1.0, min(cs) if cs else 1.0))
            # 组间
            print("   组间中心 cos：")
            for a in range(len(names)):
                for b in range(a + 1, len(names)):
                    print("     %-22s x %-22s %.3f" % (names[a], names[b],
                                                       float(cen[names[a]] @ cen[names[b]])))


if __name__ == "__main__":
    main()
