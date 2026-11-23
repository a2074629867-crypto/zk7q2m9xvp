import glob, os, numpy as np, soundfile as sf, json, statistics as st
files = sorted(glob.glob('G:/_setup/_audio_ch123/out/c*.wav'))
print('files', len(files))
gaps = []
per = []
thr_db = -35.0
for f in files:
    y, sr = sf.read(f, dtype='float32')
    if y.ndim > 1: y = y.mean(1)
    hop = int(sr * 0.01)
    n = len(y) // hop
    if n < 5: continue
    fr = y[:n*hop].reshape(n, hop)
    rms = np.sqrt((fr**2).mean(1) + 1e-12)
    db = 20*np.log10(rms + 1e-12)
    voiced = db > thr_db
    # find runs of silence
    idx = np.flatnonzero(voiced)
    if len(idx) < 2: continue
    a, b = idx[0], idx[-1]
    runs = []
    i = a
    while i <= b:
        if not voiced[i]:
            j = i
            while j <= b and not voiced[j]: j += 1
            d = (j-i)*0.01
            if d >= 0.12: runs.append(d)
            i = j
        else:
            i += 1
    gaps.extend(runs)
    per.append((os.path.basename(f)[:-4], len(runs), sum(runs)))

gaps.sort()
q = lambda p: gaps[int(len(gaps)*p)]
print('internal gaps', len(gaps))
print('median %.3f  p25 %.3f  p75 %.3f  p90 %.3f  max %.2f' % (st.median(gaps), q(.25), q(.75), q(.9), max(gaps)))
buckets = [0.12,0.3,0.6,1.0,1.5,2.0,3.0,99]
lab = ['0.12-0.3','0.3-0.6','0.6-1.0','1.0-1.5','1.5-2.0','2.0-3.0','>=3.0']
for i in range(len(buckets)-1):
    c = sum(1 for g in gaps if buckets[i] <= g < buckets[i+1])
    print('%-10s %4d  %5.1f%%' % (lab[i], c, 100*c/len(gaps)))
print('每句平均停次数 %.2f' % (len(gaps)/len(per)))
sil = sum(p[2] for p in per); tot = sum(1 for _ in per)
print('停顿总时长 %.1f s' % sil)
json.dump({'gaps':gaps}, open('_probe_gaps.json','w'))
