# -*- coding: utf-8 -*-
"""全库体检：原文标点 → ASR 找回率；底噪可测性。"""
import glob
import json
import os
import re
import sys

os.environ.setdefault('HF_HOME', r'C:/Users/86178/.cache/huggingface')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
sys.path.insert(0, r'G:/_setup')

import numpy as np
import soundfile as sf

from ch123_plan import INNER, PLAN
from insert_pauses import plan_from_proto, tail_punct
from room_tone import _frame_db
from transplant_prosody2 import word_times

BANK = json.load(open(r'G:/_setup/pause_bank.json', encoding='utf-8'))
PROTO = {k: float(v['median']) if isinstance(v, dict) else float(v)
         for k, v in BANK.items()}
c, p = PROTO.get(',', 0.55), PROTO.get('.', 0.85)
for k, frac in ((';', 0.85), (':', 0.75), ('!', 1.0), ('?', 1.0),
                ('\u2014', 0.75), ('\u2013', 0.75)):
    PROTO.setdefault(k, c + (p - c) * frac)

TEXT = {'L%03d' % i: t for i, _, _, t in PLAN}
TEXT.update({'I%02d' % i: t for i, (_, _, _, t) in enumerate(INNER)})


def expect_inner(text):
    """原文里句内（非句末）标点数：逗号等，句末标点不算。"""
    t = text.strip()
    # 找到所有标点位置，排除最后一个字符处的句末标点
    hits = []
    for m in re.finditer(r'[,;:!?\u2014\u2013]|(?<!\.)\.(?!\.)', t):
        if m.end() >= len(t.rstrip('.!?"\')')):
            continue
        hits.append(m.group(0))
    return len(hits), hits


rows = []
noise = []
for f in sorted(glob.glob(r'G:/_setup/ch123_final/*.wav')):
    k = os.path.basename(f)[:-4]
    if k not in TEXT:
        continue
    x, sr = sf.read(f, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    db = _frame_db(x, sr, fl=0.02, hop=0.01)
    med = float(np.median(db))
    q = db[(db < med - 25) & (db > -80)]
    nq = float(np.median(q)) if len(q) else float('nan')

    rw = word_times(f)
    got = [(i, tail_punct(w[2])) for i, w in enumerate(rw)]
    got = [(i, pn) for i, pn in got if pn and i < len(rw) - 1]   # 句末不算
    plan = plan_from_proto(rw, PROTO, 1.0)
    nexp, hits = expect_inner(TEXT[k])
    rows.append(dict(k=k, dur=len(x) / sr, words=len(rw), exp=nexp,
                     hit=len(got), plan=len(plan), add=sum(p[1] for p in plan),
                     hits=hits, got=[p for _, p in got], med=med, noise=nq,
                     nq=len(q)))
    noise.append((k, nq, len(q), med))
    print('%-5s %5.2fs %2d词 原文句内标点%d  ASR找回%d  规划插入%d  +%.2fs | med%6.1f noise%7.1f(n=%d)'
          % (k, len(x) / sr, len(rw), nexp, len(got), len(plan),
             sum(p[1] for p in plan), med, nq, len(q)), flush=True)

json.dump(rows, open(r'G:/_setup/_pause_audit.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)

print('\n===== 汇总 =====')
E = sum(r['exp'] for r in rows)
H = sum(r['hit'] for r in rows)
P = sum(r['plan'] for r in rows)
print('原文句内标点 %d 处，ASR 找回 %d 处（%.1f%%），实际规划插入 %d 处' % (E, H, 100 * H / E, P))
miss = [r['k'] for r in rows if r['exp'] > 0 and r['hit'] == 0]
print('完全丢失标点的条目 %d 条: %s' % (len(miss), ' '.join(miss)))
wrong = [r for r in rows if r['exp'] != r['hit']]
print('数量不符 %d 条' % len(wrong))
nz = [r for r in rows if r['nq'] < 10]
print('底噪不可测(<10帧) %d 条: %s' % (len(nz), ' '.join(r['k'] for r in nz)))
vals = np.array([r['noise'] for r in rows if r['nq'] >= 10])
print('可测底噪 n=%d  min%.1f p25%.1f 中位%.1f p75%.1f max%.1f 跨度%.1fdB'
      % (len(vals), vals.min(), np.percentile(vals, 25), np.median(vals),
         np.percentile(vals, 75), vals.max(), vals.max() - vals.min()))
