import sys, wave
import numpy as np
import onnxruntime as ort, onnx_asr
def rd(p):
    w=wave.open(p); sr=w.getframerate(); n=w.getnframes()
    a=np.frombuffer(w.readframes(n),dtype="<i2").astype(np.float32)/32768.0
    w.close(); return a,sr
def r16(a,sr):
    if sr==16000: return a
    n=int(round(len(a)*16000/sr)); return np.interp(np.linspace(0,len(a)-1,n),np.arange(len(a),dtype=np.float64),a).astype(np.float32)
so=ort.SessionOptions(); so.log_severity_level=3
m=onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3","G:/_setup/models/parakeet-v3-int8",quantization="int8",providers=[("CPUExecutionProvider",{})],sess_options=so)
for p in sys.argv[1:]:
    a,sr=rd(p); print(p.split("/")[-1], round(len(a)/sr,2), "->", m.recognize(r16(a,sr)))
