# -*- coding: utf-8 -*-
"""同一句话、不同 take 的韵律差异 vs 不同句子的差异 —— 噪声地板。"""
import sys, os, glob, re, random, itertools
sys.path.insert(0, 'G:/_setup')
import numpy as np
from _band import sent_stats

random.seed(3); np.random.seed(3)

def dtw(a, b):
    n, m = len(a), len(b)
    D = np.full((n + 1, m + 1), np.inf); D[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i, j] = abs(a[i - 1] - b[j - 1]) + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return D[n, m] / (n + m)

items = []
for p in sorted(glob.glob('_ab48/*.wav')):
    b = os.path.basename(p)
    if '.raw.' in b: continue
    m = re.search(r'(c\d_\d{4})', b)
    if m: items.append((m.group(1), p))
for d in sorted(glob.glob('_seedpick/*')):
    if os.path.isdir(d):
        for p in glob.glob(d + '/*.wav'):
            items.append((os.path.basename(d), p))
print('files', len(items), 'sentences', len({s for s, _ in items}))

seq = {}
for sid, p in items:
    r = sent_stats(p)
    if r and len(r['deltas']) >= 4:
        v = np.array(r['deltas'], float)
        seq[p] = (v - v.mean()) / (v.std() + 1e-9)
print('可用', len(seq))

groups = {}
for sid, p in items:
    if p in seq: groups.setdefault(sid, []).append(p)

same = []
for sid, ps in groups.items():
    for a, b in itertools.combinations(ps, 2):
        d = dtw(seq[a], seq[b])
        if d: same.append(d)
gl = [g for g in groups if len(groups[g])]
diff = []
for _ in range(4000):
    s1, s2 = random.sample(gl, 2)
    a = random.choice(groups[s1]); b = random.choice(groups[s2])
    d = dtw(seq[a], seq[b])
    if d: diff.append(d)

print(f'同句不同 take: n={len(same)}  DTW 中位={np.median(same):.3f}  p10/90={np.percentile(same,10):.3f}/{np.percentile(same,90):.3f}')
print(f'不同句:        n={len(diff)}  DTW 中位={np.median(diff):.3f}  p10/90={np.percentile(diff,10):.3f}/{np.percentile(diff,90):.3f}')
print(f'比值 = {np.median(same)/np.median(diff):.3f}   （1.0 = 同句的 take 之间与不同句一样不像）')
