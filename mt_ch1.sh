#!/bin/bash
# mt_ch1.sh —— 第一章按新规则重做（rate 深度放慢 → ASR → NISQA → 择优 → 拼章 → 质检）
# 全部阶段可断点续跑。
set -u
cd /g/_setup || exit 1
PY="G:/Python310/python.exe"
DPY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
ASRV="./asr_venv/Scripts/python.exe"
LOG="_mt_ch1.log"
DIRS="_mt_raw_s42,_mt_raw_s1234,_mt_raw_s777,_mt_raw_srate"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_OFFLINE=1

echo "=== ch1 rebuild start $(date '+%F %T') ===" >> "$LOG"

echo "--- ① rate 生成（逐条 factor=0.40）---" >> "$LOG"
"$PY" mt_gen.py --ch ch1 --seeds 42 --outdir _mt_raw_srate >> "$LOG" 2>&1

echo "--- ② ASR ---" >> "$LOG"
"$ASRV" mt_asr_all.py --dirs "$DIRS" --out _mt_asr.json >> "$LOG" 2>&1

echo "--- ③ NISQA ---" >> "$LOG"
"$PY" mt_nisqa_all.py --dirs "$DIRS" --out _mt_nisqa.json >> "$LOG" 2>&1

echo "--- ④ 择优 ---" >> "$LOG"
"$DPY" mt_score.py --ch ch1 --dirs "$DIRS" --nisqa _mt_nisqa.json >> "$LOG" 2>&1

echo "--- ⑤ 拼章 ---" >> "$LOG"
"$PY" mt_post.py --ch ch1 --plan mt_plan3.json >> "$LOG" 2>&1

echo "--- ⑥ 质检 ---" >> "$LOG"
"$PY" mt_report.py --ch ch1 >> "$LOG" 2>&1
"$DPY" mt_consist.py --wav _mt_out/ch1.wav >> "$LOG" 2>&1
"E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i _mt_out/ch1.wav \
    -codec:a libmp3lame -b:a 128k _mt_out/ch1.mp3 >> "$LOG" 2>&1
"$PY" mt_page.py --out mt_review.html >> "$LOG" 2>&1

echo "=== ch1 rebuild done $(date '+%F %T') ===" >> "$LOG"
