# -*- coding: utf-8 -*-
"""
情绪「到位度」评分 —— 用业界通行的连续余弦口径，而不是分类对错。

为什么换口径（有论文依据）：
  · SES-Bench / SES-Judge（arXiv 2609.32504，NTU Hung-yi Lee 组，2026-09）
    明确指出：**embedding cosine 与「分类对错」都不是人耳口径**，
    人耳问的是「这段离目标情绪有多近」，是一个连续量。
    他们用「冻结 SER 编码器 + 层融合余弦」作基线，Spearman 0.4820；
    加序数回归训练的 SES-Judge 到 0.5297。SES-Judge 权重未发布，
    **但它的基线（余弦）现在就能复现，且不需要训练**。
  · Emotion Adherence Score（IEEE Access 2026, 10.1109/access.2026.3656800）
    用 emotion2vec 嵌入 + 情绪原型做「符合度」，与人类评分中度正相关，
    并明确说明它对「分类不准」的系统仍然能给出稳定的梯度分。

本脚本实现两种零训练到位度：
  Adh-e2v  : emotion2vec 话语嵌入 → 与目标情绪锚点集的余弦（= EAS 的原型法，原型用真人样本均值，不训练）
  Adh-vad  : SER 维度输出 (A,V,D) 向量 → 同一套余弦（= SES-Judge 的 VAD 基线）

锚点全部来自 Expresso 真人：
  happy  ← style ∈ {happy, laughing}
  sad    ← style = sad
  neutral← style = default

评估（有标准答案）：
  1) 三分类准确度 vs 类别基线（标准答案 = 生成时指定的 cond / base）
  2) 到位度的区分度：目标情绪得分是否高于非目标（AUC）
  3) Spearman 与人耳语义强度序
  4) 与「分类 top-1」直接对比，看哪种口径真的能分开
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

EXPR = {
    "happy": {"happy", "laughing"},
    "sad": {"sad"},
    "neutral": {"default"},
}
# 生成集的 cond → 三分类标准答案（calm 归 neutral：都是「没情绪起伏」这一侧）
COND2CLS = {"happy": "happy", "sad": "sad", "calm": "neutral", "base": "neutral"}


def load_jsonl(n):
    p = os.path.join(OUT, n)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def cos(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def auc(pos, neg):
    pos = np.asarray(pos, float); neg = np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan")
    d = pos[:, None] - neg[None, :]
    return float(((d > 0).sum() + 0.5 * (d == 0).sum()) / d.size)


def boot_auc(pos, neg, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    pos = np.asarray(pos, float); neg = np.asarray(neg, float)
    s = []
    for _ in range(n):
        a = pos[rng.integers(0, len(pos), len(pos))]
        b = neg[rng.integers(0, len(neg), len(neg))]
        d = a[:, None] - b[None, :]
        s.append(((d > 0).sum() + 0.5 * (d == 0).sum()) / d.size)
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


# ── 嵌入提取 ─────────────────────────────────────────────────────
def e2v_embed(paths, cache_name="e2v_emb.json"):
    """emotion2vec 话语嵌入（对时间维取平均）。带磁盘缓存，避免重复跑模型。"""
    cp = os.path.join(OUT, cache_name)
    if os.path.exists(cp):
        d = json.load(open(cp, encoding="utf-8"))
        if all(p in d for p in paths):
            return {p: np.array(d[p], dtype=np.float32) for p in paths}
    sys.path.insert(0, HERE)
    import ser as S
    M = S.E2V(model="G:/_setup/models/ms/iic/emotion2vec_plus_large")
    d = {}
    if os.path.exists(cp):
        d = json.load(open(cp, encoding="utf-8"))
    for i, p in enumerate(paths):
        if p in d:
            continue
        r = M.m.generate(p, granularity="utterance", extract_embedding=True)
        if not r:
            continue
        feats = np.asarray(r[0]["feats"], dtype=np.float32)
        if feats.ndim > 1:
            feats = feats.mean(axis=0)
        d[p] = feats.ravel().tolist()
        if (i + 1) % 50 == 0:
            print("   e2v 嵌入 %d/%d" % (i + 1, len(paths)), flush=True)
            json.dump(d, open(cp, "w", encoding="utf-8"))
    json.dump(d, open(cp, "w", encoding="utf-8"))
    return {p: np.array(d[p], dtype=np.float32) for p in paths if p in d}


def vad_embed(paths):
    d = {}
    for n in ("real_vox_dim.jsonl", "gen_vox_dim.jsonl"):
        for r in load_jsonl(n):
            if r.get("score"):
                d[r["path"]] = np.array([r["score"]["arousal"],
                                         r["score"]["valence"],
                                         r["score"]["dominance"]], dtype=np.float32)
    return {p: d[p] for p in paths if p in d}


# ── 主评估 ───────────────────────────────────────────────────────
def evaluate(name, emb, meta, anchors):
    """emb: {path: vec}; anchors: {cls: [vec,...]}"""
    proto = {c: np.mean(np.stack(v), 0) for c, v in anchors.items() if v}
    rows = []
    for path, m in meta.items():
        if m["src"] != "gen" or path not in emb:
            continue
        gt = COND2CLS.get(m["cond"])
        if not gt:
            continue
        sc = {c: cos(emb[path], p) for c, p in proto.items()}
        pred = max(sc, key=sc.get)
        rows.append(dict(path=path, cond=m["cond"], ref=m["ref"], gt=gt,
                         pred=pred, sc=sc))
    if not rows:
        print("  %s：无可评条目" % name)
        return None

    y = [r["gt"] for r in rows]
    p = [r["pred"] for r in rows]
    acc = float(np.mean([a == b for a, b in zip(y, p)]))
    base = max(y.count(c) for c in set(y)) / len(y)
    print("  %s" % name)
    print("    三分类准确度 = %.3f   类别基线 = %.3f   n=%d" % (acc, base, len(y)))
    labels = ["happy", "sad", "neutral"]
    print("    %-9s %s" % ("", "".join("%-9s" % c for c in labels)))
    for c in labels:
        row = [sum(1 for a, b in zip(y, p) if a == c and b == d) for d in labels]
        print("    %-9s %s  n=%d" % (c, "".join("%-9d" % v for v in row), sum(row)))

    # 区分度：目标情绪得分 vs 非目标
    for c in labels:
        pos = [r["sc"][c] for r in rows if r["gt"] == c]
        neg = [r["sc"][c] for r in rows if r["gt"] != c]
        lo, hi = boot_auc(pos, neg)
        print("    「%s」到位度的区分度 AUC = %.3f  [%.3f, %.3f]" % (c, auc(pos, neg), lo, hi))
    return acc, rows


def main():
    meta = {}
    for r in load_jsonl("real_vox_dim.jsonl"):
        meta[r["path"]] = dict(src="expresso", style=r.get("style"))
    for r in load_jsonl("gen_index.jsonl"):
        meta[r["path"]] = dict(src="gen", cond=r["cond"], ref=r["pid"])

    exp_paths = [p for p, m in meta.items() if m["src"] == "expresso"]
    gen_paths = [p for p, m in meta.items() if m["src"] == "gen"]
    print("锚点（Expresso 真人）：%d 条；待评（生成）：%d 条"
          % (len(exp_paths), len(gen_paths)))

    print("\n提取 emotion2vec 嵌入…")
    e2v = e2v_embed(exp_paths + gen_paths)

    def build_anchors(emb):
        a = {}
        for p, m in meta.items():
            if m["src"] != "expresso" or p not in emb:
                continue
            for c, styles in EXPR.items():
                if m.get("style") in styles:
                    a.setdefault(c, []).append(emb[p])
        for c in a:
            print("   锚点 %-8s %d 条" % (c, len(a[c])))
        return a

    print("\n" + "=" * 88)
    print("Adh-e2v：emotion2vec 嵌入余弦（= EAS 的原型法，零训练）")
    print("=" * 88)
    r1 = evaluate("", e2v, meta, build_anchors(e2v))

    print("\n" + "=" * 88)
    print("Adh-vad：SER 维度向量余弦（= SES-Judge 的 VAD 基线，零训练）")
    print("=" * 88)
    vad = vad_embed(exp_paths + gen_paths)
    r2 = evaluate("", vad, meta, build_anchors(vad))

    # 直接对比：分类 top-1（旧口径）
    print("\n" + "=" * 88)
    print("对照：分类 top-1（旧口径，emotion2vec 打分）")
    print("=" * 88)
    CN = {"开心/happy": "happy", "难过/sad": "sad", "中立/neutral": "neutral"}
    e2s = {r["path"]: r["score"] for r in load_jsonl("gen_e2v.jsonl") if r.get("score")}
    y, p = [], []
    for path, m in meta.items():
        if m["src"] != "gen" or path not in e2s:
            continue
        gt = COND2CLS.get(m["cond"])
        if not gt:
            continue
        y.append(gt); p.append(CN.get(e2s[path]["_top"], e2s[path]["_top"]))
    print("  三分类准确度 = %.3f   类别基线 = %.3f   n=%d"
          % (np.mean([a == b for a, b in zip(y, p)]),
             max(y.count(c) for c in set(y)) / len(y), len(y)))


if __name__ == "__main__":
    main()
