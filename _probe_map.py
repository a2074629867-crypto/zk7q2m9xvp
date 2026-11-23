import json, numpy as np, soundfile as sf, os
phys = {x['id']: x for x in json.load(open('_narr_phys.json', encoding='utf-8'))}
plan = json.load(open('_narr_pause_plan_v3.json', encoding='utf-8'))
items = {}
import glob
for f in sorted(glob.glob('_ann/tasks_tier_full/batch_*.json')):
    for it in json.load(open(f, encoding='utf-8'))['items']:
        items[it['sid']] = it
same = more = less = zero = 0
for sid in phys:
    f = '_audio_ch123/out/%s.wav' % sid
    y, sr = sf.read(f, dtype='float32')
    if y.ndim > 1: y = y.mean(1)
    hop = int(sr*0.01); n = len(y)//hop
    db = 20*np.log10(np.sqrt((y[:n*hop].reshape(n,hop)**2).mean(1)+1e-12)+1e-12)
    v = db > -35.0; idx = np.flatnonzero(v)
    if len(idx) < 2: zero += 1; continue
    a,b = idx[0], idx[-1]; c = 0; j = a
    while j <= b:
        if not v[j]:
            k = j
            while k <= b and not v[k]: k += 1
            if (k-j)*0.01 >= 0.40: c += 1
            j = k
        else: j += 1
    s = len(plan.get(sid, []))
    if c == s: same += 1
    elif c > s: more += 1
    elif c < s: less += 1
print('gap数==槽数: %d   多: %d   少: %d   无法测: %d   总 %d' % (same, more, less, zero, len(phys)))
print('可直接按顺序对齐的比例 %.1f%%' % (100*same/len(phys)))
