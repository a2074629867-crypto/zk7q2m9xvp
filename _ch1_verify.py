# -*- coding: utf-8 -*-
"""整章 ASR 回读 + 与旁白文本逐词比对（按块）"""
import os, re, glob, wave, difflib, json
import numpy as np, onnxruntime as ort, onnx_asr
os.environ.setdefault("HF_ENDPOINT","https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE","1")

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

chunks=json.load(open("G:/_setup/chapter1/audio/chunks.json",encoding="utf-8"))
print("块数 %d" % len(chunks))
tot_sim=[]; bad=[]
for c in chunks:
    p="G:/_setup/chapter1/audio/fix/c%02d.wav" % c["idx"]
    if not os.path.exists(p):
        p="G:/_setup/chapter1/audio/raw/c%02d.wav" % c["idx"]
    if not os.path.exists(p):
        print("MISS", c.get("idx")); continue
    a,sr=rd(p); seg=r16(a,sr)
    txt=m.recognize(seg) or ""
    tw=norm(c["text"]).split(); gw=norm(txt).split()
    sim=difflib.SequenceMatcher(None,tw,gw).ratio()
    miss=[w for w in tw if w not in gw]
    tot_sim.append(sim)
    flag="OK " if sim>=0.90 else "BAD"
    print("%s c%02d %5.2fs 词 %d/%d sim=%.3f 缺%d %s" % (
        flag, c["idx"], len(a)/sr, len(gw), len(tw), sim, len(miss), ("| "+",".join(miss[:8])) if miss else ""))
    if sim<0.90: bad.append(c["idx"])
print()
print("块级 sim: 中位 %.3f  min %.3f  <0.90 的块: %s" % (np.median(tot_sim), min(tot_sim), bad or "无"))
