# -*- coding: utf-8 -*-
"""把某一簇再拆开，并打印每簇样本文本（用于人工认人）。"""
import json, os, sys, collections
import numpy as np
sys.path.insert(0, "G:/_setup")

cuedir = sys.argv[1]
k = int(sys.argv[2]) if len(sys.argv) > 2 else 2
keep_cl = int(sys.argv[3]) if len(sys.argv) > 3 else 0

d = json.load(open(os.path.join(cuedir, "cues.json"), encoding="utf-8"))
cs = d if isinstance(d, list) else d["cues"]
cl = json.load(open(os.path.join(cuedir, "cluster.json"), encoding="utf-8"))["rows"]
byf = {r["file"]: r for r in cl}

sel = [c for c in cs if byf.get(os.path.basename(c["path"]), {}).get("cl") == keep_cl
       and c["dur"] >= 1.5 and not c.get("multi") and not c.get("sfx")]
print("选中 %d 条" % len(sel), flush=True)

cache = os.path.join(cuedir, "_emb_sub%d.npz" % keep_cl)
files = [os.path.basename(c["path"]) for c in sel]
E = None
if os.path.exists(cache):
    z = np.load(cache, allow_pickle=True)
    if list(z["files"]) == files:
        E = z["E"]; print("复用缓存", flush=True)
if E is None:
    from sv_onnx import SV
    sv = SV(name="r34")
    rows = []
    for i, c in enumerate(sel, 1):
        rows.append(sv.embed(c["path"]))
        if i % 100 == 0: print("  %d/%d" % (i, len(sel)), flush=True)
    E = np.array(rows, dtype=np.float32)
    np.savez(cache, E=E, files=np.array(files, dtype=object))

E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
from sklearn.cluster import AgglomerativeClustering
lab = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(E)
cnt = collections.Counter(lab)
print("簇大小", dict(cnt))
for c in sorted(cnt, key=lambda z: -cnt[z]):
    idx = [i for i in range(len(lab)) if lab[i] == c]
    f0s = [byf[files[i]]["f0"] for i in idx if byf.get(files[i], {}).get("f0")]
    print("\n=== 簇 %d  %d 条  F0 %0.0f" % (c, len(idx), np.median(f0s) if f0s else 0))
    step = max(1, len(idx) // 22)
    for i in idx[::step][:22]:
        print("   %7.1f %s" % (sel[i]["t0"], sel[i]["text"][:88]))
