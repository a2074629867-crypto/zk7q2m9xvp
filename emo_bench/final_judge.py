#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对交付成品（ch123_final）做情绪到位度体检。
按每条自己的目标情绪选判据，输出分位 + 三档判定。"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(HERE, *a)

PRIMARY = {
    "兴奋": ("vox", "a_x_v"),
    "激动反抗": ("vox", "d"),
    "紧张": ("vox", "a_x_nd"),
    "委屈": ("vox", "neg_a"),
    "警惕": ("e2v", "厌恶/disgusted"),
    "平静": ("vox", "v"),
}


def vf(A, V, D, k):
    return {"a": A, "v": V, "d": D, "neg_a": 1 - A, "neg_v": 1 - V, "neg_d": 1 - D,
            "a_x_v": A * V, "a_x_nd": A * (1 - D)}[k]


def pct(v, dist):
    arr = np.array([dist["p10"], dist["p25"], dist["p50"], dist["p75"], dist["p90"]])
    qs = [.10, .25, .50, .75, .90]
    for i in range(1, len(arr)):
        if v <= arr[i]:
            f = (v - arr[i - 1]) / max(1e-9, arr[i] - arr[i - 1])
            return qs[i - 1] + f * (qs[i] - qs[i - 1])
    return .90 + min(.10, (v - arr[-1]) / max(1e-9, arr[-1]) * .3)


def main():
    stats = json.load(open(P("out", "ref_stats.json"), encoding="utf-8"))
    lab = [json.loads(l) for l in open(P("out", "final_labels.jsonl"), encoding="utf-8")]
    vox = {json.loads(l)["path"]: json.loads(l)["score"] for l in open(P("out", "final_vox.jsonl"), encoding="utf-8")}
    e2v_path = P("out", "final_e2v.jsonl")
    e2v = {}
    if os.path.exists(e2v_path):
        for l in open(e2v_path, encoding="utf-8"):
            d = json.loads(l)
            e2v[d["path"]] = d["score"]

    rows = []
    for it in lab:
        p = it["path"]
        if p not in vox:
            continue
        emo = it["emotion"]
        src, key = PRIMARY[emo]
        if src == "vox":
            sc = vox[p]
            val = vf(sc["arousal"], sc["valence"], sc["dominance"], key)
        else:
            if p not in e2v:
                continue
            val = float(e2v[p].get(key, 0.0))
        st = stats[emo]["signals"]["%s:%s" % (src, key)]
        q = pct(val, st["pos"])
        tier = "到位" if q >= 0.25 else ("勉强" if q >= 0.10 else "没演出来")
        rows.append(dict(wid=it["wid"], who=it["who"], emo=emo, val=val, pct=q, tier=tier,
                         auc=st["auc"], text=it.get("text", "")))

    print("=== 交付成品 59 条：按目标情绪体检 ===")
    print("%-6s %-3s %-6s %8s %7s %-8s %s" % ("id", "人", "目标", "判据值", "分位", "判定", "台词"))
    for r in sorted(rows, key=lambda x: (x["emo"], x["pct"])):
        print("%-6s %-3s %-6s %8.3f %6.0f%% %-8s %s" % (
            r["wid"], r["who"], r["emo"], r["val"], 100 * r["pct"], r["tier"], r["text"][:38]))

    print()
    print("=== 汇总 ===")
    import collections
    by = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        by[r["emo"]][r["tier"]] += 1
    print("%-8s %5s %6s %6s %6s %8s" % ("目标", "n", "到位", "勉强", "没演", "到位率"))
    for emo, c in sorted(by.items(), key=lambda x: -sum(x[1].values())):
        n = sum(c.values())
        print("%-8s %5d %6d %6d %6d %7.0f%%" % (emo, n, c["到位"], c["勉强"], c["没演出来"], 100 * c["到位"] / n))

    json.dump(rows, open(P("out", "final_judge.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> out/final_judge.json")


if __name__ == "__main__":
    main()
