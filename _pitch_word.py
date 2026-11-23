"""逐词对比：单词级 <pitch, semitones=9> 与 <rate, factor=0.7> 对目标词的影响。

基线 n0194_base.wav 与两个标注版同 seed / 同步数 / 同文本。
指标：目标词的 F0 中位数、时长、能量峰值，以及在全句突出度里的名次。
"""
import json
import os
import wave

import numpy as np
import parselmouth

D = "G:/_setup/_stress_test"
WORDS = "G:/_setup/_words_n0194.json"
TARGET = "slowly"


def rd(p):
    w = wave.open(p)
    sr = w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    if w.getnchannels() > 1:
        a = a.reshape(-1, w.getnchannels()).mean(axis=1)
    w.close()
    return a, sr


def word_feats(a, sr, s, e):
    seg = a[int(s * sr):int(e * sr)]
    if len(seg) < 800:
        return None
    p = parselmouth.Sound(seg, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=40.0, pitch_ceiling=400.0)
    v = p.selected_array["frequency"]
    v = v[v > 0]
    f0 = float(np.median(v)) if len(v) else 0.0
    rms = float(np.sqrt(np.mean(seg ** 2)) + 1e-12)
    return dict(f0=f0, dur=e - s, db=20 * np.log10(rms))


def rz(x):
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826 + 1e-9
    return (x - med) / mad


def main():
    tags = ["n0194_base", "n0194_pitch9", "n0194_rate07"]
    wmap = json.load(open(WORDS, encoding="utf-8"))
    print("%-13s %-9s %8s %8s %8s %8s" % ("版本", "目标词", "F0", "时长", "能量dB", "名次"))
    for t in tags:
        p = os.path.join(D, t + ".wav")
        if not os.path.exists(p):
            print(t, "missing")
            continue
        ws = wmap.get(t + ".wav")
        if not ws:
            print(t, "no words")
            continue
        a, sr = rd(p)
        rows = []
        for w in ws["words"]:
            f = word_feats(a, sr, w["start"], w["end"])
            if f:
                rows.append(dict(w=w["w"], **f))
        if not rows:
            continue
        f0s = rz([r["f0"] for r in rows])
        durs = rz([r["dur"] for r in rows])
        dbs = rz([r["db"] for r in rows])
        prom = f0s + durs + dbs
        idx = [i for i, r in enumerate(rows) if r["w"].lower().startswith(TARGET[:5])]
        if not idx:
            print("%-13s 目标词未找到 (%s)" % (t, " ".join(r["w"] for r in rows)))
            continue
        i = idx[0]
        rank = 1 + int((prom > prom[i]).sum())
        print("%-13s %-9s %8.1f %8.3f %8.1f %4d/%d"
              % (t, rows[i]["w"], rows[i]["f0"], rows[i]["dur"], rows[i]["db"], rank, len(rows)))


if __name__ == "__main__":
    main()
