#!/bin/bash
# mt_ch1b.sh —— 第一章收尾：补生成失败条 → 重评 ASR/NISQA → 择优 → 拼章 → 质检
set -u
cd /g/_setup || exit 1
PY="G:/Python310/python.exe"
DPY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
ASRV="./asr_venv/Scripts/python.exe"
LOG="_mt_ch1b.log"
BASE="_mt_raw_s42,_mt_raw_s1234,_mt_raw_s777,_mt_raw_srate"
FIX="_mt_raw_sfixa,_mt_raw_sfixb,_mt_raw_sfixc"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_OFFLINE=1

echo "=== ch1 收尾 start $(date '+%F %T') ===" >> "$LOG"
IDS=$(cat _mt_fail_ch1.txt)
echo "补生成清单：$IDS" >> "$LOG"

echo "--- ① 补生成 3 轮 ---" >> "$LOG"
# 注意：不传 --rate-file 时会自动吃 _mt_rate_ch1.json，纯种子轮必须显式指向不存在的文件
"$PY" mt_gen.py --ch ch1 --plan mt_plan3.json --seeds 777   --outdir _mt_raw_sfixa --ids "$IDS" --rate-file _mt_rate_none.json >> "$LOG" 2>&1
"$PY" mt_gen.py --ch ch1 --plan mt_plan3.json --seeds 2024  --outdir _mt_raw_sfixb --ids "$IDS" --rate-file _mt_rate_fix.json  >> "$LOG" 2>&1
"$PY" mt_gen.py --ch ch1 --plan mt_plan3.json --seeds 31337 --outdir _mt_raw_sfixc --ids "$IDS" --rate-file _mt_rate_none.json >> "$LOG" 2>&1

echo "--- ② ASR（全 7 池）---" >> "$LOG"
"$ASRV" mt_asr_all.py --dirs "$BASE,$FIX" --out _mt_asr.json >> "$LOG" 2>&1

echo "--- ③ NISQA（全 7 池）---" >> "$LOG"
"$PY" mt_nisqa_all.py --dirs "$BASE,$FIX" --out _mt_nisqa.json >> "$LOG" 2>&1

echo "--- ④ 择优 ---" >> "$LOG"
"$DPY" mt_score.py --ch ch1 --dirs "$BASE,$FIX" --plan mt_plan3.json >> "$LOG" 2>&1

echo "--- ⑤ 拼章 ---" >> "$LOG"
"$PY" mt_post.py --ch ch1 --plan mt_plan3.json >> "$LOG" 2>&1

echo "--- ⑥ 质检 ---" >> "$LOG"
"$PY" mt_report.py --ch ch1 >> "$LOG" 2>&1
"$DPY" mt_consist.py --wav _mt_out/ch1.wav >> "$LOG" 2>&1
"E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i _mt_out/ch1.wav \
    -codec:a libmp3lame -b:a 128k _mt_out/ch1.mp3 >> "$LOG" 2>&1
"$PY" mt_page.py --out mt_review.html >> "$LOG" 2>&1

echo "=== ch1 收尾 done $(date '+%F %T') ===" >> "$LOG"
