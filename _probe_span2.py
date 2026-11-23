import numpy as np, soundfile as sf, sys
sys.path.insert(0,'G:/_setup')
import narr_check as NC
def show(p,l):
    y,sr=sf.read(p)
    if y.ndim>1: y=y.mean(1)
    y=np.ascontiguousarray(y,dtype=np.float32)
    d=NC.l1_unit(y,sr)
    dur=len(y)/sr
    print(f"{l:24s} dur={dur:6.2f}  span={d.get('energy_span')}  band={d.get('energy_band')}  f0_med={d.get('f0_med')}  f0jump={d.get('f0_jump_n')}  hardcut={d.get('cut_hard')}")
for p,l in [(r'G:/_setup/_narr_new/out/B000.wav','新链路 B000(已移植)'),
            (r'G:/_setup/_narr_new/raw/B000.wav','B000 原样(未移植)'),
            (r'G:/_setup/_narr_new/out/B001.wav','新链路 B001(已移植)'),
            (r'G:/_setup/_narr_new/raw/B001.wav','B001 原样(未移植)'),
            (r'G:/_setup/_audio_ch123/out/c1_0001.wav','旧 c1_0001'),
            (r'G:/_setup/_audio_ch123/out/c1_0008.wav','旧 c1_0008')]:
    try: show(p,l)
    except Exception as e: print(l,"ERR",e)
