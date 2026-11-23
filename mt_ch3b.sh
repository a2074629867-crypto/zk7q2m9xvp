#!/bin/bash
# mt_ch3b.sh —— 第三章收尾：补生成 22 条 → 重评 → 拼章 → 质检 → 出 mp3/页面
set -u
cd /g/_setup || exit 1
PY="G:/Python310/python.exe"
DPY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
ASRV="./asr_venv/Scripts/python.exe"
LOG="_mt_ch3b.log"
DIRS="_mt_raw_s42,_mt_raw_s1234,_mt_raw_s2024,_mt_raw_s31337,_mt_raw_sf1,_mt_raw_sf2,_mt_raw_sf3,_mt_raw_sf4"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_OFFLINE=1

echo "=== ch3 收尾 start $(date '+%F %T') ===" >> "$LOG"
IDS=$(cat _mt_fix_ch3.txt)
echo "补生成清单（${#IDS} 字符）：$IDS" >> "$LOG"

for pair in "f1:1001" "f2:1002" "f3:1003" "f4:1004"; do
    d="${pair%%:*}"; s="${pair##*:}"
    echo "--- 种子 $s → _mt_raw_s$d ---" >> "$LOG"
    "$PY" mt_gen.py --ch ch3 --plan mt_plan3.json --seeds "$s" --outdir "_mt_raw_s$d" \
        --ids "$IDS" --rate-file _mt_rate_none.json >> "$LOG" 2>&1
done

"$ASRV" mt_asr_all.py --dirs "$DIRS" --out _mt_asr.json >> "$LOG" 2>&1
"$PY" mt_nisqa_all.py --dirs "$DIRS" --out _mt_nisqa.json >> "$LOG" 2>&1
"$DPY" mt_score.py --ch ch3 --dirs "$DIRS" --plan mt_plan3.json >> "$LOG" 2>&1
"$PY" mt_post.py --ch ch3 --plan mt_plan3.json >> "$LOG" 2>&1

"$PY" mt_report.py --ch ch3 >> "$LOG" 2>&1
"$DPY" mt_consist.py --wav _mt_out/ch3.wav >> "$LOG" 2>&1
"E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i _mt_out/ch3.wav \
    -codec:a libmp3lame -b:a 128k _mt_out/ch3.mp3 >> "$LOG" 2>&1
"E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i _mt_out/ch3.wav -t 180 \
    -codec:a libmp3lame -b:a 128k _mt_ch3_head.mp3 >> "$LOG" 2>&1
"$PY" mt_page.py --out mt_review.html >> "$LOG" 2>&1

echo "=== ch3 收尾 done $(date '+%F %T') ===" >> "$LOG"
