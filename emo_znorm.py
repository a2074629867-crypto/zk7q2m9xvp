"""情绪音色归属检测（Z-norm 版）。

模板库 = _emo_refs.json（每个角色每个情绪若干条干净 ref）
每条 ref 单独当一个模板，用自己的 mu/sigma 做 Z-norm，消除"吸力"差异。

用法：
  python emo_znorm.py --list G:/_setup/emo_bench/out/final_labels.jsonl \
                      --out G:/_setup/out_sv/final_emo_znorm.json
  python emo_znorm.py --list ... --bg cues     # 用电影 cue 做背景
"""
import os, sys, json, argparse
import numpy as np

sys.path.insert(0, "G:/_setup")
from sv_onnx import SV

LIB = "G:/_setup/_emo_refs.json"


def build(model="r34"):
    m = SV(model)
    lib = json.load(open(LIB, encoding="utf-8"))
    keys, mats = [], []
    for role, emos in lib.items():
        for emo, items in emos.items():
            for it in items:
                p = it["path"] if isinstance(it, dict) else it
                if not os.path.exists(p):
                    continue
                keys.append((role, emo, os.path.basename(p)))
                mats.append(m.embed(p))
    return m, keys, np.array(mats)


def smatrix(m, mats, paths):
    M = np.full((len(paths), len(mats)), np.nan, dtype=np.float32)
    for i, p in enumerate(paths):
        try:
            e = m.embed(p)
        except Exception:
            continue
        M[i] = mats @ e
    return M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--bg", default="self", help="self | cues")
    ap.add_argument("--model", default="r34")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    m, keys, mats = build(a.model)
    print("模板 %d 条：" % len(keys))
    import collections
    c = collections.Counter((k[0], k[1]) for k in keys)
    for k, v in sorted(c.items()):
        print("  %-8s %-9s %d" % (k[0], k[1], v))

    items = [json.loads(l) for l in open(a.list, encoding="utf-8")]
    paths = [d["path"] for d in items]
    print("待测 %d 条" % len(paths), flush=True)
    M = smatrix(m, mats, paths)

    if a.bg == "cues":
        bg = json.load(open("G:/_setup/out_sv/cues_znorm2.json", encoding="utf-8"))
        bp = [r["path"] for r in bg]
        B = smatrix(m, mats, bp)
    else:
        B = M
    mu = np.nanmean(B, 0)
    sd = np.nanstd(B, 0) + 1e-9

    out = []
    for i, d in enumerate(items):
        if np.isnan(M[i]).any():
            continue
        z = (M[i] - mu) / sd
        order = np.argsort(-z)
        k1, k2 = keys[order[0]], keys[order[1]]
        zc = max(z[j] for j, k in enumerate(keys) if k[0] == "Charles")
        zt = max(z[j] for j, k in enumerate(keys) if k[0] == "Thomas")
        rec = {
            "name": os.path.basename(d["path"]),
            "target_emo": d.get("emotion"),
            "top1": "%s/%s" % (k1[0], k1[1]), "ref1": k1[2], "z1": round(float(z[order[0]]), 3),
            "top2": "%s/%s" % (k2[0], k2[1]), "ref2": k2[2], "z2": round(float(z[order[1]]), 3),
            "role": k1[0], "emo": k1[1],
            "margin": round(float(z[order[0]] - z[order[1]]), 3),
            "role_z": round(float(zc - zt), 3),
            "confident": bool(z[order[0]] >= 0.7 and (z[order[0]] - z[order[1]]) >= 0.2),
            "z": {"%s/%s" % (k[0], k[1]): round(float(v), 2) for k, v in zip(keys, z)},
            "cos": {"%s/%s" % (k[0], k[1]): round(float(v), 3) for k, v in zip(keys, M[i])},
        }
        out.append(rec)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    import collections
    print("\n写 ->", a.out)
    print("角色:", dict(collections.Counter(r["role"] for r in out)))
    print("top1 档:", dict(collections.Counter("%s/%s" % (r["role"], r["emo"]) for r in out).most_common()))
    print("置信: %d/%d" % (sum(1 for r in out if r["confident"]), len(out)))
    # 角色一致性（成品应全是 Charles 或全是一个角色，视角色而定）
    ch = sum(1 for r in out if r["role"] == "Charles")
    print("Charles: %d  Thomas: %d" % (ch, len(out) - ch))


if __name__ == "__main__":
    main()
