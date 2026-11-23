# -*- coding: utf-8 -*-
"""全片 embedding 缓存 + k 扫描 + 指定簇再拆（带文本样本）。"""
import json, os, sys, collections
import numpy as np
sys.path.insert(0, "G:/_setup")

cuedir = sys.argv[1]
kmax = int(sys.argv[2]) if len(sys.argv) > 2 else 8
sub = sys.argv[3] if len(sys.argv) > 3 else ""   # 形如 "5:0:2" = k5 的簇0 再拆2

d = json.load(open(os.path.join(cuedir, "cues.json"), encoding="utf-8"))
cs = d if isinstance(d, list) else d["cues"]
cs = [c for c in cs if c["dur"] >= 1.2 and not c.get("multi") and not c.get("sfx")]
files = [os.path.basename(c["path"]) for c in cs]
print("cue %d 条" % len(cs), flush=True)

cache = os.path.join(cuedir, "_E_all.npz")
E = None
if os.path.exists(cache):
    z = np.load(cache, allow_pickle=True)
    if list(z["files"]) == files:
        E = z["E"]; print("复用缓存", flush=True)
if E is None:
    from sv_onnx import SV
    sv = SV(name="r34")
    rows = []
    for i, c in enumerate(cs, 1):
        rows.append(sv.embed(c["path"]))
        if i % 150 == 0: print("  %d/%d" % (i, len(cs)), flush=True)
    E = np.array(rows, dtype=np.float32)
    np.savez(cache, E=E, files=np.array(files, dtype=object))
E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)

from sklearn.cluster import AgglomerativeClustering

def f0med(idx):
    v = [c.get("_f0") for c in idx] 
    return 0

def bands(lab, k):
    cnt = collections.Counter(lab)
    out = []
    for c in sorted(cnt, key=lambda z: -cnt[z]):
        idx = [i for i in range(len(lab)) if lab[i] == c]
        out.append((c, len(idx), idx))
    return out

print("\n%-3s %s" % ("k", "各簇条数"))
labs = {}
for k in range(2, kmax + 1):
    lab = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(E)
    labs[k] = lab
    print("%-3d %s" % (k, "  ".join("%d:%d" % (c, n) for c, n, _ in bands(lab, k))), flush=True)

if sub:
    k1, c1, k2 = [int(x) for x in sub.split(":")]
    lab = labs[k1]
    idx = [i for i in range(len(lab)) if lab[i] == c1]
    print("\n=== k=%d 簇 %d：%d 条，再拆 %d" % (k1, c1, len(idx), k2))
    E2 = E[idx]
    lab2 = AgglomerativeClustering(n_clusters=k2, metric="cosine", linkage="average").fit_predict(E2)
    cnt2 = collections.Counter(lab2)
    for c in sorted(cnt2, key=lambda z: -cnt2[z]):
        sub_idx = [idx[i] for i in range(len(idx)) if lab2[i] == c]
        print("\n--- 子簇 %d  %d 条" % (c, len(sub_idx)))
        step = max(1, len(sub_idx) // 20)
        for i in sub_idx[::step][:20]:
            print("   %7.1f %4.1fs %s" % (cs[i]["t0"], cs[i]["dur"], cs[i]["text"][:80]))
