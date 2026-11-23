"""检测每个锚点内部是否混了两个人。

方法：把每档锚点切成 1.5s 窗口（0.75s 步进），逐窗提 X-Vector，做层次聚类，
看是否稳定分裂成两簇、两簇中心距离是否大于簇内距离。
"""
import os, json
import numpy as np
import torch
import soundfile as sf
from scipy.signal import resample_poly
from transformers import WavLMForXVector, AutoFeatureExtractor

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
MODEL = "microsoft/wavlm-base-plus-sv"
CACHE = "G:/_setup/models/sv"
REF = "G:/_setup/castle_fr_ref"

FILES = [
    "1_charles_normal.wav", "2_charles_soft.wav", "3_charles_excited.wav", "4_charles_angry.wav",
    "5_hooper_loud.wav", "6_hooper_calm.wav", "6b_hooper_scold.wav", "7_hooper_begging.wav",
]


def wav(p, sr=16000):
    x, s = sf.read(p, dtype="float32", always_2d=True)
    x = x.mean(1)
    if s != sr:
        from math import gcd
        g = gcd(int(s), int(sr))
        x = resample_poly(x, sr // g, s // g)
    return x


def main():
    fe = AutoFeatureExtractor.from_pretrained(MODEL, cache_dir=CACHE)
    model = WavLMForXVector.from_pretrained(MODEL, cache_dir=CACHE).eval()

    print("%-24s %5s %6s %6s %6s  %s" % ("锚点", "窗数", "内部min", "内部med", "跨组距离", "是否混人"))
    report = {}
    for f in FILES:
        p = os.path.join(REF, f)
        if not os.path.exists(p):
            continue
        x = wav(p)
        win, hop = int(1.5 * 16000), int(0.75 * 16000)
        segs = [x[i:i + win] for i in range(0, max(1, len(x) - win + 1), hop)]
        segs = [s for s in segs if len(s) > 0.6 * win and np.abs(s).max() > 0.01]
        if len(segs) < 3:
            print("%-24s %5d  数据不足" % (f, len(segs)))
            continue
        inp = fe(segs, sampling_rate=16000, return_tensors="pt", padding=True)
        with torch.no_grad():
            e = model(**inp).embeddings
        e = torch.nn.functional.normalize(e, dim=-1).numpy()
        S = e @ e.T
        iu = np.triu_indices(len(segs), 1)
        iv = S[iu]
        # 取相似度最低的 1/4 对当"疑似跨人"
        thr = np.percentile(iv, 25)
        lo = iv[iv <= thr]
        # 用最低对建立两组中心
        i, j = iu[0][np.argmin(iv)], iu[1][np.argmin(iv)]
        c1, c2 = e[i], e[j]
        for _ in range(20):
            d1, d2 = e @ c1, e @ c2
            a = np.where(d1 >= d2)[0]
            b = np.where(d1 < d2)[0]
            if len(a) == 0 or len(b) == 0:
                break
            c1, c2 = e[a].mean(0), e[b].mean(0)
        cross = float(c1 @ c2 / (np.linalg.norm(c1) * np.linalg.norm(c2) + 1e-9))
        # 组内一致度
        def consist(idx):
            if len(idx) < 2:
                return 1.0
            v = [e[a] @ e[b] for x, a in enumerate(idx) for b in idx[x + 1:]]
            return float(np.median(v))
        c_in = min(consist(a), consist(b))
        ratio = len(a) / len(e)
        mixed = cross < c_in - 0.03 and 0.2 < ratio < 0.8
        print("%-24s %5d %6.3f %6.3f %6.3f/%6.3f  %s" % (
            f, len(segs), iv.min(), np.median(iv), cross, c_in, "★疑似混人" if mixed else ""))
        report[f] = {"n": len(segs), "min": float(iv.min()), "med": float(np.median(iv)),
                     "cross": cross, "within": c_in, "mixed": bool(mixed),
                     "split": [len(a), len(b)]}
    json.dump(report, open("G:/_setup/out_anchor_purity.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
