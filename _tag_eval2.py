# -*- coding: utf-8 -*-
"""通用：扫描 _seam/tag 下的 wav，与指定 baseline 比对时长 / F0 / RMS / 间隙 / md5。"""
import glob
import hashlib
import os
import sys
import wave

import numpy as np
import parselmouth

D = "G:/_setup/_seam/tag"


def rd(p):
    w = wave.open(p)
    sr, n = w.getframerate(), w.getnframes()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64) / 32768.0
    w.close()
    return a, sr


def stats(p):
    a, sr = rd(p)
    dur = len(a) / sr
    rms = 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-12)
    snd = parselmouth.Sound(a, sampling_frequency=sr)
    pit = snd.to_pitch(time_step=0.01, pitch_floor=60.0, pitch_ceiling=400.0)
    v = pit.selected_array["frequency"]
    v = v[v > 0]
    f0 = float(np.median(v)) if len(v) else 0.0
    md5 = hashlib.md5(open(p, "rb").read()).hexdigest()[:10]
    hop = max(1, int(0.01 * sr))
    k = len(a) // hop
    e = np.sqrt(np.mean(a[:k * hop].reshape(k, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(e + 1e-12)
    sil = db < -40.0
    gaps = []
    i = 0
    while i < len(sil):
        if sil[i]:
            j = i
            while j < len(sil) and sil[j]:
                j += 1
            if (j - i) * 0.01 >= 0.06:
                gaps.append((j - i) * 0.01)
            i = j
        else:
            i += 1
    return dict(dur=dur, f0=f0, rms=rms, md5=md5, ngap=len(gaps),
                sil=sum(gaps), big=[round(g, 2) for g in gaps if g > 0.3])


def main():
    base_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(D, "tts_base.wav")
    tags = sys.argv[2:] if len(sys.argv) > 2 else None
    base = stats(base_path)
    print("baseline = %s  时长 %.2fs  F0 %.1fHz  RMS %.1fdB  大停顿 %s"
          % (os.path.basename(base_path), base["dur"], base["f0"], base["rms"], base["big"]))
    print()
    print("%-14s %7s %7s %8s %8s %8s %6s  %s" %
          ("条件", "时长", "相对", "F0", "Δ半音", "RMS", "间隙", "md5"))
    print("-" * 92)
    files = sorted(glob.glob(os.path.join(D, "*.wav")))
    for p in files:
        tag = os.path.basename(p)[:-4]
        if tags and tag not in tags:
            continue
        if os.path.abspath(p) == os.path.abspath(base_path):
            continue
        if os.path.getsize(p) < 1000:
            print("%-14s  —— 无输出" % tag)
            continue
        s = stats(p)
        ratio = s["dur"] / base["dur"]
        semi = 12 * np.log2(s["f0"] / base["f0"]) if (base["f0"] and s["f0"]) else 0
        mark = "  ← 与基线逐字节相同" if s["md5"] == base["md5"] else ""
        print("%-14s %6.2fs %6.2fx %7.1fHz %+7.2f %7.1fdB %6d  %s%s" %
              (tag, s["dur"], ratio, s["f0"], semi, s["rms"], s["ngap"], s["md5"], mark))
        if s["big"] != base["big"]:
            print("%-14s   大停顿 %s" % ("", s["big"]))


if __name__ == "__main__":
    main()
