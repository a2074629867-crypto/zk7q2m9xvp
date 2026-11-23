import glob, statistics, parselmouth, numpy as np
fs = sorted(glob.glob('_audio_ch123/out/c1_*.wav'))[:20]
allg=[]; per=[]
for f in fs:
    s = parselmouth.Sound(f)
    it = s.to_intensity(minimum_pitch=75)
    v = it.values[0]; t = it.xs()
    if len(v)==0: continue
    thr = np.nanmax(v) - 25.0
    sil = v < thr
    gaps=[]; i=0; n=len(sil)
    while i < n:
        if sil[i]:
            j=i
            while j<n and sil[j]: j+=1
            d = t[min(j,n-1)] - t[i]
            if d >= 0.08 and t[i] > 0.2 and t[min(j,n-1)] < s.duration-0.2:
                gaps.append(d)
            i=j
        else: i+=1
    per.append((f.split('/')[-1], s.duration, len(gaps), (statistics.median(gaps) if gaps else 0), (max(gaps) if gaps else 0)))
    allg += gaps
print('file              dur    n_gap  med_gap  max_gap')
for r in per: print('%-18s %5.2f  %3d   %5.2f    %5.2f'%r)
if allg:
    print('\n合计句内停顿 %d 处'%len(allg))
    print('中位数 %.3fs  均值 %.3fs  P90 %.3fs  最大 %.3fs'%(statistics.median(allg), statistics.mean(allg), np.percentile(allg,90), max(allg)))
    for lo,hi,name in [(0,0.2,'<0.2s'),(0.2,0.4,'0.2-0.4'),(0.4,0.6,'0.4-0.6'),(0.6,1.0,'0.6-1.0'),(1.0,9,'>1.0s')]:
        c=sum(1 for g in allg if lo<=g<hi); print('  %-9s %3d  (%.0f%%)'%(name,c,100*c/len(allg)))
