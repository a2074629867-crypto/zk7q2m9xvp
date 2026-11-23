# -*- coding: utf-8 -*-
import sys, numpy as np, soundfile as sf
SR=48000
def gaps(p):
    x,sr=sf.read(p,dtype='float64',always_2d=True); x=x.mean(1)
    hop=int(SR*0.010); n=len(x)//hop
    db=20*np.log10(np.sqrt((x[:n*hop].reshape(n,hop)**2).mean(1))+1e-12)
    sp=db>(db.max()-35.0)
    m=sp.copy(); i=0
    while i<len(m):
        if not m[i]:
            j=i
            while j<len(m) and not m[j]: j+=1
            if i>0 and j<len(m) and (j-i)<8: m[i:j]=True
            i=j
        else: i+=1
    i=0
    while i<len(m):
        if m[i]:
            j=i
            while j<len(m) and m[j]: j+=1
            if (j-i)<12: m[i:j]=False
            i=j
        else: i+=1
    segs=[];i=0
    while i<n:
        if m[i]:
            j=i
            while j<n and m[j]: j+=1
            segs.append((i*0.01,j*0.01)); i=j
        else: i+=1
    gs=[segs[k][0]-segs[k-1][1] for k in range(1,len(segs))]
    gs=[g for g in gs if g>0.02]
    return len(x)/SR, sum(b-a for a,b in segs), gs
print("%-22s %7s %7s %7s %7s %6s" % ("file","total","speech","silence","gapMed","nGap"))
for p in sys.argv[1:]:
    d,v,gs=gaps(p)
    print("%-22s %7.2f %7.2f %7.2f %7.2f %6d" % (p.split('/')[-1], d, v, d-v,
          np.median(gs) if gs else 0, len(gs)))
