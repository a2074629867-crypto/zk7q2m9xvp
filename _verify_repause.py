import json, os, numpy as np, soundfile as sf, statistics as st
phys = {x['id']: x for x in json.load(open('_narr_phys.json', encoding='utf-8'))}
def scan(d):
    tot = 0.0; voiced = 0.0; gaps = []; peak = 0.0; lev = []
    for sid in phys:
        f = '%s/%s.wav' % (d, sid)
        y, sr = sf.read(f, dtype='float32')
        if y.ndim > 1: y = y.mean(1)
        tot += len(y)/sr; peak = max(peak, float(np.abs(y).max()))
        h = int(sr*0.01); n = len(y)//h
        db = 20*np.log10(np.sqrt((y[:n*h].reshape(n,h)**2).mean(1)+1e-12)+1e-12)
        v = db > -35.0; idx = np.flatnonzero(v)
        if len(idx) < 2: continue
        voiced += len(idx)*0.01
        # 语音段 RMS
        fv = y[:n*h].reshape(n,h)[v]
        lev.append(float(np.sqrt((fv.astype(np.float64)**2).mean())))
        a, b = idx[0], idx[-1]; i = a
        while i <= b:
            if not v[i]:
                j = i
                while j <= b and not v[j]: j += 1
                if (j-i)*0.01 >= 0.40: gaps.append((j-i)*0.01)
                i = j
            else: i += 1
    gaps.sort()
    q = lambda p: gaps[int(len(gaps)*p)]
    words = sum(x['words'] for x in phys.values())
    print('%-22s 总长 %.1fs  成品 %.0f wpm  语音 %.1fs' % (d.split('/')[-1], tot, words/tot*60, voiced))
    print('   gap %d 处  median %.2f  p25 %.2f  p75 %.2f  p90 %.2f' % (len(gaps), st.median(gaps), q(.25), q(.75), q(.9)))
    print('   峰值 %.3f  voiced RMS %.1f dBFS' % (peak, 20*np.log10(st.median(lev)+1e-12)))
print('参考：旧版')
scan('_audio_ch123/out_bak_prepause')
print('新版')
scan('_audio_ch123/out_v4')
