"""用多语种 X-Vector (WavLM-VoxCeleb) 评测两个法语童声的可分性。

输出：
  1. 8 个锚点两两余弦相似度矩阵
  2. 类内（同角色不同情绪）vs 类间（不同角色）分离度
  3. 每档锚点被分到哪一侧
"""
import os, sys, glob, json
import numpy as np
import torch
import soundfile as sf
import librosa

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from transformers import WavLMForXVector, AutoFeatureExtractor  # noqa: E402

MODEL = os.environ.get("SV_MODEL", "microsoft/wavlm-base-plus-sv")
CACHE = "G:/_setup/models/sv"
REF = "G:/_setup/castle_fr_ref"

FILES = [
    "1_charles_normal.wav", "2_charles_soft.wav", "3_charles_excited.wav", "4_charles_angry.wav",
    "5_hooper_loud.wav", "6_hooper_calm.wav", "6b_hooper_scold.wav", "7_hooper_begging.wav",
]


def load_wav(p, sr=16000):
    x, s = sf.read(p, dtype="float32", always_2d=True)
    x = x.mean(1)
    if s != sr:
        x = librosa.resample(x, orig_sr=s, target_sr=sr)
    return x


def main():
    fe = AutoFeatureExtractor.from_pretrained(MODEL, cache_dir=CACHE)
    model = WavLMForXVector.from_pretrained(MODEL, cache_dir=CACHE).eval()
    print("model:", MODEL)

    embs, names = {}, []
    for f in FILES:
        p = os.path.join(REF, f)
        if not os.path.exists(p):
            print("MISS", f)
            continue
        x = load_wav(p)
        inp = fe([x], sampling_rate=16000, return_tensors="pt", padding=True)
        with torch.no_grad():
            e = model(**inp).embeddings
        e = torch.nn.functional.normalize(e, dim=-1).squeeze().numpy()
        embs[f] = e
        names.append(f)

    n = len(names)
    print("\n=== 余弦相似度矩阵 ===")
    short = [x.split("_")[0] + ("C" if "charles" in x else "H") for x in names]
    print("%-8s" % "" + "".join("%8s" % s for s in short))
    for a in names:
        row = "".join("%8.3f" % float(np.dot(embs[a], embs[b])) for b in names)
        print("%-8s" % (a.split("_")[0] + ("C" if "charles" in a else "H")) + row)

    C = [f for f in names if "charles" in f]
    H = [f for f in names if "hooper" in f]
    ic = [float(np.dot(embs[a], embs[b])) for i, a in enumerate(C) for b in C[i + 1:]]
    hc = [float(np.dot(embs[a], embs[b])) for i, a in enumerate(H) for b in H[i + 1:]]
    bc = [float(np.dot(embs[a], embs[b])) for a in C for b in H]

    within = ic + hc
    print("\n=== 分离度 ===")
    print("类内(同角色): min %.3f  med %.3f  max %.3f" % (min(within), np.median(within), max(within)))
    print("类间(跨角色): min %.3f  med %.3f  max %.3f" % (min(bc), np.median(bc), max(bc)))
    gap = min(bc) - max(within)
    print("分离度(类间min - 类内max) = %+.3f  => %s" % (gap, "可分" if gap > 0 else "重叠"))

    # 阈值最优分类正确率
    thr_all = sorted(set(within + bc))
    best = (-1, 0)
    for t in thr_all:
        acc = (sum(1 for v in within if v > t) + sum(1 for v in bc if v <= t)) / len(within + bc)
        if acc > best[0]:
            best = (acc, t)
    print("最优阈值 %.3f 时，两两判定正确率 %.1f%%" % (best[1], 100 * best[0]))

    # 每个锚点用"与同角色均值 - 与异角色均值"的 margin
    print("\n=== 每个锚点归属 ===")
    print("%-24s %8s %8s %8s" % ("锚点", "与C均", "与H均", "margin"))
    ok = 0
    for f in names:
        mc = np.mean([np.dot(embs[f], embs[x]) for x in C if x != f] or [0])
        mh = np.mean([np.dot(embs[f], embs[x]) for x in H] or [0])
        truth = "charles" in f
        pred = mc > mh
        good = (truth == pred)
        ok += good
        print("%-24s %8.3f %8.3f %+8.3f  %s" % (f, mc, mh, mc - mh, "OK" if good else "WRONG"))
    print("归属正确 %d/%d" % (ok, n))

    json.dump({"model": MODEL, "emb": {k: v.tolist() for k, v in embs.items()},
               "within": within, "between": bc},
              open("G:/_setup/out_spk_wavlm.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
