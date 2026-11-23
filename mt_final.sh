#!/bin/bash
# 交付链最后一步：逐处停顿（LLM 判定）+ 场景底噪
#
#   ch123/*.wav                    生成 + 切段电平
#     → ch123_final_build.py       降速（tempo 硬底 0.70）+ clean（整体增益 −24dBFS）
#     → ch123_final/*.wav
#     → 本脚本                     ← 停顿 + 底噪（唯一改动音频的最后一环）
#     → ch123_final_llm/*.wav      交付
#
# 停顿从哪来：pause_llm.json —— LLM 按「夏尔这个角色的情绪 + 语言自然度」逐处判绝对值，
#   不按标点档位给常数。标定基准是夏尔真人原声 castle_fr_ref（中位 0.43s / 0.15~0.76），
#   不是马修旁白母带（1.16/1.56）—— 那是 97wpm 睡前朗读，量级差 2~3 倍。
#   没有 LLM 判定时才退回档位（--no-llm）。
#
# 反序会出错：先做停顿再降速，停顿会被 rubberband 一起拉长；
# 先铺底噪再 clean，clean 的整体增益会把底噪一起放大 34dB。
set -u
cd /g/_setup || exit 1
PY="G:/Python310/python.exe"
export HF_HOME=C:/Users/86178/.cache/huggingface
export HF_HUB_OFFLINE=1

SRC="${1:-G:/_setup/ch123_final}"
DST="${2:-G:/_setup/ch123_final_llm}"
[ $# -ge 1 ] && shift
[ $# -ge 1 ] && shift

"$PY" -u mt_final_pause.py --in "$SRC" --out "$DST" "$@"
rc=$?

echo "--- 验收 ---"
"$PY" -u -c "
import glob,os,sys,numpy as np,soundfile as sf
sys.path.insert(0,r'G:/_setup')
from mt_final_pause import frame_db
dst=r'$DST'
f5=[];z=[];pk=[]
for f in sorted(glob.glob(os.path.join(dst,'*.wav'))):
    x,sr=sf.read(f,dtype='float32')
    if x.ndim>1: x=x.mean(1)
    d,_,_=frame_db(x,sr)
    f5.append(np.percentile(d,5)); z.append(100*(d<-90).mean()); pk.append(np.abs(x).max())
if f5:
    print('  静音段 p05 跨度 %.1f dB（%.1f ~ %.1f）'%(max(f5)-min(f5),min(f5),max(f5)))
    print('  残留零帧 >0.5%% 的条目 %d / %d'%(sum(1 for v in z if v>0.5),len(z)))
    print('  峰值 %.3f  削波 %d 条'%(max(pk),sum(1 for p in pk if p>=0.999)))
"
exit $rc
