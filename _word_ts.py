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

def words_from_tokens(tokens, ts):
    """子词 token → 词。以空格开头（或纯标点）为词边界。"""
    out=[]
    for tk,t in zip(tokens,ts):
        if tk.startswith(" ") or (out and all(not c.isalnum() for c in tk)):
            out.append([tk.strip(), t, t])
        elif out:
            out[-1][2]=t
        else:
            out.append([tk.strip(), t, t])
    return out

so=ort.SessionOptions(); so.log_severity_level=3
m=onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3","G:/_setup/models/parakeet-v3-int8",quantization="int8",
                      providers=[("CPUExecutionProvider",{})],sess_options=so)
tm=m.with_timestamps()

TARGET=sys.argv[1]
files=sys.argv[2:]
for p in files:
    a,sr=rd(p); dur=len(a)/sr
    r=tm.recognize(r16(a,sr))
    ws=words_from_tokens(r.tokens, r.timestamps)
    # 每个词的结束 = 下一个词的起点
    for i in range(len(ws)-1): ws[i][2]=ws[i+1][1]
    ws[-1][2]=dur
    hit=[w for w in ws if w[0].lower().startswith(TARGET.lower()[:4])]
    print("="*72)
    print("%-28s %.2fs  词数 %d" % (os.path.basename(os.path.dirname(p))+'/'+os.path.basename(p), dur, len(ws)))
    if hit:
        for w in hit:
            print("   %-12s %.3f → %.3f  时长 %.3f" % (w[0], w[1], w[2], w[2]-w[1]))
    else:
        print("   未找到", TARGET)
    # 全句能量/F0 供对比
    import parselmouth
    from parselmouth.praat import call
    s=parselmouth.Sound(p)
    pit=s.to_pitch(0.01,50,400)
    f=pit.selected_array['frequency']; ft=pit.xs()
    ok=f>0
    fm=float(np.median(f[ok])) if ok.sum() else 0
    if hit:
        w=hit[0]
        msk=(ft>=w[1])&(ft<=w[2])&ok
        fw=float(np.median(f[msk])) if msk.sum() else 0
        seg=a[int(w[1]*sr):int(w[2]*sr)]
        allv=a[np.abs(a)>1e-4]
        import math
        def rms(x): return 20*math.log10(math.sqrt((x**2).mean())+1e-12)
        print("   F0: 该词 %.1f / 全句 %.1f → %+.2f 半音 | 能量: 该词 %.1f / 全句 %.1f → %+.1f dB"
              % (fw, fm, 12*np.log2(fw/fm) if fw and fm else 0, rms(seg), rms(allv), rms(seg)-rms(allv)))
