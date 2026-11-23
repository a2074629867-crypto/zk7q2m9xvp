#!/bin/bash
# mt_rebuild.sh —— 三章按统一目标语速 190 重拼（只重做拉伸/拼接，不重新生成）
set -u
cd /g/_setup || exit 1
PY="G:/Python310/python.exe"
DPY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
LOG="_mt_rebuild.log"

echo "=== 统一语速重拼 start $(date '+%F %T') ===" >> "$LOG"
for ch in ch1 ch2 ch3; do
    echo "--- $ch ---" >> "$LOG"
    "$PY" mt_post.py --ch "$ch" --plan mt_plan3.json >> "$LOG" 2>&1
    "$PY" mt_report.py --ch "$ch" >> "$LOG" 2>&1
    "$DPY" mt_consist.py --wav "_mt_out/$ch.wav" >> "$LOG" 2>&1
    "E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i "_mt_out/$ch.wav" \
        -codec:a libmp3lame -b:a 128k "_mt_out/$ch.mp3" >> "$LOG" 2>&1
    "E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i "_mt_out/$ch.wav" -t 180 \
        -codec:a libmp3lame -b:a 128k "_mt_${ch}_head.mp3" >> "$LOG" 2>&1
done
"$PY" mt_page.py --out mt_review.html >> "$LOG" 2>&1
echo "=== 统一语速重拼 done $(date '+%F %T') ===" >> "$LOG"
