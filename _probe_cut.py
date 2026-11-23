import numpy as np, soundfile as sf
p=r"G:/_setup/_audio_ch123/out/c1_0001.wav"
x,sr=sf.read(p)
if x.ndim>1: x=x.mean(1)
k=max(int(0.005*sr),16)
body=x[max(0,len(x)-int(0.205*sr)):len(x)-k].astype(np.float64)
tail=x[-k:].astype(np.float64)
t_rms=float(np.sqrt((tail**2).mean())); b_rms=float(np.sqrt((body**2).mean()))
import math
print("sr",sr,"n",len(x),"dur",round(len(x)/sr,2))
print("末采样 abs", abs(float(x[-1])))
print("tail_rms",round(t_rms,6),"body_rms",round(b_rms,6))
print("cut_drop(新判据)", round(20*math.log10(t_rms/b_rms+1e-12),1))
print("cut_hard", bool(20*math.log10(t_rms/b_rms+1e-12) > -6.0 and abs(float(x[-1]))>0.02))
# 尾部包络 8 段
seg=np.array_split(x[-int(0.35*sr):], 8)
print("尾部 8 段 RMS(dB):", [round(20*math.log10(float(np.sqrt((s**2).mean()))+1e-12),1) for s in seg])
