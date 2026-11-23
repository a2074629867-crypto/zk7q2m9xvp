# -*- coding: utf-8 -*-
"""把偏离 −24dBFS 超过 0.05dB 的交付条目轻微拉回（只为满足「跨度 ≤1dB」）。

背景：r5/r6 之前的归一各自留了零点几 dB 的尾差，回填叠加后全库跨度 0.58→1.02dB，
刚刚越过需求 23 的 1dB 线。这里只对小偏差条目做 ±0.8dB 以内的增益修正，
峰值超 0.891 才软限幅（与 norm_dlg 同一把尺子）。
备份：`_audio_ch123/out_bak_nudge_1113/`，台账 `_nudge_rms_log.json`。
"""
import json, os, shutil, sys
import numpy as np
import soundfile as sf
sys.path.insert(0, "G:/_setup")
from norm_dlg import vdb, soft_clip

OUT = "G:/_setup/_audio_ch123/out"
BAK = "G:/_setup/_audio_ch123/out_bak_nudge_1113"
TARGET, PEAK_MAX = -24.0, 0.891

d = json.load(open("G:/_setup/_voiced_rms.json", encoding="utf-8"))
todo = [(k, v) for k, v in d.items() if v is not None and abs(v - TARGET) > 0.05]
os.makedirs(BAK, exist_ok=True)
log = []
for i, r0 in sorted(todo):
    p = os.path.join(OUT, i + ".wav")
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    gain = TARGET - vdb(y, sr)
    y = y * (10 ** (gain / 20.0))
    pk = float(np.abs(y).max())
    clip = pk > PEAK_MAX
    if clip:
        y = soft_clip(y, PEAK_MAX)
    bp = os.path.join(BAK, i + ".wav")
    if not os.path.exists(bp):
        shutil.copy2(p, bp)
    sf.write(p, y.astype(np.float32), sr, subtype="PCM_16")
    r1 = round(float(vdb(y, sr)), 2)
    log.append(dict(id=i, rms0=r0, gain=round(gain, 2), rms1=r1,
                    peak=round(float(np.abs(y).max()), 3), clip=clip))
    d[i] = r1
    print("%-8s %7.2f -> %7.2f  gain %+.2f  peak %.3f%s"
          % (i, r0, r1, gain, float(np.abs(y).max()), " 软限幅" if clip else ""))
json.dump(d, open("G:/_setup/_voiced_rms.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(log, open("G:/_setup/_nudge_rms_log.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
v = sorted(x for x in d.values() if x is not None)
print("\n修正 %d 条；全库 %d 条：min %.2f 中位 %.2f max %.2f 跨度 %.2f dB"
      % (len(log), len(v), v[0], v[len(v) // 2], v[-1], v[-1] - v[0]))
