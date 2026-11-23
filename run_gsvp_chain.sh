#!/usr/bin/env bash
# run_gsvp_chain.sh —— ★ 最终配方：把「停顿经验」+「环境底噪」加到 GSV 输出上
#
# 结论（2026-10-16 实测）：
#   真人 real_trim = 29.41s = 语音 17.57 + 静音 11.84，整段 0% 数字零（p01 −62.1 dB）
#   GSV 微调模型(e8_s1216+e10) 0.88x 直出 = 21.58s = 语音 17.63 + 静音 3.95  ← 语音已对齐
#   → 补停顿 = 27.92s（真人 95%）
#   → 再铺 room tone：数字零 26.7% → 0%，p01 −199.9 → −58.6 dB
#
# 三步都不能省：
#   ① donor（真人实际停顿序列）> 原型（pause_bank 中位数），未覆盖用 --proto-fallback 兜底
#   ② room tone：插进去的停顿是绝对数字零，不铺底噪会"环境一会儿在、一会儿不在"
#   ③ 声纹也跟着涨：0.8095 → 0.8474（真人基准本身带房间声）
set -u
S=/g/_setup
O=E:/tts-models/acpp/out/gsvp
REAL=E:/tts-models/acpp/out/calmdeep_final/real_trim.wav
BANK=$S/pause_bank.json
TONE=$S/rt/room_mcconaughey_clean.wav    # 40s / RMS −56dB，真人安静帧频谱 + 随机相位合成
PY="G:/Python310/python.exe"
export HF_HOME=C:/Users/86178/.cache/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

cd "$S"

# 输入：GSV 微调模型 speed_factor=0.88 的直出（sl088_final.wav, 21.58s）
# 若需重新生成：GSV_SPEED=0.88 G:/Python310/python.exe -u G:/_setup/real_scene.py \
#   --text-file G:/_setup/scene_calmdeep.txt --out E:/tts-models/acpp/out/sl088 \
#   --tag sl088 --skip-pause --skip-ex --eq-gain 0

echo "########## ① 补停顿（donor + 原型兜底）##########"
"$PY" -u "$S/insert_pauses.py" \
  --in  E:/tts-models/acpp/out/sl088/sl088_final.wav \
  --out "$O/gsvp_088_full.wav" \
  --donor "$REAL" --proto "$BANK" --proto-fallback --strength 1.0 \
  --report "$O/gsvp_088_full_pauses.json" 2>&1 | tail -14

echo
echo "########## ② 铺回 room tone（--match 自动对齐语音段底噪）##########"
"$PY" -u "$S/room_tone.py" \
  --in  "$O/gsvp_088_full.wav" \
  --out "$O/gsvp_088_full_room.wav" \
  --tone "$TONE" --match --mode all 2>&1 | tail -3

echo
echo "=== 结果 ==="
"$PY" -c "
import numpy as np, soundfile as sf
from scipy.signal import resample_poly
SR=48000
def fdb(x,sr,fl=0.02,hop=0.01):
    fl_n=max(1,int(fl*sr)); hop_n=max(1,int(hop*sr))
    n=max(1,(len(x)-fl_n)//hop_n+1)
    idx=np.arange(fl_n)[None,:]+hop_n*np.arange(n)[:,None]
    np.clip(idx,0,len(x)-1,out=idx)
    r=np.sqrt((x[idx]**2).mean(1)+1e-20)
    return 20*np.log10(r+1e-12)
print('  %-26s %7s %8s %9s'%('音轨','时长','p01','数字零%'))
for n,p in [('真人 real_trim','$REAL'),
            ('+停顿（无底噪）','$O/gsvp_088_full.wav'),
            ('+停顿+room tone ★','$O/gsvp_088_full_room.wav')]:
    x,sr=sf.read(p,dtype='float64')
    if x.ndim>1: x=x.mean(1)
    if sr!=SR: x=resample_poly(x,SR,sr)
    d=fdb(x,SR)
    print('  %-26s %6.2fs %8.1f %8.1f%%'%(n,len(x)/SR,np.percentile(d,1),100*(d<-150).mean()))"
echo GSVPCHAINDONE
