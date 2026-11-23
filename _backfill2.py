"""把选定的切段回填到 out / out_paused，带备份与电平校验。"""
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db

BAK = "G:/_setup/_bak_short_1120b"
DIRS = ["G:/_setup/_audio_ch123/out", "G:/_setup/_audio_ch123/out_paused"]

# id -> 已选定的切段
PICK = {
    "c1_0187": "_sweep/cs2/c1_0187_135.wav",
    "c3_0652": "_sweep/cs3/c3_0652_013.wav",
    "c3_0654": "_sweep/cs2/c3_0654_018.wav",
    "c3_0837": "_sweep/cs2/c3_0837_054.wav",
    "c2_0275": "_sweep/cs4/c2_0275_%03d.wav",
}


def main():
    os.makedirs(BAK, exist_ok=True)
    override = sys.argv[1] if len(sys.argv) > 1 else ""
    picks = dict(PICK)
    if override:
        k, v = override.split("=", 1)
        picks = {k: v}
    done = {}
    for rid, src in picks.items():
        if "%03d" in src:
            continue
        if not os.path.exists(src):
            print("缺文件 %s" % src)
            continue
        y, sr = sf.read(src, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y.astype("float32"))
        lv, _, _ = voiced_db(y, sr)
        if lv is None or abs(lv + 24.0) > 0.35:
            g = 10 ** ((-24.0 - lv) / 20.0) if lv else 1.0
            y = (y * g).astype("float32")
            if float(np.abs(y).max()) > 0.97:
                y = (y * (0.97 / float(np.abs(y).max()))).astype("float32")
            lv, _, _ = voiced_db(y, sr)
        for d in DIRS:
            dst = os.path.join(d, rid + ".wav")
            if os.path.exists(dst):
                shutil.copy2(dst, os.path.join(BAK, os.path.basename(d) + "_" + rid + ".wav"))
            sf.write(dst, y, sr, subtype="PCM_16")
        done[rid] = {"src": src, "dur": round(len(y) / sr, 3), "rms": round(float(lv), 2)}
        print("%-9s <- %-34s dur %.2f rms %.2f" % (rid, os.path.basename(src), len(y) / sr, lv))
    p = "G:/_setup/_backfill_short2.json"
    old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    old.update(done)
    json.dump(old, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("回填 %d 条，记录 %s" % (len(done), p))


if __name__ == "__main__":
    main()
