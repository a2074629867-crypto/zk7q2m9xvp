# -*- coding: utf-8 -*-
"""_spg_cant.py —— 把各 take 的 can't 词尾放大成频谱图，用眼睛判 /t/ 有没有释放

为什么不用阈值硬算：`hf_tail` 在「can't I」连读里会把下一个 I 的起音算进来
（s46 因此在旧表里被量成 0.170、hfJump 3.78，看着像有爆破，其实那是 I 的起音）。
频谱图能直接看出：元音之后有没有一条 10~30ms 的宽带竖条（= 爆破），
还是一片平滑衰减（= 收成 /m/，也就是「cam」）。
"""
import json
import os
import sys

import matplotlib
import numpy as np
import parselmouth
import soundfile as sf

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = "G:/_setup/_spg"
os.makedirs(OUT, exist_ok=True)

P = {"now": "G:/_setup/_audio_ch123/out/c3_0853.wav"}
for pool in ("_gapfix3",):
    d = os.path.join("G:/_setup", pool, "c3_0853")
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.startswith("s") and f.endswith(".wav"):
                P[f[:-4]] = os.path.join(d, f)

import os as _os
RANK = _os.environ.get("RANK_JSON", "G:/_setup/_pool_rank.json")
rows = {r["tag"]: r for r in json.load(open(RANK, encoding="utf-8"))["rows"]}


def draw(tag, pad_l=0.12, pad_r=0.22):
    p = P[tag]
    spans = [(s[0], s[1], s[2]) for s in rows[tag]["spans"]]
    cant = [s for s in spans if s[0].startswith("cant")][0]
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    t0 = max(0.0, cant[1] - pad_l)
    t1 = min(len(y) / sr, cant[2] + pad_r)
    seg = y[int(t0 * sr):int(t1 * sr)]
    snd = parselmouth.Sound(seg, sampling_frequency=sr)
    spg = snd.to_spectrogram(0.005, 5000, 0.002, 20)
    S = np.flipud(spg.values)

    S = 10 * np.log10(S + 1e-12)
    fig, ax = plt.subplots(2, 1, figsize=(9, 4.2), sharex=True,
                           gridspec_kw={"height_ratios": [1, 2.4]})
    tt = t0 + np.arange(len(seg)) / sr
    ax[0].plot(tt, seg, lw=0.6, color="#1f6feb")
    ax[0].set_ylim(-0.6, 0.6)
    ax[0].axvline(cant[2], color="#da3633", lw=1.2, ls="--")
    ax[0].set_title("s46 参照" if tag == "s46" else tag, fontsize=10, loc="left")
    fmax = spg.y1 + spg.dy * (spg.ny - 1)
    ext = [t0, t1, 0, fmax]
    ax[1].imshow(S, aspect="auto", origin="lower", extent=ext,
                 cmap="magma", vmin=np.percentile(S, 20))
    ax[1].axvline(cant[2], color="#3fb950", lw=1.0, ls="--")
    ax[1].set_ylabel("Hz")
    ax[1].set_xlabel("s")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "%s_cant.png" % tag), dpi=110)
    plt.close(fig)
    return os.path.join(OUT, "%s_cant.png" % tag)


if __name__ == "__main__":
    tags = sys.argv[1:] or ["s46", "s60", "s52", "s51", "s54"]
    for t in tags:
        print(draw(t))
