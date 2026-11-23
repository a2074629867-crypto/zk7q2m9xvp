import os, sys, json, wave
import numpy as np, onnxruntime as ort, onnx_asr
os.environ.setdefault("HF_ENDPOINT","https://hf-mirror.com"); os.environ.setdefault("HF_HUB_OFFLINE","1")

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

def to_words(tokens, ts, dur):
    """子词 token → 词（拼接名字，结束时间=下一词起点）"""
    out=[]
    for tk,t in zip(tokens,ts):
        if tk.startswith(" ") or not out:
            out.append([tk.strip(), t])
        elif all(not c.isalnum() for c in tk):      # 纯标点单独成词
            out.append([tk.strip(), t])
        else:
            out[-1][0]+=tk
    for i in range(len(out)-1): out[i].append(out[i+1][1])
    out[-1].append(dur)
    return [dict(w=w, start=round(s,3), end=round(e,3)) for w,s,e in out]

so=ort.SessionOptions(); so.log_severity_level=3
m=onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3","G:/_setup/models/parakeet-v3-int8",quantization="int8",
                      providers=[("CPUExecutionProvider",{})],sess_options=so)
tm=m.with_timestamps()
out={}
for p in sys.argv[1:]:
    a,sr=rd(p); dur=len(a)/sr
    r=tm.recognize(r16(a,sr))
    out[p]=dict(dur=round(dur,3), text=r.text, words=to_words(r.tokens, r.timestamps, dur))
json.dump(out, open("_words.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
for p,v in out.items():
    print("%-40s %.2fs  %d 词" % (os.path.basename(os.path.dirname(p))+'/'+os.path.basename(p), v["dur"], len(v["words"])))
