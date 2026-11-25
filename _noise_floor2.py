# -*- coding: utf-8 -*-
"""噪声地板（无需转写、无需 GPU）：同句不同 take 的 F0 轮廓 vs 不同句。
做法：整句 F0 → 只在有声段内插值 → 时间归一化到 64 点 → z 归一 → DTW。"""
import os, glob, re, random, itertools, sys
import numpy as np, soundfile as sf, parselmouth

random.seed(5); np.random.seed(5)

def contour(path, n=64):
    y, sr = sf.read(path, dtype='float32')
    if y.ndim > 1: y = y.mean(1)
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    p = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=350)
    f0 = p.selected_array['frequency'].astype(float)
    v = f0 > 0
    if v.sum() < 20: return None
    idx = np.arange(len(f0))
    f = np.interp(idx, idx[v], f0[v])
    st = 12*np.log2(np.maximum(f,1)/100.0)
    x = np.linspace(0, len(st)-1, n)
    r = np.interp(x, np.arange(len(st)), st)
    return (r - r.mean())/(r.std()+1e-9)

def dtw(a,b):
    n=len(a); D=np.full((n+1,n+1),np.inf); D[0,0]=0
    for i in range(1,n+1):
        for j in range(1,n+1):
            D[i,j]=abs(a[i-1]-b[j-1])+min(D[i-1,j],D[i,j-1],D[i-1,j-1])
    return D[n,n]/(2*n)

items=[]
for p in sorted(glob.glob('_ab48/*.wav')):
    b=os.path.basename(p)
    if '.raw.' in b: continue
    m=re.search(r'(c\d_\d{4})',b)
    if m: items.append((m.group(1),p))
for d in sorted(glob.glob('_seedpick/*')):
    if os.path.isdir(d):
        for p in glob.glob(d+'/*.wav'): items.append((os.path.basename(d),p))
C={p:contour(p) for _,p in items}
C={p:c for p,c in C.items() if c is not None}
print('files',len(items),'可用轮廓',len(C),'句子',len({s for s,p in items if p in C}))

g={}
for s,p in items:
    if p in C: g.setdefault(s,[]).append(p)
same=[dtw(C[a],C[b]) for s,ps in g.items() for a,b in itertools.combinations(ps,2)]
gl=[s for s in g if len(g[s])>1]
allp=[p for p in C]
diff=[]
for _ in range(4000):
    a,b=random.sample(allp,2)
    sa={s for s,ps in g.items() if a in ps}.pop(); sb={s for s,ps in g.items() if b in ps}.pop()
    if sa==sb: continue
    diff.append(dtw(C[a],C[b]))
print(f'同句不同 take: n={len(same)} 中位={np.median(same):.3f} p10/90={np.percentile(same,10):.3f}/{np.percentile(same,90):.3f}')
print(f'不同句:        n={len(diff)} 中位={np.median(diff):.3f} p10/90={np.percentile(diff,10):.3f}/{np.percentile(diff,90):.3f}')
print(f'比值={np.median(same)/np.median(diff):.3f}  1.0=同句与不同句一样不像')
