import numpy as np, soundfile as sf, parselmouth, os
def prof(p, label):
    x,sr=sf.read(p)
    if x.ndim>1: x=x.mean(1)
    dur=len(x)/sr
    snd=parselmouth.Sound(np.ascontiguousarray(x,dtype=np.float64), sampling_frequency=sr)
    pit=snd.to_pitch_ac(time_step=0.01,pitch_floor=60,pitch_ceiling=300,voicing_threshold=0.25,silence_threshold=0.03)
    f=np.asarray(pit.selected_array['frequency'],dtype=float); f=f[f>0]
    rms=20*np.log10(np.sqrt((x.astype(np.float64)**2).mean())+1e-12)
    print(f"{label:42s} dur={dur:6.2f}s  F0中位={np.median(f):6.1f}  F0_sd={np.std(f):5.1f}  RMS={rms:6.1f}")
files=[
 (r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav','chapter_run.py 用的 REF（Wonder）'),
 (r'G:/_setup/dots_edit2/MCH_matthew.wav','MCH_matthew（麦康纳素材）'),
 (r'G:/_setup/dots_edit2/MCH_quiet.wav','MCH_quiet'),
 (r'G:/_setup/dots_prog/E_mc1.wav','E_mc1'),
 (r'G:/_setup/_audio_ch123/out/c1_0001.wav','现有旁白 c1_0001'),
 (r'G:/_setup/_audio_ch123/out/c1_0008.wav','现有旁白 c1_0008'),
 (r'G:/_setup/_narr_new/out/B000.wav','新链路 B000（10:03 生成）'),
]
for p,l in files:
    if os.path.exists(p):
        try: prof(p,l)
        except Exception as e: print(l,"ERR",e)
    else: print(l,"MISSING")
