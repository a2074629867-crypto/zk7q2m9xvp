# -*- coding: utf-8 -*-
"""c2_0191 逐词 F0：为什么耳朵听到「重音在 much」，而 rel_z 看不见。"""
import json, os, sys
import numpy as np
import soundfile as sf
import parselmouth

ID = "c2_0191"
old = {os.path.basename(k).rsplit(".", 1)[0]: v
       for k, v in json.load(open(r"G:\_setup\_wl_words.json", encoding="utf-8")).items()}
new = {os.path.basename(k).rsplit(".", 1)[0]: v
       for k, v in json.load(open(r"G:\_setup\_wl_regen1123.json", encoding="utf-8")).items()}


def f0_track(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    s = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr)
    p = s.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=500)
    return p, len(y) / float(sr)


def semis(f):
    return 12 * np.log2(f / 100.0)


def per_word(p, rec):
    out = []
    for w in rec["words"]:
        t0, t1 = float(w["start"]), float(w["end"])
        vals = []
        t = t0
        while t < t1:
            v = p.get_value_at_time(t)
            if v is not None and not np.isnan(v) and v > 0:
                vals.append(v)
            t += 0.01
        if len(vals) < 3:
            out.append((w["w"], None, None, None))
            continue
        a = np.array(vals)
        out.append((w["w"], float(semis(np.median(a))),
                    float(semis(np.percentile(a, 95))),
                    float(semis(a.max()) - semis(a.min()))))
    return out


for tag, rec, path in (("验收版", old[ID], r"G:\_setup\_audio_ch123\out\%s.wav" % ID),
                       ("三档版", new[ID], r"G:\_setup\_regen_final\%s.wav" % ID)):
    p, dur = f0_track(path)
    rows = per_word(p, rec)
    med = np.median([r[1] for r in rows if r[1] is not None])
    print("\n=== %s   全句 F0 中位 %.1f st(rel 100Hz) ===" % (tag, med))
    print("%-12s %8s %8s %8s %8s" % ("word", "med st", "p95 st", "range", "Δmed"))
    prev = None
    for w, m, q, rg in rows:
        if m is None:
            print("%-12s     --" % w)
            continue
        d = "" if prev is None else "%+7.2f" % (m - prev)
        star = ""
        if q - med >= 2.0:
            star = "  <<< 高出句内中位 %.1f st" % (q - med)
        print("%-12s %8.2f %8.2f %8.2f %8s%s" % (w, m, q, rg, d, star))
        prev = m
