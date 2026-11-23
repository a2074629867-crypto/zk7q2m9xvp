# -*- coding: utf-8 -*-
"""单句情绪「有没有」判定 —— 零样本 AUC 基准

核心问题：给定一句话，能不能判断出它有没有「委屈 / 激动反抗 / 警惕 / 紧张」？
评估方式：把每个引擎的原始输出当作打分（不训练、不调阈值），
         对每个情绪做 one-vs-rest，算 AUC。
         AUC 与阈值无关，纯粹衡量「排序能力」= 这个引擎到底能不能区分。

  AUC = 0.50  瞎猜
  AUC = 0.70  可用（弱）
  AUC = 0.80  好用
  AUC = 0.90  强

引擎（全部零样本，用现成权重）：
  e2v       emotion2vec+ large 9 类概率
  vox_dim   MSP-Podcast 维度头 A/V/D
  deear     DeEAR 三维 + 融合分（人耳 SRCC 0.86）
  phys      纯声学（F0/能量/HNR/语速）
  sv        SenseVoice 离散标签

数据集标签是多标签（"Sad, Angry" 这种），正好对应「一句话同时有几种情绪」。
"""
import json, os, sys, argparse, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 用户点名的四类 + 常用类。键是中文名，值是标签别名（原数据集写法不统一）
GROUPS = {
    "委屈":     ["sad", "Sad", "sadness", "Sadness", "Frustration", "frustration", "disappointed"],
    "激动反抗": ["angry", "Angry", "anger", "Anger", "agitated"],
    "警惕":     ["disgusted", "Disgusted", "disgust", "Disgust", "contempt", "sarcastic"],
    "紧张":     ["fear", "Fear", "fearful", "Fearful", "anxious", "nervous"],
    "兴奋":     ["happy", "Happy", "elated", "amused", "excited"],
    "惊讶":     ["surprised", "Surprised", "surprise", "Surprise"],
    "平静":     ["neutral", "Neutral", "calm", "Calm", "default"],
}


def parse_labels(s):
    """把 "Sad, Angry" / "sad" / "Angry, Surprised, Other" 拆成集合。"""
    if not s:
        return set()
    parts = [p.strip() for p in str(s).replace("/", ",").replace(";", ",").split(",")]
    return set([p for p in parts if p])


