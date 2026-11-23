import json, os, sys, argparse
import numpy as np, soundfile as sf
SRC='G:/_setup/_audio_ch123/out'
PLAN='G:/_setup/_narr_pause_plan_v4.json'
THR=-35.0; MIN_GAP=0.40

def fdb(y,sr):
    h=max(1,int(sr*0.01)); n=len(y)//h
    if n<3: return np.zeros(0)
    f=y[:n*h].reshape(n,h)
    return 20*np.log10(np.sqrt((f**2).mean(1)+1e-12)+1e-12)

def gaps_of(y,sr):
    db=fdb(y,sr)
    if len(db)==0: return []
    v=db>THR; idx=np.flatnonzero(v)
    if len(idx)<2: return []
    a,b=idx[0],idx[-1]; out=[]; i=a
    while i<=b:
        if not v[i]:
            j=i
            while j<=b and not v[j]: j+=1
            if (j-i)*0.01>=MIN_GAP: out.append((int(i*0.01*sr),int(j*0.01*sr)))
            i=j
        else: i+=1
    return out

def bed_of(y,sr,gaps):
    win=int(0.1*sr)
    if len(y)<win*2: return np.zeros(win,dtype=np.float32)
    mask=np.ones(len(y),dtype=bool)
    for s,e in gaps: mask[max(0,s-win//2):min(len(y),e+win//2)]=False
    best=None; br=1e9
    for i in range(0,len(y)-win,win):
        if not mask[i:i+win].all(): continue
        r=float(np.sqrt((y[i:i+win]**2).mean()))
        if 1e-6<r<br: best,br=y[i:i+win],r
    return (best if best is not None else np.zeros(win)).astype(np.float32)

def rebuild(y,sr,gaps,targets,bed):
    if not gaps: return y
    out=[]; prev=0
    for (gs,ge),want in zip(gaps,targets):
        out.append(y[prev:gs]); sil=y[gs:ge]
        wn=max(1,int(round(want*sr))); cur=len(sil)
        if wn < cur-10:
            cut=cur-wn; a=(cur-cut)//2
            out.append(np.concatenate([sil[:a],sil[a+cut:]]))
        elif wn > cur+10:
            add=wn-cur; a=cur//2
            reps=int(np.ceil(add/len(bed))) if len(bed) else 1
            fill=np.tile(bed,reps)[:add] if len(bed) else np.zeros(add,dtype=np.float32)
            r=max(1,int(0.005*sr))
            if len(fill)>2*r:
                fill[:r]*=np.linspace(0,1,r); fill[-r:]*=np.linspace(1,0,r)
            out.append(np.concatenate([sil[:a],fill,sil[a:]]))
        else:
            out.append(sil)
        prev=ge
    out.append(y[prev:])
    return np.concatenate(out)

ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); a=ap.parse_args()
plan=json.load(open(PLAN,encoding='utf-8')); os.makedirs(a.out,exist_ok=True)
st={'exact':0,'fallback':0,'no_gap':0}
for sid in sorted(plan):
    f=os.path.join(SRC,sid+'.wav')
    if not os.path.exists(f): continue
    y,sr=sf.read(f,dtype='float32')
    if y.ndim>1: y=y.mean(1)
    g=gaps_of(y,sr); slots=plan[sid]
    if not g: st['no_gap']+=1; tg=[]
    elif len(g)==len(slots): st['exact']+=1; tg=[s['d'] for s in slots]
    else:
        st['fallback']+=1; G,S=len(g),len(slots)
        tg=([slots[int(round(i*(S-1)/(G-1))) if G>1 else 0]['d'] for i in range(G)] if S else [min(0.85,(e-s)/sr) for s,e in g])
    bed=bed_of(y,sr,g)
    y2=rebuild(y,sr,g,tg,bed)
    pk=float(np.abs(y2).max()) if len(y2) else 0.0
    if pk>0.999: y2*=0.99/pk
    sf.write(os.path.join(a.out,sid+'.wav'),y2,sr,subtype='PCM_16')
print('done',st)
