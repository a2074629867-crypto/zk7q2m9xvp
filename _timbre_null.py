# -*- coding: utf-8 -*-
"""_timbre_null.py —— 段间声纹相似度的零分布对照

问题：ch123_segcheck 对短段“循环补长到 2s”后再提嵌入。
旁白单段常只有 0.3~1.0s，补长会破坏说话人信息 ⇒ 0.55 阈值可能根本不适用。

做法：取 N 条旁白，抽出所有段；
  within = 同一条内部的段间相似度（应该最像 = 同一人同一句）
  between = 不同条之间（同一 voice，但不同句）
若 within ≈ between ⇒ 这个指标在旁白上无区分力，不能当验收口径。
"""
import os, sys, json, itertools
import numpy as np

sys.path.insert(0, 'G:/_setup')
import ch123_segcheck as CS

AUD = 'G:/_setup/_audio_ch123/out'
N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
units = [x['unit'] for x in json.load(open('G:/_setup/_narr_check4/_narr_check.json', encoding='utf-8'))]
step = max(1, len(units) // N)
sample = units[::step][:N]

os.makedirs('_segchk_null', exist_ok=True)
CS.SEGDIR = '_segchk_null'

embs = {}
durs = {}
for u in sample:
    p = os.path.join(AUD, u + '.wav')
    if not os.path.exists(p):
        continue
    a, sr = CS.read_wav(p)
    segs = CS.split_at_silence(a, sr)
    lst = []
    for i, (s0, s1) in enumerate(segs):
        seg = a[int(s0*sr):int(s1*sr)]
        d = len(seg)/sr
        fp = os.path.join('_segchk_null', '%s_p%d.wav' % (u, i))
        CS.write_wav(fp, np.tile(seg, int(np.ceil(CS.PAD_TO/d))) if d < CS.PAD_TO else seg, sr)
        lst.append((CS.SPK.embed(fp), d))
    if len(lst) >= 2:
        embs[u] = [x[0] for x in lst]
        durs[u] = [x[1] for x in lst]

print('可用条数', len(embs), '| 段总数', sum(len(v) for v in embs.values()))

within, between = [], []
for u, E in embs.items():
    for i, j in itertools.combinations(range(len(E)), 2):
        within.append((CS.SPK.cos(E[i], E[j]), durs[u][i], durs[u][j]))
keys = list(embs)
for a_, b_ in itertools.combinations(keys, 2):
    for x in embs[a_][:2]:
        for y in embs[b_][:2]:
            between.append(CS.SPK.cos(x, y))

w = np.array([x[0] for x in within]); b = np.array(between)
print('\nwithin (同一句内)  n=%d  中位 %.3f  p10 %.3f  min %.3f' % (
    len(w), np.median(w), np.percentile(w, 10), w.min()))
print('between (不同句间) n=%d  中位 %.3f  p10 %.3f  min %.3f' % (
    len(b), np.median(b), np.percentile(b, 10), b.min()))
print('差值（within - between 中位）= %.3f' % (np.median(w) - np.median(b)))

print('\n按较短段时长分桶（两个段取短的那个）：')
print('%-10s %4s %10s %10s' % ('段长', 'n', 'within中位', '<0.55比例'))
for lo, hi in [(0, .4), (.4, .6), (.6, .8), (.8, 1.2), (1.2, 2.0), (2.0, 99)]:
    sel = [x[0] for x in within if lo <= min(x[1], x[2]) < hi]
    if sel:
        print('%-10s %4d %10.3f %9.0f%%' % ('%.1f-%.1fs' % (lo, hi), len(sel),
              np.median(sel), 100*np.mean([s < 0.55 for s in sel])))
