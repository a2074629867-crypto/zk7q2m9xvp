# -*- coding: utf-8 -*-
"""域内锚点能否救回到位度指标（不训练任何模型，只把锚点换成同域样本）。
数据：59 条已交付对白（ch123_final），标注 calm 34 / sad 11 / happy 7。
做法：5 折，锚点 = 其余折的同标注情绪样本均值，测留出折。
对照：① 域内锚点 ② 跨域锚点（Expresso 真人） ③ 分类 top-1 ④ 全猜多数类
"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)

rows = json.load(open(os.path.join(OUT, "book_judge.json"), encoding="utf-8"))["rows"]
MAP = {"calm": "neutral", "sad": "sad", "happy": "happy"}
items = [r for r in rows if MAP.get((r.get("emo") or "").lower())]
print("可用 %d 条：%s" % (len(items), {c: sum(1 for r in items if MAP[r['emo'].lower()] == c)
                                    for c in ["happy", "sad", "neutral"]}))

# e2v 嵌入
import ser as S
cache = os.path.join(OUT, "book_e2v_emb.json")
emb = json.load(open(cache, encoding="utf-8")) if os.path.exists(cache) else {}
need = [r["id"] for r in items if r["id"] not in emb]
if need:
    M = S.E2V(model="G:/_setup/models/ms/iic/emotion2vec_plus_large")
    for i, rid in enumerate(need):
        w = os.path.join("G:/_setup/ch123_final", rid + ".wav")
        if not os.path.exists(w):
            continue
        rr = M.m.generate(w, granularity="utterance", extract_embedding=True)
        if rr:
            f = np.asarray(rr[0]["feats"], dtype=np.float32)
            emb[rid] = (f.mean(0) if f.ndim > 1 else f).ravel().tolist()
    json.dump(emb, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
print("嵌入 %d 条" % len(emb))

def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

for tag, keys in [("Adh-e2v 嵌入", "e2v"), ("Adh-vad 三维", "vad")]:
    X = {}
    for r in items:
        if keys == "e2v":
            v = emb.get(r["id"])
            if v is None:
                continue
            X[r["id"]] = np.array(v, dtype=np.float32)
        else:
            X[r["id"]] = np.array([r["A"], r["D"], r["V"]], dtype=np.float32)
    ids = [r["id"] for r in items if r["id"] in X]
    gt = {r["id"]: MAP[(r["emo"] or "").lower()] for r in items}
    rng = np.random.default_rng(0)
    order = np.array(ids); rng.shuffle(order)
    folds = np.array_split(order, 5)
    y, p = [], []
    for f in folds:
        tr = [i for i in order if i not in set(f.tolist())]
        proto = {}
        for c in ["happy", "sad", "neutral"]:
            vs = [X[i] for i in tr if gt[i] == c]
            if vs:
                proto[c] = np.mean(np.stack(vs), 0)
        for i in f:
            sc = {k: cos(X[i], proto[k]) for k in proto}
            y.append(gt[i]); p.append(max(sc, key=sc.get))
    acc = np.mean([a == b for a, b in zip(y, p)])
    base = max(y.count(c) for c in set(y)) / len(y)
    print("\n%s  域内锚点 5 折：accuracy = %.3f   全猜多数类 = %.3f  n=%d"
          % (tag, acc, base, len(y)))
    labels = ["happy", "sad", "neutral"]
    print("  %-9s %s" % ("", "".join("%-9s" % c for c in labels)))
    for c in labels:
        row = [sum(1 for a, b in zip(y, p) if a == c and b == d) for d in labels]
        print("  %-9s %s  n=%d" % (c, "".join("%-9d" % v for v in row), sum(row)))
