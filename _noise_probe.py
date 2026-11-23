# -*- coding: utf-8 -*-
"""诊断：逐文件能否分离出「真底噪」电平/纹理。"""
import glob
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, r'G:/_setup')
from room_tone import voice_floor_db, _frame_db

for f in sorted(glob.glob(r'G:/_setup/ch123_final/*.wav')):
    x, sr = sf.read(f, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    db = _frame_db(x, sr, fl=0.02, hop=0.01)
    med = float(np.median(db))
    # 候选底噪帧：比中位低 25dB 以上、且不是数字零
    q = db[(db < med - 25) & (db > -80)]
    vf = voice_floor_db(x, sr)
    zero = float((db < -90).mean() * 100)
    print('%-10s %5.2fs  med=%6.1f  vfloor=%6.1f  quiet_n=%4d  quiet_med=%7.1f  '
          'quiet_p10=%7.1f  zero=%4.0f%%'
          % (os.path.basename(f)[:-4], len(x) / sr, med, vf, len(q),
             np.median(q) if len(q) else np.nan,
             np.percentile(q, 10) if len(q) else np.nan, zero))
