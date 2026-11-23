import numpy as np, soundfile as sf, sys, statistics
sys.path.insert(0,'G:/_setup')
import narr_check as NC

def analyze(p):
    y,sr=sf.read(p)
    if y.ndim>1: y=y.mean(1)
    y=np.ascontiguousarray(y,dtype=np.float32)
    w=NC.l1_unit(y,sr)
    us=NC.cut_units(y,sr)
    sp=[]
    for a,b in us:
        seg=y[int(a*sr):int(b*sr)]
        if len(seg)/sr<2.5: continue
        d=NC.l1_unit(seg,sr)
        if d.get('energy_span') is not None: sp.append(d['energy_span'])
    sp.sort()
    return dict(dur=len(y)/sr, span=w.get('energy_span'), f0jump=w.get('f0_jump_n'),
                nsent=len(us), nmeas=len(sp),
                smed=statistics.median(sp) if sp else None,
                sp10=sp[int(.1*len(sp))] if sp else None)

print(f"{'':26s}{'总时长':>8s}{'句数':>6s}{'可测':>5s}{'句span中位':>11s}{'F0突跳':>8s}")
for bid in ['B000','B001','B002']:
    a=analyze(f'G:/_setup/_narr_new/out/{bid}.wav')
    b=analyze(f'G:/_setup/_concat_ab/{bid}_concat_t.wav')
    ra=analyze(f'G:/_setup/_narr_new/raw/{bid}.wav') if bid!='B002' else None
    print(f"{bid+' chunk生成(移植后)':26s}{a['dur']:>8.1f}{a['nsent']:>6d}{a['nmeas']:>5d}{str(a['smed']):>11s}{a['f0jump']:>8}")
    print(f"{bid+' 拼接(移植后)':26s}{b['dur']:>8.1f}{b['nsent']:>6d}{b['nmeas']:>5d}{str(b['smed']):>11s}{b['f0jump']:>8}")
    if ra:
        print(f"{bid+' chunk生成(未移植)':26s}{ra['dur']:>8.1f}{ra['nsent']:>6d}{ra['nmeas']:>5d}{str(ra['smed']):>11s}{ra['f0jump']:>8}")
    print()

# 拼接处能量跳变：找句子边界，看边界前后 50ms 的 RMS 差
def seam_jump(p):
    y,sr=sf.read(p)
    if y.ndim>1: y=y.mean(1)
    us=NC.cut_units(np.ascontiguousarray(y,dtype=np.float32),sr)
    js=[]
    for i in range(len(us)-1):
        e=int(us[i][1]*sr); s2=int(us[i+1][0]*sr)
        # 前一语音段末尾 50ms vs 后一语音段开头 50ms
        k=int(0.05*sr)
        a=y[max(0,e-k):e]; b=y[s2:s2+k]
        if len(a)<k or len(b)<k: continue
        ra=20*np.log10(np.sqrt((a.astype(np.float64)**2).mean())+1e-12)
        rb=20*np.log10(np.sqrt((b.astype(np.float64)**2).mean())+1e-12)
        js.append(abs(ra-rb))
    return js
print("== 句间能量跳变（越小越衔接自然）==")
for bid in ['B000','B001']:
    for tag,p in [('chunk',f'G:/_setup/_narr_new/out/{bid}.wav'),('拼接',f'G:/_setup/_concat_ab/{bid}_concat_t.wav')]:
        js=seam_jump(p)
        if js: print(f"  {bid} {tag:6s} n={len(js):3d} 中位={statistics.median(js):5.1f}dB p90={sorted(js)[int(.9*len(js))]:5.1f} max={max(js):5.1f}")
