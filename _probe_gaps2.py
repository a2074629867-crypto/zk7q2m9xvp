import numpy as np, soundfile as sf, json, statistics as st, os
ids = {x['id'] for x in json.load(open('_narr_phys.json', encoding='utf-8'))}
gaps = []
miss = 0
for i in sorted(ids):
    f = 'G:/_setup/_audio_ch123/out/%s.wav' % i
    if not os.path.exists(f):
        miss += 1; continue
    y, sr = sf.read(f, dtype='float32')
    if y.ndim > 1: y = y.mean(1)
    hop = int(sr*0.01); n = len(y)//hop
    if n < 5: continue
    db = 20*np.log10(np.sqrt((y[:n*hop].reshape(n,hop)**2).mean(1)+1e-12)+1e-12)
    voiced = db > -35.0
    idx = np.flatnonzero(voiced)
    if len(idx) < 2: continue
    a, b = idx[0], idx[-1]; i2 = a
    while i2 <= b:
        if not voiced[i2]:
            j = i2
            while j <= b and not voiced[j]: j += 1
            d = (j-i2)*0.01
            if d >= 0.40: gaps.append(d)
            i2 = j
        else: i2 += 1
gaps.sort()
q = lambda p: gaps[int(len(gaps)*p)]
print('716 条中实到 %d，缺 %d' % (len(ids)-miss, miss))
print('内部停顿(>=0.40s) %d 处' % len(gaps))
print('median %.2f  p25 %.2f  p75 %.2f  p90 %.2f  max %.2f' % (st.median(gaps), q(.25), q(.75), q(.9), max(gaps)))
B = [(0.40,0.70,'0.4-0.7 (逗号内层)'),(0.70,1.05,'0.7-1.05'),(1.05,1.45,'1.05-1.45 (逗号位)'),(1.45,2.00,'1.45-2.0 (句号位)'),(2.00,9,'>=2.0 (段落位)')]
for lo,hi,lab in B:
    c = sum(1 for g in gaps if lo <= g < hi)
    print('%-24s %4d  %5.1f%%' % (lab, c, 100*c/len(gaps)))
