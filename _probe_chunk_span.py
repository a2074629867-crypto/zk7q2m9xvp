import numpy as np, soundfile as sf, sys, statistics
sys.path.insert(0,'G:/_setup')
import narr_check as NC
def units_span(p, tag):
    y,sr=sf.read(p)
    if y.ndim>1: y=y.mean(1)
    y=np.ascontiguousarray(y,dtype=np.float32)
    us=NC.cut_units(y,sr)
    out=[]
    for (a,b) in us:
        seg=y[int(a*sr):int(b*sr)]
        if len(seg)/sr < 2.5: continue
        d=NC.l1_unit(seg,sr)
        if d.get('energy_span') is not None: out.append(d['energy_span'])
    if out:
        o=sorted(out)
        print(f"{tag:26s} 句数={len(us):3d} 可测={len(out):3d}  span p10={o[int(.1*len(o))]:5.1f} 中位={statistics.median(o):5.1f} max={o[-1]:5.1f}")
    else:
        print(f"{tag:26s} 无可用句")
for p,t in [(r'G:/_setup/_narr_new/out/B000.wav','新 B000 切开'),
            (r'G:/_setup/_narr_new/out/B001.wav','新 B001 切开'),
            (r'G:/_setup/_audio_ch123/out/c1_0008.wav','旧 c1_0008 切开')]:
    units_span(p,t)
# 旧链路整章统计对照
import json
rows=json.load(open(r'G:/_setup/_narr_check2/_narr_check.json',encoding='utf-8'))
sp=[r['energy_span'] for r in rows if r.get('energy_span') is not None and (r.get('dur') or 0)>=2.5]
sp.sort()
print(f"\n旧链路 716 条整体（句级）: p10={sp[int(.1*len(sp))]:.1f} 中位={statistics.median(sp):.1f} max={sp[-1]:.1f}")
