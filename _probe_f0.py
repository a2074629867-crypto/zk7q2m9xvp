import numpy as np, soundfile as sf, parselmouth
def jumps(p, floor, ceil, vt=0.20):
    x,sr=sf.read(p); 
    if x.ndim>1: x=x.mean(1)
    snd=parselmouth.Sound(np.ascontiguousarray(x,dtype=np.float64), sampling_frequency=sr)
    pit=snd.to_pitch_ac(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceil,
                        voicing_threshold=vt, silence_threshold=0.03)
    f=np.asarray(pit.selected_array['frequency'],dtype=float)
    v=f>0
    if v.sum()<8: return None
    fv=f[v]
    st=12*np.log2(fv/np.median(fv))
    d=np.abs(np.diff(st))
    ev=[x for x in d if x>=9.0]
    return dict(f0_med=float(np.median(fv)), n_jump=len(ev), max_jump=float(max(ev)) if ev else 0.0)
import os
tests=['c1_0008','c1_0007','c1_0064','c1_0097']
print(f"{'id':10s}{'floor/ceil':14s}{'f0_med':>8s}{'突跳数':>7s}{'max':>7s}")
for t in tests:
    p=f'G:/_setup/_audio_ch123/out/{t}.wav'
    if not os.path.exists(p): continue
    for (fl,ce,vt) in [(60,250,0.20),(60,180,0.20),(70,200,0.35)]:
        r=jumps(p,fl,ce,vt)
        if r: print(f"{t:10s}{f'{fl}/{ce}/{vt}':14s}{r['f0_med']:8.1f}{r['n_jump']:7d}{r['max_jump']:7.1f}")
    print()
