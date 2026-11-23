#!/bin/bash
# mt_ch4.sh —— 第三章：两轮种子 → 择优 → 失败补两轮 → 再择优 → 拼章 → 质检
set -u
cd /g/_setup || exit 1
PY="G:/Python310/python.exe"
DPY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
ASRV="./asr_venv/Scripts/python.exe"
LOG="_mt_ch4.log"
BASE="_mt_raw_s42,_mt_raw_s1234"
FIX="_mt_raw_s2024,_mt_raw_s31337"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_OFFLINE=1

echo "=== ch4 start $(date '+%F %T') ===" >> "$LOG"

echo "--- ① 生成 seed 42 ---" >> "$LOG"
"$PY" mt_gen.py --ch ch4 --plan mt_plan3b.json --seeds 42 --outdir _mt_raw_s42 --rate-file _mt_rate_none.json >> "$LOG" 2>&1

echo "--- ② 生成 seed 1234 ---" >> "$LOG"
"$PY" mt_gen.py --ch ch4 --plan mt_plan3b.json --seeds 1234 --outdir _mt_raw_s1234 --rate-file _mt_rate_none.json >> "$LOG" 2>&1

echo "--- ③ ASR ---" >> "$LOG"
"$ASRV" mt_asr_all.py --dirs "$BASE" --out _mt_asr.json >> "$LOG" 2>&1
echo "--- ④ NISQA ---" >> "$LOG"
"$PY" mt_nisqa_all.py --dirs "$BASE" --out _mt_nisqa.json >> "$LOG" 2>&1
echo "--- ⑤ 首轮择优 ---" >> "$LOG"
"$DPY" mt_score.py --ch ch4 --dirs "$BASE" --plan mt_plan3b.json >> "$LOG" 2>&1

IDS=$(cat _mt_fail_ch4.txt)
echo "--- ⑥ 补生成：$IDS ---" >> "$LOG"
"$PY" mt_gen.py --ch ch4 --plan mt_plan3b.json --seeds 2024  --outdir _mt_raw_s2024  --ids "$IDS" --rate-file _mt_rate_none.json >> "$LOG" 2>&1
"$PY" mt_gen.py --ch ch4 --plan mt_plan3b.json --seeds 31337 --outdir _mt_raw_s31337 --ids "$IDS" --rate-file _mt_rate_none.json >> "$LOG" 2>&1

echo "--- ⑦ 重评 ---" >> "$LOG"
"$ASRV" mt_asr_all.py --dirs "$BASE,$FIX" --out _mt_asr.json >> "$LOG" 2>&1
"$PY" mt_nisqa_all.py --dirs "$BASE,$FIX" --out _mt_nisqa.json >> "$LOG" 2>&1
"$DPY" mt_score.py --ch ch4 --dirs "$BASE,$FIX" --plan mt_plan3b.json >> "$LOG" 2>&1

echo "--- ⑧ 拼章 ---" >> "$LOG"
"$PY" mt_post.py --ch ch4 --plan mt_plan3b.json >> "$LOG" 2>&1

echo "--- ⑨ 质检 ---" >> "$LOG"
"$PY" mt_report.py --ch ch4 >> "$LOG" 2>&1
"$DPY" mt_consist.py --wav _mt_out/ch4.wav >> "$LOG" 2>&1
"E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i _mt_out/ch4.wav \
    -codec:a libmp3lame -b:a 128k _mt_out/ch4.mp3 >> "$LOG" 2>&1
"E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i _mt_out/ch4.wav -t 180 \
    -codec:a libmp3lame -b:a 128k _mt_ch4_head.mp3 >> "$LOG" 2>&1
"$PY" mt_page.py --out mt_review.html >> "$LOG" 2>&1

echo "=== ch4 done $(date '+%F %T') ===" >> "$LOG"
