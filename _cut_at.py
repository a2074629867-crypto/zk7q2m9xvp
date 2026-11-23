"""按给定起点裁掉开头（LEAD_REF），归一电平后回填，带备份。

用法：G:/Python310/python.exe _cut_at.py c1_0046=1.80 c1_0165=1.72
"""
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db

BAK = "G:/_setup/_bak_trimlead_1120b"
DIRS = ["G:/_setup/_audio_ch123/out", "G:/_setup/_audio_ch123/out_paused"]


def main():
    os.makedirs(BAK, exist_ok=True)
    log = {}
    p_json = "G:/_setup/_cut_at_log.json"
    if os.path.exists(p_json):
        log = json.load(open(p_json, encoding="utf-8"))
    for arg in sys.argv[1:]:
        rid, st = arg.split("=")
        st = float(st)
        src = "G:/_setup/_audio_ch123/out_paused/%s.wav" % rid
        y, sr = sf.read(src, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        s = int(st * sr)
        z = np.ascontiguousarray(y[s:].astype("float32"))
        k = int(0.015 * sr)
        if len(z) > 2 * k:
            z[:k] *= np.linspace(0, 1, k, dtype="float32")
        lv, _, _ = voiced_db(z, sr)
        if lv is not None:
            z = (z * 10 ** ((-24.0 - lv) / 20.0)).astype("float32")
            if float(np.abs(z).max()) > 0.97:
                z = (z * (0.97 / float(np.abs(z).max()))).astype("float32")
            lv, _, _ = voiced_db(z, sr)
        for d in DIRS:
            dst = os.path.join(d, rid + ".wav")
            if os.path.exists(dst):
                shutil.copy2(dst, os.path.join(BAK, os.path.basename(d) + "_" + rid + ".wav"))
            sf.write(dst, z, sr, subtype="PCM_16")
        log[rid] = {"cut_from": st, "dur": round(len(z) / sr, 3), "rms": round(float(lv), 2)}
        print("%-9s 裁 %.2f 起 -> dur %.2f rms %.2f" % (rid, st, len(z) / sr, lv))
    json.dump(log, open(p_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
