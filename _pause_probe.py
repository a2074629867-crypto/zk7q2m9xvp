# -*- coding: utf-8 -*-
"""探测：word_times 是否保留标点；proto 模式在真实单句上能插几处。"""
import os
import sys

os.environ.setdefault('HF_HOME', r'C:/Users/86178/.cache/huggingface')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
sys.path.insert(0, r'G:/_setup')

import json

import numpy as np
import soundfile as sf

from insert_pauses import plan_from_proto, tail_punct
from transplant_prosody2 import word_times

BANK = json.load(open(r'G:/_setup/pause_bank.json', encoding='utf-8'))
PROTO = {}
for k, v in BANK.items():
    PROTO[k] = float(v['median']) if isinstance(v, dict) else float(v)
# 与 insert_pauses.py 完全一致的兜底展开
c, p = PROTO.get(',', 0.55), PROTO.get('.', 0.85)
for k, frac in ((';', 0.85), (':', 0.75), ('!', 1.0), ('?', 1.0),
                ('\u2014', 0.75), ('\u2013', 0.75)):
    PROTO.setdefault(k, c + (p - c) * frac)

print('PROTO =', {k: round(v, 3) for k, v in PROTO.items()})
print()

for k in sys.argv[1:]:
    for base in ('G:/_setup/ch123_v5', 'G:/_setup/ch123', 'G:/_setup/ch123_final'):
        f = os.path.join(base, k + '.wav')
        if os.path.exists(f):
            break
    else:
        print('[miss]', k)
        continue
    rw = word_times(f)
    dur = sf.info(f).duration
    words = [(round(a, 2), round(b, 2), t) for a, b, t in rw]
    punct = [(i, tail_punct(w[2])) for i, w in enumerate(rw)]
    punct = [(i, p) for i, p in punct if p]
    plan = plan_from_proto(rw, PROTO, 1.0)
    print('%s  %.2fs  %d词  标点命中%d  → 插%d处' % (k, dur, len(rw), len(punct), len(plan)))
    print('   words:', words)
    print('   punct@:', punct)
    if plan:
        for t, add, w, tgt, cur in plan:
            print('   cut=%.2fs  %-14s 目标%.3f 现有%.3f 补%.3f' % (t, w, tgt, cur, add))
    else:
        print('   !! 无插入')
    print()
