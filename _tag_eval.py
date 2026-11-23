# -*- coding: utf-8 -*-
"""比对 _tag_probe.py 各条件的时长 / F0 / RMS / md5。"""
import glob
import hashlib
import os
import wave

import numpy as np
import parselmouth

D = "G:/_setup/_seam/tag"
ORDER = ["base", "rate16", "rate06", "pitch_p5", "pitch_m5", "pitch_p12", "pause_ins", "volume"]


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
    # 静音结构
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
    inner = [g for g in gaps if g < dur - 0.2]
    return dict(dur=dur, f0=f0, rms=rms, md5=md5, ngap=len(gaps),
                sil=sum(gaps), big=[round(g, 2) for g in gaps if g > 0.3])


def main():
    base = None
    rows = []
    for tag in ORDER:
        p = os.path.join(D, tag + ".wav")
        if not os.path.exists(p) or os.path.getsize(p) < 1000:
            rows.append((tag, None))
            continue
        s = stats(p)
        if tag == "base":
            base = s
        rows.append((tag, s))

    if base is None:
        print("没有 baseline，无法比对")
        return

    print("%-10s %7s %7s %8s %8s %7s %6s  %s" %
          ("条件", "时长", "相对", "F0", "Δ半音", "RMS", "间隙", "md5"))
    print("-" * 88)
    for tag, s in rows:
        if s is None:
            print("%-10s  —— 无输出（被拒绝或失败）" % tag)
            continue
        ratio = s["dur"] / base["dur"] if base["dur"] else 0
        semi = 12 * np.log2(s["f0"] / base["f0"]) if (base["f0"] and s["f0"]) else 0
        mark = "  ← 与基线完全相同" if s["md5"] == base["md5"] else ""
        print("%-10s %6.2fs %6.2fx %7.1fHz %+7.2f %7.1fdB %6d  %s%s" %
              (tag, s["dur"], ratio, s["f0"], semi, s["rms"], s["ngap"], s["md5"], mark))

    print()
    print("基线大停顿:", base["big"])
    for tag, s in rows:
        if s and tag != "base" and s["big"] != base["big"]:
            print("%-10s 大停顿 %s  ← 变了" % (tag, s["big"]))


if __name__ == "__main__":
    main()
