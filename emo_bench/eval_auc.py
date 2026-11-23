# -*- coding: utf-8 -*-
"""单句情绪「有没有」AUC 评估表。

对每个情绪组做 one-vs-rest，看每个引擎的原始输出能不能把正例排在负例前面。
零样本、不训练、不调阈值 —— AUC 就是「这个信号能不能判断这句话有没有该情绪」。

用法：
  python eval_auc.py --labels out/labels_subset.jsonl \
      --engines e2v=out/sub_e2v.jsonl vox=out/sub_vox.jsonl deear=out/sub_deear.jsonl
"""
import json, os, sys, argparse, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = ["委屈", "激动反抗", "警惕", "紧张", "兴奋", "惊讶", "平静"]


def auc(y, s):
    y = np.asarray(y, int)
    s = np.asarray(s, float)
    n1 = int(y.sum()); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    o = np.argsort(s, kind="mergesort")
    r = np.empty(len(s)); ss = s[o]; i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]:
            j += 1
        r[o[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def boot_ci(y, s, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    y = np.asarray(y); s = np.asarray(s)
    v = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        a = auc(y[i], s[i])
        if not math.isnan(a):
            v.append(a)
    return (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) if v else (float("nan"),) * 2


# 引擎输出 → 每类情绪的候选打分函数
def scores_of(engine, rec):
    """返回 {列名: 分数}，分数越高越像该情绪。列名会显示在表里。"""
    d = {}
    sc = rec.get("score") or {}
    if engine == "e2v":
        m = {"委屈": ["难过/sad"], "激动反抗": ["生气/angry"], "警惕": ["厌恶/disgusted"],
             "紧张": ["恐惧/fearful"], "兴奋": ["开心/happy"], "惊讶": ["吃惊/surprised"],
             "平静": ["中立/neutral"]}
        for g, ks in m.items():
            d[g + "|e2v"] = max(float(sc.get(k, 0)) for k in ks)
    elif engine in ("vox", "vox_dim"):
        A = float(sc.get("arousal", 0)); V = float(sc.get("valence", 0)); D = float(sc.get("dominance", 0))
        d["A"] = A; d["V"] = V; d["D"] = D; d["-V"] = 1 - V
        d["A×-V"] = A * (1 - V)
        d["-V×-D"] = (1 - V) * (1 - D)
        d["A×D"] = A * D
        d["A×-D"] = A * (1 - D)
        d["-A×-V×-D"] = (1 - A) * (1 - V) * (1 - D)
        d["A×-V×D"] = A * (1 - V) * D
        d["A×V"] = A * V
        d["-A"] = 1 - A
    elif engine == "deear":
        d["A"] = float(sc.get("score_arousal", 0))
        d["P"] = float(sc.get("score_prosody", 0))
        d["N"] = float(sc.get("score_nature", 0))
        d["EXP"] = float(sc.get("score_expressive", 0))
    elif engine == "sv":
        t = sc.get("_top", "")
        for g in GROUPS + ["困惑", "困倦", "渴望"]:
            d[g] = 0.0
        mp = {"委屈": "SAD", "激动反抗": "ANGRY", "警惕": "DISGUSTED", "紧张": "FEARFUL",
              "兴奋": "HAPPY", "惊讶": "SURPRISED", "平静": "NEUTRAL"}
        for g, tag in mp.items():
            d[g] = 1.0 if t == tag else 0.0
    elif engine == "phys":
        for k in ("f0_med", "f0_std", "f0_p90", "hnr", "speech_db", "voiced_ratio"):
            d[k] = float(sc.get(k, 0) or 0)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--engines", nargs="+", required=True, help="名字=路径")
    ap.add_argument("--top", type=int, default=4, help="每个情绪显示前 N 个信号")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    lab = [json.loads(l) for l in open(a.labels, encoding="utf-8")]
    key_of = {os.path.normcase(r["path"]): r for r in lab}

    engs = []
    for spec in a.engines:
        name, path = spec.split("=", 1)
        if not os.path.exists(path):
            print("缺 " + path); continue
        rows = {}
        for ln in open(path, encoding="utf-8"):
            try:
                r = json.loads(ln)
                rows[os.path.normcase(r["path"])] = r
            except Exception:
                pass
        engs.append((name, rows))
        print("%-6s %d 条" % (name, len(rows)))

    # 交集
    common = set(key_of)
    for _, rows in engs:
        common &= set(rows)
    paths = [p for p in key_of if p in common]
    print("交集 %d 条\n" % len(paths))

    result = {}
    for g in GROUPS:
        y = np.array([1 if key_of[p]["emotion"] == g else 0 for p in paths])
        if y.sum() < 20:
            continue
        cols = {}
        for name, rows in engs:
            first = scores_of(name, rows[paths[0]])
            for cname in first:
                cols["%s|%s" % (name, cname)] = np.array(
                    [scores_of(name, rows[p]).get(cname, 0.0) for p in paths])
        # e2v 自带组名，避免重复列
        cols = {k: v for k, v in cols.items() if len(set(v.tolist())) > 1}
        table = []
        for k, v in cols.items():
            au = auc(y, v)
            table.append((au, k))
        table.sort(reverse=True)
        result[g] = {"n": int(len(y)), "pos": int(y.sum()),
                     "auc": [{"sig": k, "auc": round(au, 4), "ci": [round(x, 3) for x in boot_ci(y, cols[k])]}
                             for au, k in table]}
        print("【%s】 n=%d 正例=%d" % (g, len(y), y.sum()))
        for au, k in table[:a.top]:
            lo, hi = boot_ci(y, cols[k])
            print("   %.3f  [%.3f,%.3f]  %s" % (au, lo, hi, k))
        print()

    if a.out:
        json.dump(result, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("->", a.out)


if __name__ == "__main__":
    main()
