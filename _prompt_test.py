# -*- coding: utf-8 -*-
"""prompt 污染隔离测试：同一段音频，无 prompt / 污染 prompt / 干净 prompt 三档对比"""
import sys, time
import numpy as np, soundfile as sf
from faster_whisper import WhisperModel

SR = 32000
SRC = 'G:/_setup/_denoise_full/wonder_train_df3.wav'
x, _ = sf.read(SRC, dtype='float32', always_2d=True)
x = x.mean(1)
m = WhisperModel('G:/asr_models/faster-whisper-large-v3-turbo', device='cpu',
                 compute_type='int8', cpu_threads=10)
print('model loaded', flush=True)

WINDOWS = [(171.8, 196.7, '窗7'), (196.7, 221.1, '窗8'), (221.1, 243.4, '窗9')]
POLLUTED = 'This evening I am the one, you cannot see, but you want'
CLEAN = 'As the wind subsided, the leaves settled to stillness in the trees,'

for (a, b, nm) in WINDOWS:
    seg = x[int(a * SR):int(b * SR)]
    print('\n########## %s  %.1f-%.1f s ##########' % (nm, a, b), flush=True)
    for tag, kw in [('无prompt', dict()),
                    ('prompt=污染', dict(initial_prompt=POLLUTED)),
                    ('prompt=干净', dict(initial_prompt=CLEAN))]:
        t = time.time()
        segs, info = m.transcribe(seg, language='en', beam_size=5, word_timestamps=True,
                                  condition_on_previous_text=False, vad_filter=False, **kw)
        txt = ''.join(s.text for s in segs).strip()
        print('  [%-12s] %5.1fs | %s' % (tag, time.time() - t, txt[:200]), flush=True)
print('\nPROMPTTESTDONE', flush=True)
