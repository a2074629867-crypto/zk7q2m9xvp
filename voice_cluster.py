# -*- coding: utf-8 -*-
"""无监督找人声：一部片里到底有几种人、各多少条。

用途：冷启动补角色音色。现有模板库只有两个角色时，1-NN 会把成年人的
声音硬塞进这两个桶（实测 257 条全被分成 Thomas 193 / Charles 64，一个
"其他人"都没有）。所以先不谈角色，只做两件事：

  1) 用声纹 embedding 做余弦聚类 → 有几簇
  2) 每簇报中位 F0 → 男声 / 女声 / 童声

簇的命名仍要人读文本确认（"Papa" 是孩子叫爸爸）。这步只负责把候选
范围从 257 条压到每簇十几条。

用法:
  python voice_cluster.py --dir _emo_auto/cues --out out/voice_cluster.json
"""
import argparse
import collections
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from sv_onnx import SV


def read_wav(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return a.mean(axis=1), sr


def median_f0(p, fmin=60, fmax=450):
    a, sr = read_wav(p)
    if len(a) < sr * 0.2:
        return 0.0
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=fmin, pitch_ceiling=fmax)
    f = pit.selected_array["frequency"]
    f = f[f > 0]
    return float(np.median(f)) if len(f) else 0.0


def vocal_band(f0):
    """按中位 F0 粗判声部。成人男 ~100-145，成人女 ~175-225，儿童 ~235-320。
    重叠区（145-175 / 225-240）标「界」不硬分。"""
    if f0 <= 0:
        return "?"
    if f0 < 145:
        return "成年男"
    if f0 < 175:
        return "界(男/女)"
    if f0 < 225:
        return "成年女"
    if f0 < 240:
        return "界(女/童)"
    return "儿童"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default="out/voice_cluster.json")
    ap.add_argument("--kmax", type=int, default=6)
    ap.add_argument("--model", default="r34")
    a = ap.parse_args()

    from chain_check import EmoVoice
    m = EmoVoice(model=a.model).m

    files = sorted(f for f in os.listdir(a.dir) if f.lower().endswith(".wav"))
    print("cue %d 条" % len(files), flush=True)

    emb, rows = [], []
    for i, f in enumerate(files, 1):
        p = os.path.join(a.dir, f)
        emb.append(m.embed(p))
        rows.append({"id": f.split("_")[0], "file": f, "f0": round(median_f0(p), 1)})
        if i % 40 == 0:
            print("  提特征 %d/%d" % (i, len(files)), flush=True)

    E = np.array(emb, dtype=np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    for r, e in zip(rows, E):
        r["emb"] = e.tolist()

    print("\n%-4s %-6s %s" % ("k", "条数", "各簇 (条数 / F0中位 / 声部)"))
    best = {}
    for k in range(2, a.kmax + 1):
        from sklearn.cluster import AgglomerativeClustering
        lab = AgglomerativeClustering(n_clusters=k, metric="cosine",
                                      linkage="average").fit_predict(E)
        sizes = collections.Counter(lab)
        parts = []
        for c in sorted(sizes, key=lambda x: -sizes[x]):
            idx = [i for i in range(len(lab)) if lab[i] == c]
            f0 = np.median([rows[i]["f0"] for i in idx if rows[i]["f0"] > 0])
            parts.append("%d/%0.0fHz/%s" % (sizes[c], f0, vocal_band(f0)))
        print("%-4d %-6d %s" % (k, len(files), "  ".join(parts)))
        best[k] = lab

    k = int(os.environ.get("K", 4))
    lab = best[k]
    for r, c in zip(rows, lab):
        r["cl"] = int(c)
        r.pop("emb")

    print("\n=== k=%d 每簇细节 ===" % k)
    for c in sorted(set(lab)):
        idx = [i for i in range(len(lab)) if lab[i] == c]
        f0s = [rows[i]["f0"] for i in idx if rows[i]["f0"] > 0]
        ids = [rows[i]["id"] for i in idx]
        print("\n簇 %d：%d 条  F0 %0.0f–%0.0f（中位 %0.0f）%s" % (
            c, len(idx), min(f0s), max(f0s), np.median(f0s), vocal_band(np.median(f0s))))
        print("  " + " ".join(ids[:14]))

    json.dump({"k": k, "rows": rows}, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写 -> %s" % a.out)


if __name__ == "__main__":
    main()
