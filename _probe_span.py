import numpy as np, soundfile as sf, sys
sys.path.insert(0,'G:/_setup')
import narr_check as NC
def span(p):
    y,sr=sf.read(p)
    if y.ndim>1: y=y.mean(1)
    y=np.ascontiguousarray(y,dtype=np.float32)
    d=NC.l1_unit(y,sr)
    return d
for p,l in [(r'G:/_setup/_narr_new/out/B000.wav','新链路 B000'),
            (r'G:/_setup/_narr_new/out/B001.wav','新链路 B001'),
            (r'G:/_setup/_narr_new/raw/B000.wav','B000 未移植停顿'),
            (r'G:/_setup/_audio_ch123/out/c1_0001.wav','旧 c1_0001'),
            (r'G:/_setup/_audio_ch123/out/c1_0008.wav','旧 c1_0008')]:
    try:
        d=span(p)
        print(f"{l:22s} dur={d.get('dur'):6.2f}  span={d.get('energy_span')}  band={d.get('energy_band')}  f0_med={d.get('f0_med')}  cut_drop={d.get('cut_drop')}  verdict={'FIX' if d.get('cut_hard') or d.get('f0_jump_fix') else 'ok'}")
    except Exception as e:
        print(l,"ERR",e)