def auc(y_true, y_score):
    """Mann-Whitney U 版 AUC（含并列处理）。"""
    y = np.asarray(y_true, dtype=int)
    s = np.asarray(y_score, dtype=float)
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=float)
    ss = s[order]
    i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def auc_ci(y, s, n_boot=2000, seed=0):
    """bootstrap 95% CI。"""
    rng = np.random.default_rng(seed)
    y = np.asarray(y); s = np.asarray(s)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        a = auc(y[idx], s[idx])
        if not np.isnan(a):
            vals.append(a)
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def load_scores(rows, engine):
    """从已落盘的引擎 jsonl 里取每条音频的分数向量，返回 dict path->vector。"""
    out = {}
    for r in rows:
        p = r.get("path") or r.get("audio_path")
        out[os.path.normcase(p)] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True, help="统一标签 jsonl: path, emotion, speaker")
    ap.add_argument("--engines", default="e2v,vox_dim,deear,phys")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "bench_judge.json"))
    a = ap.parse_args()

    lab = [json.loads(l) for l in open(a.labels, encoding="utf-8")]
    print("标注入 %d 条" % len(lab), flush=True)

    eng = a.engines.split(",")
    score = {}
    for e in eng:
        f = os.path.join(HERE, "out", "real_%s.jsonl" % e)
        if not os.path.exists(f):
            print("缺 %s" % f); continue
        score[e] = load_scores([json.loads(l) for l in open(f, encoding="utf-8")], e)
        print("  %s: %d 条" % (e, len(score[e])))

    # 只保留每类情绪正样本 >=20 的
    present = {g: 0 for g in GROUPS}
    for r in lab:
        ls = parse_labels(r.get("emotion"))
        for g, aliases in GROUPS.items():
            if ls & set(aliases):
                present[g] += 1
    groups = [g for g, n in present.items() if n >= 20]
    print("可评估情绪:", ", ".join("%s(%d)" % (g, present[g]) for g in groups), flush=True)

    result = {"n": len(lab), "groups": {}}

    # ── 特征提取器：引擎原始输出 → 目标情绪打分 ──────────────────────
    def scorers(e, rec):
        """返回 {情绪组: 分数}；分数越高越像该情绪。"""
        d = {}
        if e == "e2v":
            pr = rec.get("score") or rec.get("probs") or {}
            if isinstance(pr, dict):
                m = {"委屈": ["难过/sad"], "激动反抗": ["生气/angry"], "警惕": ["厌恶/disgusted"],
                     "紧张": ["恐惧/fearful"], "兴奋": ["开心/happy"], "惊讶": ["吃惊/surprised"],
                     "平静": ["中立/neutral"]}
                for g, ks in m.items():
                    d[g] = max([float(pr.get(k, 0)) for k in ks] or [0.0])
        elif e == "vox_dim":
            s = rec.get("score", {})
            A, V, D = float(s.get("arousal", 0)), float(s.get("valence", 0)), float(s.get("dominance", 0))
            # 维度分区（心理学 circumplex + 支配度）：不训练，纯定义
            d["委屈"] = (1 - V) * (1 - A) * (1 - D)
            d["激动反抗"] = A * (1 - V) * D
            d["警惕"] = (1 - V) * A * (1 - abs(D - 0.5)) * D
            d["紧张"] = A * (1 - V) * (1 - D)
            d["兴奋"] = A * V
            d["惊讶"] = A * abs(V - 0.5)
            d["平静"] = (1 - A) * (1 - abs(V - 0.5))
        elif e == "deear":
            A = float(rec.get("score_arousal", 0))
            P = float(rec.get("score_prosody", 0))
            d["_exp"] = float(rec.get("score_expressive", 0))
            d["_A"] = A
            d["_P"] = P
        elif e == "phys":
            s = rec.get("score", rec)
            d["_f0span"] = float(s.get("f0_span", s.get("f0_std", 0)) or 0)
            d["_db"] = float(s.get("speech_db", -30) or -30)
        return d

    for g in groups:
        y = []
        vec = {e: [] for e in eng}
        skip = collections.Counter()
        for r in lab:
            ls = parse_labels(r.get("emotion"))
            key = os.path.normcase(r["path"])
            got = False
            for e in eng:
                if e not in score or key not in score[e]:
                    skip[e] += 1
            # 只要四大引擎都有这条
            if all(e in score and key in score[e] for e in eng):
                y.append(1 if (ls & set(GROUPS[g])) else 0)
                for e in eng:
                    vec[e].append(scorers(e, score[e][key]))
                got = True
            if not got:
                continue
        if not y or sum(y) < 20:
            continue
        y = np.array(y)
        res = {"n": len(y), "pos": int(y.sum())}
        for e in eng:
            keys = [k for k in vec[e][0].keys() if not k.startswith("_")] if vec[e] and vec[e][0] else []
            for k in keys:
                s = np.array([v.get(k, 0.0) for v in vec[e]])
                if len(set(s.tolist())) < 2:
                    continue
                au = auc(y, s)
                lo, hi = auc_ci(y, s)
                res["%s:%s" % (e, k)] = {"auc": round(au, 4), "ci": [round(lo, 3), round(hi, 3)]}
        result["groups"][g] = res
        print("\n【%s】 n=%d 正例=%d" % (g, res["n"], res["pos"]))
        rank = sorted([(v["auc"], k) for k, v in res.items() if isinstance(v, dict) and "auc" in v], reverse=True)
        for au, k in rank:
            print("   %.3f  %s" % (au, k))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(result, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s" % a.out)


if __name__ == "__main__":
    main()
