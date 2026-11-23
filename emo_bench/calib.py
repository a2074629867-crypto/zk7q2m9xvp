# -*- coding: utf-8 -*-
"""标定判定线：对每条判据，找「负例只有 10%/25% 超过」的那条线，
再看真人正例有多少比例能过线（TPR@FPR）。

判据按实测 AUC 选（见 REPORT_EMOTION_JUDGE.md 第六节）：
  兴奋      vox  A×V            0.898
  激动反抗  vox  D              0.886
  警惕      e2v  disgusted      0.834
  紧张      vox  A×(1−D)        0.812
  委屈      vox  1−A            0.779
"""
import json, os
import numpy as np
from scipy.stats import rankdata

HERE = os.path.dirname(os.path.abspath(__file__))
FPR = 10.0

SPEC = {
    "兴奋": [("vox", "a_x_v"), ("vox", "v"), ("e2v", "开心/happy")],
    "激动反抗": [("vox", "d"), ("vox", "a_x_v_x_d"), ("e2v", "生气/angry")],
    "警惕": [("e2v", "厌恶/disgusted"), ("vox", "a_x_nd")],
    "紧张": [("vox", "a_x_nd"), ("vox", "a"), ("phys", "f0_med")],
    "委屈": [("vox", "neg_a"), ("vox", "neg_a_neg_v_neg_d"), ("e2v", "难过/sad")],
    "平静": [("vox", "v"), ("e2v", "中立/neutral")],
}


def vox_feat(sc, key):
    A = float(sc.get("arousal", 0)); V = float(sc.get("valence", 0)); D = float(sc.get("dominance", 0))
    return {"a": A, "v": V, "d": D, "neg_a": 1 - A, "neg_v": 1 - V, "neg_d": 1 - D,
            "a_x_v": A * V, "a_x_nd": A * (1 - D), "a_x_v_x_d": A * (1 - V) * D,
            "neg_a_neg_v_neg_d": (1 - A) * (1 - V) * (1 - D)}.get(key, 0.0)


def pct(v):
    v = np.asarray(v, float)
    return {"p10": round(float(np.percentile(v, 10)), 4),
            "p25": round(float(np.percentile(v, 25)), 4),
            "p50": round(float(np.percentile(v, 50)), 4),
            "p75": round(float(np.percentile(v, 75)), 4),
            "p90": round(float(np.percentile(v, 90)), 4)}


def load(p):
    if not os.path.exists(p):
        return {}
    return {os.path.normcase(json.loads(l)["path"]): json.loads(l)["score"]
            for l in open(p, encoding="utf-8")}


def main():
    E = load(os.path.join(HERE, "out", "sub_e2v.jsonl"))
    VX = load(os.path.join(HERE, "out", "mini_vox.jsonl"))
    P = load(os.path.join(HERE, "out", "mini_phys.jsonl"))
    L = {os.path.normcase(json.loads(l)["path"]): json.loads(l)
         for l in open(os.path.join(HERE, "out", "labels_subset.jsonl"), encoding="utf-8")}
    Lm = {os.path.normcase(json.loads(l)["path"]): json.loads(l)
          for l in open(os.path.join(HERE, "out", "labels_mini.jsonl"), encoding="utf-8")}

    def val(src, key, k):
        if src == "e2v":
            return float(E.get(k, {}).get(key, 0))
        if src == "vox":
            return vox_feat(VX.get(k, {}), key)
        return float(P.get(k, {}).get(key, 0))

    out = {}
    print("%-8s %-22s %5s %8s %7s %7s %6s" % ("情绪", "判据", "n正", "阈值", "TPR@10", "TPR@25", "AUC"))
    for g, sigs in SPEC.items():
        rec = {"n_pos": 0, "signals": {}}
        for src, key in sigs:
            pos = [val(src, key, k) for k, v in Lm.items() if v["emotion"] == g]
            neg = [val(src, key, k) for k, v in Lm.items() if v["emotion"] != g]
            if src == "e2v":   # e2v 用大样本
                pos = [val(src, key, k) for k, v in L.items() if v["emotion"] == g and k in E]
                neg = [val(src, key, k) for k, v in L.items() if v["emotion"] != g and k in E]
            if len(pos) < 20 or len(neg) < 20:
                continue
            rec["n_pos"] = len(pos)
            thr = float(np.percentile(neg, 100 - FPR))
            thr25 = float(np.percentile(neg, 75))
            tpr = float(np.mean(np.asarray(pos) > thr))
            tpr25 = float(np.mean(np.asarray(pos) > thr25))
            y = np.array([1] * len(pos) + [0] * len(neg))
            r = rankdata(np.array(pos + neg))
            n1, n0 = len(pos), len(neg)
            a = float((r[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
            k2 = "%s:%s" % (src, key)
            rec["signals"][k2] = {
                "threshold": round(thr, 5), "tpr_at_fpr10": round(tpr, 3),
                "threshold_fpr25": round(thr25, 5), "tpr_at_fpr25": round(tpr25, 3),
                "auc": round(a, 4), "pos": pct(pos), "neg": pct(neg),
            }
            print("%-8s %-22s %5d %8.4g %6.1f%% %6.1f%% %6.3f"
                  % (g, k2, len(pos), thr, 100 * tpr, 100 * tpr25, a))
        out[g] = rec

    p = os.path.join(HERE, "out", "ref_stats.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s" % p)


if __name__ == "__main__":
    main()
