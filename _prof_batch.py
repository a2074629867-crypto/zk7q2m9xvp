# -*- coding: utf-8 -*-
"""按 (角色, 情绪) 批量测 F0 / 语速，用来验证「档位是否选对」。"""
import json
import os
import sys

import numpy as np
import soundfile as sf
import parselmouth

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
AUDIO = "G:/_setup/_audio_ch123/out"


def prof(p):
    s = parselmouth.Sound(p)
    f = s.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=600).selected_array["frequency"]
    v = f[f > 0]
    if len(v) < 5:
        return None
    return dict(f0=int(np.median(v)), p90=int(np.percentile(v, 90)),
                sd=int(np.std(v)), voiced=round(float((f > 0).mean()), 2),
                dur=round(s.get_total_duration(), 2))


def main():
    who = sys.argv[1] if len(sys.argv) > 1 else "Charles"
    emo = sys.argv[2] if len(sys.argv) > 2 else "紧张"
    rows = json.load(open("_dlg_final_v49.json", encoding="utf-8"))
    ids = [r["id"] for r in rows if r["who"] == who and r["emo"] == emo]
    print("== %s / %s  %d 条" % (who, emo, len(ids)))
    print("%-9s %5s %5s %5s %6s %6s %5s" % ("id", "F0", "p90", "sd", "voiced", "dur", "cls"))
    cls = {r["id"]: r["cls"] for r in rows}
    out = []
    for i in ids:
        p = os.path.join(AUDIO, i + ".wav")
        if not os.path.exists(p):
            continue
        q = prof(p)
        if not q:
            continue
        out.append((i, q))
        print("%-9s %5d %5d %5d %6.2f %6.2f %5s" %
              (i, q["f0"], q["p90"], q["sd"], q["voiced"], q["dur"], cls.get(i)))
    if out:
        v = [q["f0"] for _, q in out]
        print("\nF0 中位 %d  p25 %d  p75 %d  min %d  max %d" %
              (np.median(v), np.percentile(v, 25), np.percentile(v, 75), min(v), max(v)))


if __name__ == "__main__":
    main()
