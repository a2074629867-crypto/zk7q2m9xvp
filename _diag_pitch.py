# -*- coding: utf-8 -*-
"""参考 vs 成品 的 F0 / 音高轮廓对照 —— 判「紧张档是不是选错了参考」。"""
import json
import os
import sys

import numpy as np
import parselmouth
from parselmouth.praat import call

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def prof(p):
    s = parselmouth.Sound(p)
    pitch = s.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f = pitch.selected_array["frequency"]
    v = f[f > 0]
    if len(v) == 0:
        return dict(err="no voiced")
    inten = s.to_intensity(minimum_pitch=75)
    iv = inten.values[0]
    iv = iv[iv > 0]
    return dict(f0_med=int(np.median(v)), f0_p10=int(np.percentile(v, 10)),
                f0_p90=int(np.percentile(v, 90)), f0_sd=int(np.std(v)),
                f0_range=int(np.percentile(v, 95) - np.percentile(v, 5)),
                voiced=round(float((f > 0).mean()), 2),
                int_med=round(float(np.median(iv)), 1),
                dur=round(s.get_total_duration(), 2))


def main():
    d = json.load(open("_emo_refs_v2.json", encoding="utf-8"))
    print("=== Charles 参考音频 ===")
    print("%-8s %-30s %6s %6s %6s %6s %6s %7s" %
          ("档", "文件", "F0中", "p10", "p90", "sd", "range", "强度"))
    for k, v in d["Charles"].items():
        for r in v:
            p = r["path"].replace("\\", "/")
            if not os.path.exists(p):
                continue
            q = prof(p)
            print("%-8s %-30s %6s %6s %6s %6s %6s %7s" %
                  (k, os.path.basename(p), q.get("f0_med"), q.get("f0_p10"),
                   q.get("f0_p90"), q.get("f0_sd"), q.get("f0_range"), q.get("int_med")))

    print("\n=== 成品 ===")
    for f in ["_audio_ch123/out_deliver/c2_0299.wav",
              "_audio_ch123/out_deliver/c2_0291.wav",
              "_dn_tryC/vocals.wav"]:
        if os.path.exists(f):
            q = prof(f)
            print("%-46s %s" % (f.split("/")[-1], q))

    print("\n=== Charles 平静/紧张 基准（来自 _dlg_final_v49）===")
    rows = json.load(open("_dlg_final_v49.json", encoding="utf-8"))
    for r in rows:
        if r.get("who") == "Charles":
            print("%-8s %-4s %s" % (r["id"], r["cls"], r["emo"]))


if __name__ == "__main__":
    main()
