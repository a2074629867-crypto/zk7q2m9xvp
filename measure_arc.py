# -*- coding: utf-8 -*-
"""按语音段切分，逐句量 wpm / F0 首末差 / 间隙，用于对照真人 vs 生成。"""
import sys, re
import numpy as np, soundfile as sf, parselmouth

SR = 48000
def seg_split(p):
    x, sr = sf.read(p, dtype="float64", always_2d=True)
    x = x.mean(1)
    if sr != SR:
        from scipy.signal import resample_poly
        x = resample_poly(x, SR, sr)
    hop = int(SR*0.010); n = len(x)//hop
    db = 20*np.log10(np.sqrt((x[:n*hop].reshape(n,hop)**2).mean(1))+1e-12)
    sp = db > (db.max()-35.0)
    def sm(m, mg=8, mi=12):
        m=m.copy(); i=0
        while i<len(m):
            if not m[i]:
                j=i
                while j<len(m) and not m[j]: j+=1
                if i>0 and j<len(m) and (j-i)<mg: m[i:j]=True
                i=j
            else: i+=1
        i=0
        while i<len(m):
            if m[i]:
                j=i
                while j<len(m) and m[j]: j+=1
                if (j-i)<mi: m[i:j]=False
                i=j
            else: i+=1
        return m
    sp=sm(sp)
    segs=[]; i=0
    while i<n:
        if sp[i]:
            j=i
            while j<n and sp[j]: j+=1
            segs.append((i*0.01, j*0.01)); i=j
        else: i+=1
    return x, segs

def f0_of(x):
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=SR)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=400,
                          voicing_threshold=0.35, octave_jump_cost=1.0, octave_cost=0.01)
    f0 = np.asarray(pit.selected_array["frequency"], dtype=np.float64)
    t = np.asarray(pit.xs(), dtype=np.float64)
    return t, f0

def st(a,b): return 12*np.log2(max(a,1e-6)/max(b,1e-6))

CLAUSES = ["and heating into vapor", "It is swirling in lakes", "swelling in oceans",
           "and evaporating in disguise", "It is gathering into clouds",
           "raining down onto hills and fields", "dripping down from leafy trees",
           "trickling into streams", "flowing down rivers"]

for p in sys.argv[1:]:
    x, segs = seg_split(p)
    t, f0 = f0_of(x)
    dur = len(x)/SR
    print("="*78)
    print("%s   总长 %.2fs   语音段 %d" % (p.split("/")[-1], dur, len(segs)))
    if len(segs) != len(CLAUSES):
        print("  ⚠ 段数 %d != 子句数 %d，按顺序近似对应" % (len(segs), len(CLAUSES)))
    tot_v = sum(b-a for a,b in segs)
    print("  语音 %.2fs (%.1f%%)  静音 %.2fs" % (tot_v, tot_v/dur*100, dur-tot_v))
    prev_end = 0.0
    rows=[]
    for k,(a,b) in enumerate(segs):
        gap = a - prev_end if k > 0 else a
        # F0 within this segment
        m = (t >= a) & (t <= b) & (f0 > 0)
        f = f0[m]
        arc = None
        if len(f) > 10:
            k5 = max(1, len(f)//5)
            arc = st(f[-k5:].mean(), f[:k5].mean())
        txt = CLAUSES[k] if k < len(CLAUSES) else "?"
        nw = len(txt.split())
        wpm = nw/(b-a)*60
        rows.append((k, txt, b-a, gap, nw, wpm, arc))
        prev_end = b
    print("  %-3s %-38s %6s %6s %4s %6s %7s" % ("#","clause","dur","gap","w","wpm","arc"))
    for k,txt,d,g,nw,wpm,arc in rows:
        print("  %-3d %-38s %6.2f %6.2f %4d %6.0f %7s" % (
            k+1, txt[:38], d, g, nw, wpm, ("%+.2f"%arc) if arc is not None else "  -"))
    gs=[r[3] for r in rows[1:]]
    if gs:
        print("  → 间隙 中位 %.2fs  合计 %.2fs   语速 中位 %.0f wpm" % (
            np.median(gs), sum(gs), np.median([r[5] for r in rows])))
