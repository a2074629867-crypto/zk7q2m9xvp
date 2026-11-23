import glob, wave
fs = sorted(glob.glob('_audio_ch123/out/*.wav'))
tot=0; n=0; bad=0
for f in fs:
    try:
        with wave.open(f) as w:
            tot += w.getnframes()/w.getframerate(); n+=1
    except Exception:
        bad+=1
print('files=%d  bad=%d'%(n,bad))
print('total=%.1fs = %d:%02d'%(tot, tot//60, tot%60))
print('human(LibriVox sec07) = 38:49 = 2329s')
print('ratio ours/human = %.3f'%(tot/2329.0))
