#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 8 档 ref 的裸底子（base，不打 emo 标签）按主判据对到情绪靶心上，
输出「每档天生能演什么情绪、到什么分位」。

主判据来自 ref_stats.json（calib.py 用真人正例分布标定）。
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TARGET = {  # 真人各情绪 VAD 均值（mini_vox 实测）
    "兴奋": (0.704, 0.659, 0.632),
    "激动反抗": (0.722, 0.345, 0.692),
    "警惕": (0.534, 0.275, 0.449),
    "紧张": (0.570, 0.332, 0.464),
    "委屈": (0.384, 0.396, 0.365),
    "平静": (0.574, 0.637, 0.554),
}

PRIMARY = {   # 情绪 -> (源, 特征名)，来自 calib.py 实测最优
    "兴奋":     ("vox", "a_x_v"),
    "激动反抗": ("vox", "d"),
    "紧张":     ("vox", "a_x_nd"),
    "委屈":     ("vox", "neg_a"),
    "警惕":     ("e2v", "厌恶/disgusted"),
    "平静":     ("vox", "v"),
}


def vox_feat(target_sum, key):
    A, V, D = target_sum
    return {"a": A, "v": V, "d": D, "neg_a": 1 - A, "neg_v": 1 - V, "neg_d": 1 - D,
            "a_x_v": A * V, "a_x_nd": A * (1 - D), "a_x_v_x_d": A * (1 - V) * D,
            "neg_a_neg_v_neg_d": (1 - A) * (1 - V) * (1 - D)}[key]


def main():
    stats = json.load(open(os.path.join(HERE, "out", "ref_stats.json"), encoding="utf-8"))
    vox = {json.loads(l)["path"]: json.loads(l) for l in open(os.path.join(HERE, "out", "gen_vox_dim.jsonl"), encoding="utf-8")}
    e2v = {json.loads(l)["path"]: json.loads(l) for l in open(os.path.join(HERE, "out", "var", "_base8_e2v.jsonl"), encoding="utf-8")}
    gen = [json.loads(l) for l in open(os.path.join(HERE, "out", "gen_index.jsonl"), encoding="utf-8") if '"base"' in l]

    def pct(v, dist):
        """v 落在真人正例分布 dist 的哪个分位"""
        arr = np.array([dist["p10"], dist["p25"], dist["p50"], dist["p75"], dist["p90"]])
        for i in range(1, len(arr)):
            if v <= arr[i]:
                q0, q1 = [10, 25, 50, 75, 90][i - 1] / 100.0, [10, 25, 50, 75, 90][i] / 100.0
                f = (v - arr[i - 1]) / max(1e-9, arr[i] - arr[i - 1])
                return q0 + f * (q1 - q0)
        return 0.90 + min(0.10, (v - arr[-1]) / max(1e-9, arr[-1]) * 0.3)

    rows = []
    for g in gen:
        pid, path = g["pid"], g["path"]
        sc = vox[path]["score"]
        A, V, D = sc["arousal"], sc["valence"], sc["dominance"]
        rec = {"pid": pid, "A": A, "V": V, "D": D, "dists": {}, "scores": {}}
        for emo, tgt in TARGET.items():
            rec["dists"][emo] = float(np.sqrt(sum((a - b) ** 2 for a, b in zip((A, V, D), tgt))))
        # 各情绪主判据的分位
        for emo, (src, key) in PRIMARY.items():
            if src == "vox":
                val = vox_feat((A, V, D), key)
            else:
                val = float(e2v[path]["score"].get(key, 0.0))
            st = stats[emo]["signals"].get("%s:%s" % (src, key))
            if st:
                rec["scores"][emo] = {"val": round(val, 4), "pct": round(pct(val, st["pos"]), 3),
                                      "tier": "到位" if val > st["threshold_fpr25"] else ("勉强" if val > st["threshold"] else "没演出来"),
                                      "auc": st["auc"]}
        rows.append(rec)

    print("=== 8 档 ref 裸底子（无 emo 标签）===")
    print("%-10s %6s %6s %6s  %-10s %6s" % ("ref", "A", "V", "D", "最贴情绪", "距离"))
    for r in sorted(rows, key=lambda x: -x["A"]):
        near = min(r["dists"].items(), key=lambda kv: kv[1])
        print("%-10s %.3f  %.3f  %.3f  %-10s %.3f" % (r["pid"], r["A"], r["V"], r["D"], near[0], near[1]))

    print()
    print("=== 主判据在真人正例分布中的分位（>=25% 算到位）===")
    emos = list(PRIMARY)
    print("%-10s %s" % ("ref", "".join("%-14s" % e for e in emos)))
    for r in sorted(rows, key=lambda x: -x["A"]):
        cells = []
        for e in emos:
            s = r["scores"].get(e)
            cells.append("%-14s" % ("%.0f%% %s" % (100 * s["pct"], s["tier"][:2]) if s else "-"))
        print("%-10s %s" % (r["pid"], "".join(cells)))

    print()
    print("=== 每档 ref 的最佳用法 ===")
    for r in sorted(rows, key=lambda x: -x["A"]):
        ok = [(e, s) for e, s in r["scores"].items() if s["tier"] == "到位"]
        ok.sort(key=lambda kv: -kv[1]["pct"])
        near = min(r["dists"].items(), key=lambda kv: kv[1])
        if ok:
            tag = " / ".join("%s(%.0f%%)" % (e, 100 * s["pct"]) for e, s in ok)
            print("%-10s 天生到位：%s" % (r["pid"], tag))
        else:
            best = max(r["scores"].items(), key=lambda kv: kv[1]["pct"]) if r["scores"] else None
            print("%-10s 无到位项；最接近 %s(%.0f%%)；VAD 最近 %s" % (
                r["pid"], best[0] if best else "-", 100 * best[1]["pct"] if best else 0, near[0]))

    json.dump(rows, open(os.path.join(HERE, "out", "ref_talent.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n-> out/ref_talent.json")


if __name__ == "__main__":
    main()
