import sys
sys.path.insert(0,'D:/py_libs')
import soundfile as sf, numpy as np
for f in ['_chap_ch1_v3.wav','_chap_ch1_raw2.wav']:
    x,sr=sf.read(f,dtype='float32',always_2d=True,frames=48000*400)
    x=x.mean(1)
    hop=int(sr*0.01); n=len(x)//hop
    db=20*np.log10(np.sqrt((x[:n*hop].reshape(n,hop)**2).mean(1))+1e-12)
    q=np.percentile(db,[1,5,10,25,50])
    print(f,'sr',sr,'p1/5/10/25/50 dB:',[round(float(v),1) for v in q],
          '| <-80dB %.1f%%'%(100*float((db<-80).mean())))
