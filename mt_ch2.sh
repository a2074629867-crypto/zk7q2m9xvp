#!/bin/bash
# mt_ch2.sh —— 第二章：两轮种子生成 → ASR → NISQA → 择优 → 拼章 → 质检
set -u
cd /g/_setup || exit 1
PY="G:/Python310/python.exe"
DPY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
ASRV="./asr_venv/Scripts/python.exe"
LOG="_mt_ch2.log"
DIRS="_mt_raw_s42,_mt_raw_s1234,_mt_raw_s777,_mt_raw_srate"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_OFFLINE=1

echo "=== ch2 start $(date '+%F %T') ===" >> "$LOG"

echo "--- ① 生成 seed 42 补齐 ---" >> "$LOG"
"$PY" mt_gen.py --ch ch2 --plan mt_plan3.json --seeds 42 --outdir _mt_raw_s42 --rate-file _mt_rate_none.json >> "$LOG" 2>&1

echo "--- ② 生成 seed 1234 ---" >> "$LOG"
"$PY" mt_gen.py --ch ch2 --plan mt_plan3.json --seeds 1234 --outdir _mt_raw_s1234 --rate-file _mt_rate_none.json >> "$LOG" 2>&1

echo "--- ③ ASR ---" >> "$LOG"
"$ASRV" mt_asr_all.py --dirs "$DIRS" --out _mt_asr.json >> "$LOG" 2>&1

echo "--- ④ NISQA ---" >> "$LOG"
"$PY" mt_nisqa_all.py --dirs "$DIRS" --out _mt_nisqa.json >> "$LOG" 2>&1

echo "--- ⑤ 择优 ---" >> "$LOG"
"$DPY" mt_score.py --ch ch2 --dirs "$DIRS" --plan mt_plan3.json >> "$LOG" 2>&1

echo "--- ⑥ 拼章 ---" >> "$LOG"
"$PY" mt_post.py --ch ch2 --plan mt_plan3.json >> "$LOG" 2>&1

echo "--- ⑦ 质检 ---" >> "$LOG"
"$PY" mt_report.py --ch ch2 >> "$LOG" 2>&1
"$DPY" mt_consist.py --wav _mt_out/ch2.wav >> "$LOG" 2>&1
"E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i _mt_out/ch2.wav \
    -codec:a libmp3lame -b:a 128k _mt_out/ch2.mp3 >> "$LOG" 2>&1
"$PY" mt_page.py --out mt_review.html >> "$LOG" 2>&1

echo "=== ch2 done $(date '+%F %T') ===" >> "$LOG"
