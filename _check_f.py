# -*- coding: utf-8 -*-
import os, re, glob, wave, difflib
import numpy as np, onnxruntime as ort, onnx_asr
os.environ.setdefault("HF_ENDPOINT","https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE","1")
TGT = open("G:/_setup/scene_calmdeep.txt",encoding="utf-8").read().strip()
def rd(p):
    with wave.open(p,"rb") as w:
        sr,ch,sw,nf=w.getframerate(),w.getnchannels(),w.getsampwidth(),w.getnframes(); raw=w.readframes(nf)
    a=np.frombuffer(raw,dtype="<i2").astype(np.float32)/32768.0
    if ch>1: a=a.reshape(-1,ch).mean(1)
    return a,sr
def r16(a,sr):
    if sr==16000: return a
    n=int(round(len(a)*16000/sr))
    return np.interp(np.linspace(0,len(a)-1,n),np.arange(len(a),dtype=np.float64),a).astype(np.float32)
def norm(t):
    t=t.lower(); t=re.sub(r"[^a-z0-9' ]+"," ",t); return " ".join(t.split())
so=ort.SessionOptions(); so.log_severity_level=3
m=onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3","G:/_setup/models/parakeet-v3-int8",quantization="int8",
                      providers=[("CPUExecutionProvider",{})],sess_options=so)
tw=norm(TGT).split()
print("原文 %d 词\n" % len(tw))
for f in sorted(glob.glob("G:/_setup/dots_emo/F*.wav")):
    a,sr=rd(f); seg=r16(a,sr)
    txt=m.recognize(seg) or ""
    gw=norm(txt).split()
    sm=difflib.SequenceMatcher(None,tw,gw)
    sim=sm.ratio()
    missing=[w for w in tw if w not in gw]
    print("%-18s %5.2fs  词数 %d/%d  sim=%.3f  缺=%s" % (os.path.basename(f),len(a)/sr,len(gw),len(tw),sim,missing[:6] or "无"))
