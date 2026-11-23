"""1-NN + Z-norm 声纹归属（声纹验证标准做法）。

为什么需要 Z-norm：
  纯余弦下，某些模板天然对所有音频都更相似（"中心化"），会吸走大量样本。
  Z-norm 用一组背景音频估计每个模板的分数分布 mu/sigma，把分数标准化：
      s_norm(i) = (s(i) - mu_i) / sigma_i
  这样各模板的"吸力"被拉平，比较才公平。

用法：
  python sv_znorm.py --dir G:/_setup/castle_cues --bg auto --out out/cues_znorm.json
  python sv_znorm.py --list out/final_labels.jsonl --bg out_sv/cues1nn.json --out out/final_znorm.json
"""
import os, sys, json, argparse
import numpy as np

sys.path.insert(0, "G:/_setup")
from sv_onnx import SV, load16

REF = "G:/_setup/castle_fr_ref"
ROLE_OF = {
    "1_charles_normal": "Charles", "2_charles_soft": "Charles",
    "3_charles_excited": "Charles", "4_charles_angry": "Charles",
    "5_hooper_loud": "Thomas", "6_hooper_calm": "Thomas",
    "6b_hooper_scold": "Thomas", "7_hooper_begging": "Thomas",
}
EMO_OF = {k: k.split("_", 1)[1] for k in ROLE_OF}


def build(model="r34"):
    m = SV(model)
    T = {}
    for k in ROLE_OF:
        p = os.path.join(REF, k + ".wav")
        if os.path.exists(p):
            T[k] = m.embed(p)
    return m, T


def score_matrix(m, T, paths):
    keys = list(T)
    M = np.zeros((len(paths), len(keys)), dtype=np.float32)
    for i, p in enumerate(paths):
        try:
            e = m.embed(p)
        except Exception:
            M[i] = np.nan
            continue
        for j, k in enumerate(keys):
            M[i, j] = float(np.dot(e, T[k]))
    return keys, M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir")
    ap.add_argument("--list")
    ap.add_argument("--bg", default="auto", help="背景集：auto=用待测集自身；或一个 json（含 path）")
    ap.add_argument("--model", default="r34")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    m, T = build(a.model)
    print("模板 %d 档" % len(T), flush=True)

    items = []
    if a.list:
        for line in open(a.list, encoding="utf-8"):
            d = json.loads(line)
            items.append((d["path"], d))
    elif a.dir:
        for f in sorted(os.listdir(a.dir)):
            if f.endswith(".wav"):
                p = os.path.join(a.dir, f)
                items.append((p, {"path": p, "emotion": f[:-4]}))
    paths = [p for p, _ in items]
    print("待测 %d 条" % len(paths), flush=True)

    keys, M = score_matrix(m, T, paths)

    # 背景分数分布
    if a.bg == "auto":
        B = M
    else:
        bg = json.load(open(a.bg, encoding="utf-8"))
        bpaths = [r["path"] for r in bg][:400]
        _, B = score_matrix(m, T, bpaths)
    mu = np.nanmean(B, 0)
    sd = np.nanstd(B, 0) + 1e-9
    print("Z-norm mu:", {k: round(float(x), 3) for k, x in zip(keys, mu)})
    print("Z-norm sd:", {k: round(float(x), 3) for k, x in zip(keys, sd)})

    out = []
    for i, (p, meta) in enumerate(items):
        if np.isnan(M[i]).any():
            continue
        z = (M[i] - mu) / sd
        order = np.argsort(-z)
        k1, k2 = keys[order[0]], keys[order[1]]
        zc = max(z[j] for j, k in enumerate(keys) if ROLE_OF[k] == "Charles")
        zt = max(z[j] for j, k in enumerate(keys) if ROLE_OF[k] == "Thomas")
        rec = {
            "name": os.path.basename(p), "path": p,
            "top1": k1, "z1": round(float(z[order[0]]), 3),
            "top2": k2, "z2": round(float(z[order[1]]), 3),
            "role": ROLE_OF[k1], "emo": EMO_OF[k1],
            "margin": round(float(z[order[0]] - z[order[1]]), 3),
            "role_z": round(float(zc - zt), 3),
            "confident": bool(z[order[0]] >= 0.8 and (z[order[0]] - z[order[1]]) >= 0.25),
            "z": {k: round(float(v), 3) for k, v in zip(keys, z)},
            "cos": {k: round(float(v), 4) for k, v in zip(keys, M[i])},
        }
        rec.update({k: v for k, v in meta.items() if k != "path"})
        out.append(rec)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    import collections
    print("\n写 ->", a.out)
    print("角色分布:", dict(collections.Counter(r["role"] for r in out)))
    print("置信: %d/%d" % (sum(1 for r in out if r["confident"]), len(out)))
    for k, v in collections.Counter(r["top1"] for r in out).most_common():
        print("  %-20s %d" % (k, v))


if __name__ == "__main__":
    main()
