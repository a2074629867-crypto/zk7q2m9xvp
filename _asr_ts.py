import os, sys, wave
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

so=ort.SessionOptions(); so.log_severity_level=3
m=onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3","G:/_setup/models/parakeet-v3-int8",quantization="int8",
                      providers=[("CPUExecutionProvider",{})],sess_options=so)
tm=m.with_timestamps()
for p in sys.argv[1:]:
    a,sr=rd(p)
    r=tm.recognize(r16(a,sr))
    print("="*70)
    print(os.path.basename(p), "%.2fs"%(len(a)/sr))
    print("type:", type(r))
    print("repr:", repr(r)[:600])
