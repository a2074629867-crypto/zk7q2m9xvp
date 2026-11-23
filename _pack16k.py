# -*- coding: utf-8 -*-
"""_pack16k.py —— 旁白 716 抽样转 16k 单声道并打包（给云端 EmphaClass 用）。

★ 旁白交付音频在 `_audio_ch123/out/`（955 = 对白 239 + 旁白 716），
  不是 `_mt_pick/N####`（那是另一套旧命名）。
"""
import os, sys, json, shutil, tarfile
import numpy as np
import soundfile as sf
from math import gcd
from scipy.signal import resample_poly

AUD = "G:/_setup/_audio_ch123/out"
LIST = "G:/_setup/_narr_check4/_narr_check.json"
OUT = "G:/_setup/_narr16k"
TAR = "G:/_setup/_narr16k.tar.gz"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120

units = [x["unit"] for x in json.load(open(LIST, encoding="utf-8"))]
step = max(1, len(units) // N)
sample = units[::step][:N]

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)
for u in sample:
    y, sr = sf.read(os.path.join(AUD, u + ".wav"), dtype="float32", always_2d=True)
    y = y.mean(1)
    if sr != 16000:
        g = gcd(int(sr), 16000)
        y = resample_poly(y, 16000 // g, sr // g).astype("float32")
    sf.write(os.path.join(OUT, u + ".wav"), np.clip(y, -1, 1), 16000, subtype="PCM_16")

with tarfile.open(TAR, "w:gz") as t:
    for f in sorted(os.listdir(OUT)):
        t.add(os.path.join(OUT, f), arcname=f)

print("打包 %d 条（全库 %d）-> %s (%.1f MB)" % (
    len(sample), len(units), TAR, os.path.getsize(TAR) / 1024 / 1024))
print("首尾:", sample[:3], sample[-2:])
