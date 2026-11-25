# -*- coding: utf-8 -*-
"""把 c2_0191 两版的 F0 曲线画出来，直接看形状。

深色底（配合 dark theme），纵轴半音（相对各自句中位），横轴归一化时间。
上方子图：两版叠加；下方两个子图：各自单独 + 该版 F0 可跟踪段标灰。
"""
import os

import librosa
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
SID = "c2_0191"
SR16 = 16000
HOP = 80          # 5ms，画图要细
BG = "#161514"
FG = "#ece9e4"
GRID = "#33312d"
C_OLD = "#e0705a"
C_NEW = "#5fb3a1"


def track(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y16 = librosa.resample(y, orig_sr=sr, target_sr=SR16)
    f0, vflag, _ = librosa.pyin(y16, fmin=50, fmax=400, sr=SR16,
                                frame_length=1024, hop_length=HOP)
    ok = vflag & np.isfinite(f0)
    st = 12.0 * np.log2(np.clip(f0, 1e-6, None) / 100.0)
    st[~ok] = np.nan
    base = np.nanmedian(st)
    tn = np.arange(len(st)) / float(len(st) - 1)
    return tn, st - base, float(np.isfinite(st).mean()), len(y) / float(sr)


def main():
    d = {}
    for tag, sub in (("old", "_audio_ch123/out"), ("new", "_regen_final")):
        p = os.path.join(ROOT, sub, SID + ".wav")
        d[tag] = track(p)

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), facecolor=BG,
                             gridspec_kw=dict(height_ratios=[1.5, 1, 1]))
    for ax in axes:
        ax.set_facecolor(BG)
        ax.tick_params(colors=FG, labelsize=9)
        for s in ax.spines.values():
            s.set_color(GRID)
        ax.grid(True, color=GRID, lw=0.6, alpha=0.7)

    ax = axes[0]
    for tag, c in (("old", C_OLD), ("new", C_NEW)):
        tn, st, cov, dur = d[tag]
        ax.plot(tn, st, ".", ms=1.6, color=c, alpha=0.85,
                label="%s  (%.2fs, F0 cover %.0f%%)" % (tag, dur, cov * 100))
    ax.set_ylabel("pitch (st, rel. median)", color=FG, fontsize=10)
    ax.set_title("c2_0191  F0 contour — acceptance (old) vs three-tier-pause (new)",
                 color=FG, fontsize=12, pad=10)
    ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=9, loc="upper right")
    ax.set_xlim(0, 1)
    ax.set_ylim(-14, 14)

    for i, tag in enumerate(("old", "new"), start=1):
        ax = axes[i]
        tn, st, cov, dur = d[tag]
        c = C_OLD if tag == "old" else C_NEW
        ax.plot(tn, st, ".", ms=1.8, color=c)
        nan_mask = ~np.isfinite(st)
        ax.fill_between(tn, -14, 14, where=nan_mask, color="#2e2c29", alpha=0.75,
                        step="mid", label="no F0 tracked (%.0f%%)" % (100 - cov * 100))
        ax.set_ylabel(tag, color=c, fontsize=11, fontweight="bold")
        ax.set_xlim(0, 1)
        ax.set_ylim(-14, 14)
        ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=8, loc="lower right")

    axes[-1].set_xlabel("normalized time", color=FG, fontsize=10)
    fig.tight_layout()
    out = os.path.join(ROOT, "f0_c20191.png")
    fig.savefig(out, dpi=130, facecolor=BG)
    print("→", out)


if __name__ == "__main__":
    main()
