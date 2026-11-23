# -*- coding: utf-8 -*-
"""对齐 sanity：EmphaClass 跳 0.5 的帧是不是落在发声区内（否则就是时间轴错了）"""
import json, glob, os, numpy as np, soundfile as sf
emp = {x['id']: x for x in json.load(open('_emp_narr_all.json', encoding='utf-8'))}
D = 'G:/_setup/_audio_ch123/out_bak_prepause'
ps, vs = [], []
for sid in sorted(emp)[:40]:
    p = np.asarray(emp[sid]['p'], float); dur = float(emp[sid]['dur'])
    f = os.path.join(D, sid + '.wav')
    if not os.path.exists(f): continue
    y, sr = sf.read(f, dtype='float32')
    if y.ndim > 1: y = y.mean(1)
    h = int(sr * 0.01); n = len(y) // h
    db = 20 * np.log10(np.sqrt((y[:n*h].reshape(n, h) ** 2).mean(1) + 1e-12) + 1e-12)
    v10 = db > -35.0
    # 10ms 网格 -> 帧网格
    idx = np.clip((np.arange(len(p)) / len(p) * n).astype(int), 0, n - 1)
    voiced = v10[idx]
    ps.append(float((p > 0.5).mean())); vs.append(float(voiced.mean()))
    if len(ps) <= 5:
        hi = p > 0.5
        print('%s frames %d  v/(n) %.2f  强调帧占比 %.3f  强调帧中在发声区比例 %.2f' %
              (sid, len(p), dur, hi.mean(), (voiced[hi].mean() if hi.any() else float('nan'))))
print('40 条：平均强调帧占比 %.3f，平均发声帧占比 %.3f' % (np.mean(ps), np.mean(vs)))
