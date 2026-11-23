# -*- coding: utf-8 -*-
"""验证 small.en 整段的成功配方（vad_filter=True + condition_on_previous_text=True）
能否救活 large-v3-turbo / medium.en。

做法：在 140-440s 的 300s 长窗上跑（内含争议区 170-200s），对比三种模型的输出。
真值参考（small.en 整段，170-200s）：
  A thick wall of trees wrapped around the perimeter,
  leaves gliding down from their branches in a tranquil procession.
  Across the lake, faint light shone from a scattering of cottages nestled along the shoreline,
  each sending a long reflection quivering upon the surface of the water.
  A gentle gust of wind picked up, and Zoe was enchanted by the collective rustling of a billion leaves.
  Like a beautiful rousing whisper.
"""
import time
import numpy as np, soundfile as sf
from faster_whisper import WhisperModel

SRC = 'G:/GPT-SoVITS/_dataset/wonder_train.wav'
TURBO = 'G:/asr_models/faster-whisper-large-v3-turbo'
MED = 'G:/asr_models/faster-whisper-medium.en'
SMALL = 'Systran/faster-whisper-small.en'
A, B = 140.0, 440.0

x, _ = sf.read(SRC, dtype='float32', always_2d=True); x = x.mean(1)
seg = x[int(A * 32000):int(B * 32000)]

CASES = [('turbo  vadT coptT', TURBO, 'int8'),
         ('meden  vadT coptT', MED, 'int8'),
         ('small  vadT coptT', SMALL, 'int8'),
         ('turbo  vadF coptT', TURBO, 'int8')]

for tag, mp, ct in CASES:
    kw = dict(vad_filter=True, condition_on_previous_text=True)
    if tag.endswith('vadF coptT'):
        kw['vad_filter'] = False
    t = time.time()
    m = WhisperModel(mp, device='cpu', compute_type=ct, cpu_threads=10)
    ld = time.time() - t
    t = time.time()
    segs, info = m.transcribe(seg, language='en', beam_size=5, word_timestamps=True, **kw)
    txt = ' '.join(s.text.strip() for s in segs).strip()
    # 只打印 170-200s 区间的词
    print('\n===== %s  (load %.0fs, transcribe %.0fs) =====' % (tag, ld, time.time() - t), flush=True)
    print('  [全窗首200字] %s' % txt[:200], flush=True)
    buf = []
    for s in segs:
        for w in (s.words or []):
            gs = A + float(w.start); ge = A + float(w.end)
            if ge < 168 or gs > 200: continue
            buf.append(w.word.strip())
    print('  [168-200s 段] %s' % ' '.join(buf), flush=True)
    del m

print('\nCONFIGDONE', flush=True)
