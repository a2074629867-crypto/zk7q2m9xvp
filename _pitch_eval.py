"""对比 ±9 半音标签的实际音高变化。

用较宽的 pitch 范围（40-400Hz），因为基准音高约 75Hz，-9 半音会落到 45Hz 附近，
如果沿用 60Hz 下限，负向变化会被跟踪器直接丢弃，看起来"没变化"——这是上一轮的一个隐患。
"""
import glob
import os
import sys
import wave

import numpy as np
import parselmouth

D = "G:/_setup/_pitch_test"


def rd(p):
    w = wave.open(p)
    sr = w.getframerate()
    n = w.getnframes()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64) / 32768.0
    if w.getnchannels() > 1:
        a = a.reshape(-1, w.getnchannels()).mean(axis=1)
    w.close()
    return a, sr


def f0stats(a, sr):
    snd = parselmouth.Sound(a, sampling_frequency=sr)
    p = snd.to_pitch(time_step=0.01, pitch_floor=40.0, pitch_ceiling=400.0)
    v = p.selected_array["frequency"]
    v = v[v > 0]
    if not len(v):
        return dict(n=0)
    st = 12 * np.log2(v / 100.0)
    return dict(n=len(v), med=float(np.median(v)), mean=float(v.mean()),
                st_med=float(np.median(st)),
                p10=float(np.percentile(v, 10)), p90=float(np.percentile(v, 90)),
                st_p10=float(np.percentile(st, 10)), st_p90=float(np.percentile(st, 90)))


def main():
    files = sorted(glob.glob(os.path.join(D, "*.wav")))
    rows = {}
    for f in files:
        a, sr = rd(f)
        st = f0stats(a, sr)
        rows[os.path.basename(f)[:-4]] = dict(dur=len(a) / sr, **st)
    if not rows:
        print("no files")
        return
    print("%-12s %7s %7s %8s %8s %8s %8s" % ("tag", "dur", "F0med", "st_med", "p10", "p90", "voiced"))
    for k in sorted(rows):
        v = rows[k]
        print("%-12s %7.2f %7.1f %+8.2f %8.1f %8.1f %8d"
              % (k, v["dur"], v.get("med", 0), v.get("st_med", 0),
                 v.get("p10", 0), v.get("p90", 0), v.get("n", 0)))

    print("\n=== 相对同路径无标签基线的变化 ===")
    base = {"tts": rows.get("tts_p0"), "edit": rows.get("edit_p0")}
    for k in sorted(rows):
        if k.endswith("_p0"):
            continue
        pref = "tts" if k.startswith("tts") or k.startswith("c_tts") else "edit"
        b = base[pref]
        if not b or not b.get("n"):
            continue
        v = rows[k]
        dst = v["st_med"] - b["st_med"]
        dr = v["dur"] / b["dur"]
        print("%-12s vs %-8s  音高 %+6.2f 半音  时长 ×%.3f" % (k, pref, dst, dr))


if __name__ == "__main__":
    main()
