import json,glob,os,statistics as st
import numpy as np, soundfile as sf
phys={x['id']:x for x in json.load(open('_narr_phys.json',encoding='utf-8'))}
words=sum(x['words'] for x in phys.values())
D='G:/_setup/_audio_ch123/out'
tot=voi=0.0;peak=0.0;gaps=[];lev=[];miss=0;bad=[]
for sid in phys:
    p=os.path.join(D,sid+'.wav')
    if not os.path.exists(p): miss+=1; continue
    y,sr=sf.read(p,dtype='float32')
    if y.ndim>1: y=y.mean(1)
    tot+=len(y)/sr; peak=max(peak,float(np.abs(y).max()))
    h=int(sr*0.01); n=len(y)//h
    db=20*np.log10(np.sqrt((y[:n*h].reshape(n,h)**2).mean(1)+1e-12)+1e-12)
    v=db>-35.0; idx=np.flatnonzero(v)
    if len(idx)<2: continue
    voi+=len(idx)*0.01
    r=float(np.sqrt((y[:n*h].reshape(n,h)[v].astype(np.float64)**2).mean()))
    lev.append(20*np.log10(r+1e-12))
    if lev[-1]<-24.9 or lev[-1]>-23.1: bad.append((sid,round(lev[-1],2)))
    a,b=idx[0],idx[-1]; i=a
    while i<=b:
        if not v[i]:
            j=i
            while j<=b and not v[j]: j+=1
            if (j-i)*0.01>=0.40: gaps.append((j-i)*0.01)
            i=j
        else: i+=1
gaps.sort(); q=lambda p: gaps[min(len(gaps)-1,int(len(gaps)*p))]
print('n=%d 总长 %.1fs 成品 %.0f wpm 语音 %.1fs 峰值 %.3f'%(len(phys)-miss,tot,words/tot*60,voi,peak))
print('gap %d median %.2f p25 %.2f p75 %.2f p90 %.2f max %.2f'%(len(gaps),st.median(gaps),q(.25),q(.75),q(.9),gaps[-1]))
print('RMS 中位 %.1f dB  跨度 %.1f dB (−24目标)  越界 %d 条'%(st.median(lev),max(lev)-min(lev),len(bad)))
from collections import Counter
print('分布', Counter(round(g,2) for g in gaps).most_common(6))
