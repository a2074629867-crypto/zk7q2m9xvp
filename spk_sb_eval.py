"""speechbrain ECAPA-VoxCeleb 说话人分离度评测。

用途：判断两个法语童声在两个锚点集合上能否被分开。
"""
import os
import numpy as np
import torch
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HOME"] = "G:/_setup/models/hf"

from speechbrain.inference.speaker import EncoderClassifier  # noqa: E402

REF = "G:/_setup/castle_fr_ref"
FILES = [
    "1_charles_normal.wav", "2_charles_soft.wav", "3_charles_excited.wav", "4_charles_angry.wav",
    "5_hooper_loud.wav", "6_hooper_calm.wav", "6b_hooper_scold.wav", "7_hooper_begging.wav",
]


def wav16(p, sr=16000):
    x, s = sf.read(p, dtype="float32", always_2d=True)
    x = x.mean(1)
    if s != sr:
        g = gcd(int(s), int(sr))
        x = resample_poly(x, sr // g, s // g)
    return x


def main():
    clf = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="G:/_setup/models/sv_ecapa",
        run_opts={"device": "cpu"},
    )
    embs, names = {}, []
    for f in FILES:
        p = os.path.join(REF, f)
        if not os.path.exists(p):
            continue
        x = wav16(p)
        with torch.no_grad():
            e = clf.encode_batch(torch.from_numpy(x).unsqueeze(0)).squeeze().numpy()
        e = e / (np.linalg.norm(e) + 1e-9)
        embs[f] = e
        names.append(f)

    short = [x.split("_")[0] + ("C" if "charles" in x else "H") for x in names]
    print("=== 余弦相似度矩阵 ===")
    print("%-6s" % "" + "".join("%8s" % s for s in short))
    for a in names:
        row = "".join("%8.3f" % float(np.dot(embs[a], embs[b])) for b in names)
        print("%-6s" % (a.split("_")[0] + ("C" if "charles" in a else "H")) + row)

    C = [f for f in names if "charles" in f]
    H = [f for f in names if "hooper" in f]
    wi = [float(np.dot(embs[a], embs[b])) for i, a in enumerate(C) for b in C[i + 1:]]
    wh = [float(np.dot(embs[a], embs[b])) for i, a in enumerate(H) for b in H[i + 1:]]
    bc = [float(np.dot(embs[a], embs[b])) for a in C for b in H]
    within = wi + wh
    print("\n=== 分离度 ===")
    print("类内: min %.3f  med %.3f  max %.3f" % (min(within), np.median(within), max(within)))
    print("类间: min %.3f  med %.3f  max %.3f" % (min(bc), np.median(bc), max(bc)))
    print("分离度 = %+.3f => %s" % (min(bc) - max(within), "可分" if min(bc) > max(within) else "重叠"))

    print("\n=== 每个锚点归属 ===")
    ok = 0
    for f in names:
        mc = np.mean([np.dot(embs[f], embs[x]) for x in C if x != f] or [0])
        mh = np.mean([np.dot(embs[f], embs[x]) for x in H] or [0])
        truth = "charles" in f
        good = (truth == (mc > mh))
        ok += good
        print("%-24s C=%6.3f H=%6.3f margin%+7.3f  %s" % (f, mc, mh, mc - mh, "OK" if good else "WRONG"))
    print("归属正确 %d/%d" % (ok, len(names)))


if __name__ == "__main__":
    main()
