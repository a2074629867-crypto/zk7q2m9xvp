# -*- coding: utf-8 -*-
"""解码矩阵测试：定位 large-v3-turbo 幻觉的真凶
真值（small.en 整段，171.8-196.7s）：
  leaves gliding down from their branches in a tranquil procession.
  Across the lake, faint light shone from a scattering of cottages nestled along the shoreline,
  each sending a long reflection quivering upon the surface of the water.
  A gentle gust of wind picked up, and Zoe was enchanted by the collective rustling of a billion leaves.
"""
import os, time
import numpy as np, soundfile as sf
from faster_whisper import WhisperModel

SR = 32000
SRC = 'G:/GPT-SoVITS/_dataset/wonder_train.wav'
x, _ = sf.read(SRC, dtype='float32', always_2d=True); x = x.mean(1)

TURBO = 'G:/asr_models/faster-whisper-large-v3-turbo'
MED = 'G:/asr_models/faster-whisper-medium.en'

CASES = [
    # (tag, model, ct, a, b, kwargs)
    ('turbo int8 25s coptF vadF', TURBO, 'int8', 171.8, 196.7, dict(condition_on_previous_text=False, vad_filter=False)),
    ('turbo f32  25s coptF vadF', TURBO, 'float32', 171.8, 196.7, dict(condition_on_previous_text=False, vad_filter=False)),
    ('turbo int8 25s coptT vadF', TURBO, 'int8', 171.8, 196.7, dict(condition_on_previous_text=True, vad_filter=False)),
    ('turbo int8 25s coptF vadT', TURBO, 'int8', 171.8, 196.7, dict(condition_on_previous_text=False, vad_filter=True)),
    ('meden int8 25s coptF vadF', MED, 'int8', 171.8, 196.7, dict(condition_on_previous_text=False, vad_filter=False)),
    ('turbo int8 70s coptT vadF', TURBO, 'int8', 160.0, 230.0, dict(condition_on_previous_text=True, vad_filter=False)),
    ('turbo f32  70s coptT vadF', TURBO, 'float32', 160.0, 230.0, dict(condition_on_previous_text=True, vad_filter=False)),
]

models = {}
for tag, mp, ct, a, b, kw in CASES:
    key = (mp, ct)
    if key not in models:
        t = time.time()
        models[key] = WhisperModel(mp, device='cpu', compute_type=ct, cpu_threads=10)
        print('[load] %s %s  %.1fs' % (os.path.basename(mp), ct, time.time() - t), flush=True)
    seg = x[int(a * SR):int(b * SR)]
    t = time.time()
    segs, info = models[key].transcribe(seg, language='en', beam_size=5,
                                        word_timestamps=True, **kw)
    txt = ''.join(s.text for s in segs).strip()
    print('\n[%-26s] %5.1fs (%.0f-%.0fs)' % (tag, time.time() - t, a, b), flush=True)
    print('   %s' % txt[:260], flush=True)

print('\nMATRIXDONE', flush=True)
