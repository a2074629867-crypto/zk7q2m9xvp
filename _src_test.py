# -*- coding: utf-8 -*-
"""音源对比测试：同一段（窗7 171.8-196.7s），原音 / DF3 / notch 三档，
large-v3-turbo，无 initial_prompt，看谁不幻觉。
真值（small.en 整段）：leaves gliding down from their branches in a tranquil procession.
  Across the lake, faint light shone from a scattering of cottages nestled along the shoreline,
  each sending a long reflection quivering upon the surface of the water.
  A gentle gust of wind picked up, and Zoe was enchanted by the collective rustling of a billion leaves.
"""
import time
import numpy as np, soundfile as sf
from faster_whisper import WhisperModel

SR = 32000
SRCS = [('原音', 'G:/GPT-SoVITS/_dataset/wonder_train.wav'),
        ('DF3', 'G:/_setup/_denoise_full/wonder_train_df3.wav'),
        ('DF3+notch', 'G:/_setup/_denoise_full/wonder_train_df3_notch.wav')]
WINS = [(171.8, 196.7, '窗7'), (196.7, 221.1, '窗8')]

m = WhisperModel('G:/asr_models/faster-whisper-large-v3-turbo', device='cpu',
                 compute_type='int8', cpu_threads=10)
print('model loaded', flush=True)

for (a, b, nm) in WINS:
    print('\n########## %s  %.1f-%.1f s ##########' % (nm, a, b), flush=True)
    for tag, p in SRCS:
        x, _ = sf.read(p, dtype='float32', always_2d=True); x = x.mean(1)
        seg = x[int(a * SR):int(b * SR)]
        t = time.time()
        segs, info = m.transcribe(seg, language='en', beam_size=5, word_timestamps=True,
                                  condition_on_previous_text=False, vad_filter=False)
        txt = ''.join(s.text for s in segs).strip()
        print('  [%-10s] %5.1fs | %s' % (tag, time.time() - t, txt[:230]), flush=True)
print('\nSRCTESTDONE', flush=True)
