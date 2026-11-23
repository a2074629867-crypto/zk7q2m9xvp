# -*- coding: utf-8 -*-
"""女性簇再拆：只用 2.5–8s 的干净句，k=2，打印样本文本。"""
import json, os, sys, collections
import numpy as np
sys.path.insert(0, "G:/_setup")
cuedir = "G:/MOVIE_DL/_cues_ay"
d = json.load(open(os.path.join(cuedir, "cues.json"), encoding="utf-8"))
cs = d if isinstance(d, list) else d["cues"]
z = np.load(os.path.join(cuedir, "_E_all.npz"), allow_pickle=True)
files = list(z["files"]); E = z["E"]
E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
idx_by_file = {f: i for i, f in enumerate(files)}
sel = [c for c in cs if 2.5 <= c["dur"] <= 8.0 and not c.get("multi") and not c.get("sfx")
       and os.path.basename(c["path"]) in idx_by_file]
rows = [idx_by_file[os.path.basename(c["path"])] for c in sel]
print("候选 %d 条" % len(sel), flush=True)
E2 = E[rows]
from sklearn.cluster import AgglomerativeClustering
for k in (2, 3):
    lab = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(E2)
    cnt = collections.Counter(lab)
    print("\n===== k=%d  %s" % (k, dict(cnt)))
    for c in sorted(cnt, key=lambda z: -cnt[z]):
        ix = [i for i in range(len(lab)) if lab[i] == c]
        print("\n--- 簇 %d  %d 条" % (c, len(ix)))
        step = max(1, len(ix) // 16)
        for i in ix[::step][:16]:
            print("   %7.1f %s" % (sel[i]["t0"], sel[i]["text"][:86]))
