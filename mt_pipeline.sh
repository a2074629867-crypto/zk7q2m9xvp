#!/bin/bash
# mt_pipeline.sh —— 章优先全自动流水线
#   multi-seed 生成 → ASR → 择优 → 补生成 → 拼章 → 质检 → 试听页
# 全程可断点续跑：mt_gen 按 wav 完整性跳过、mt_asr_all 按路径跳过、mt_post 有缓存
set -u
cd /g/_setup || exit 1

PY="G:/Python310/python.exe"
DPY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
ASRV="./asr_venv/Scripts/python.exe"
LOG="_mt_pipe.log"
SEEDS="${SEEDS:-42,1234}"
PLAN="${PLAN:-mt_plan2.json}"       # 抽取计划（含 ch / text / gap）
SCENE="${SCENE:-mt_plan3.json}"     # 场景调过的停顿计划（拼章用）
CHAPTERS="${CHAPTERS:-ch1 ch2 ch3}"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_OFFLINE=1

echo "=== pipeline start $(date '+%F %T')  seeds=$SEEDS plan=$PLAN ===" >> "$LOG"

for ch in $CHAPTERS; do
  echo "--- $ch 生成 ---" >> "$LOG"
  "$PY" mt_gen.py --ch "$ch" --seeds "$SEEDS" --plan "$PLAN" >> "$LOG" 2>&1

  echo "--- $ch ASR ---" >> "$LOG"
  "$ASRV" mt_asr_all.py --dirs _mt_raw_s42,_mt_raw_s1234 --out _mt_asr.json >> "$LOG" 2>&1

  echo "--- $ch 择优 ---" >> "$LOG"
  "$DPY" mt_score.py --ch "$ch" --dirs _mt_raw_s42,_mt_raw_s1234 \
        --asr _mt_asr.json --plan "$PLAN" >> "$LOG" 2>&1

  FAILS=$(cat "_mt_fail_${ch}.txt" 2>/dev/null)
  if [ -n "${FAILS:-}" ]; then
    echo "--- $ch 补生成（第 3 个种子）：$FAILS ---" >> "$LOG"
    "$PY" mt_gen.py --ch "$ch" --seeds 777 --ids "$FAILS" --plan "$PLAN" >> "$LOG" 2>&1
    "$ASRV" mt_asr_all.py --dirs _mt_raw_s42,_mt_raw_s1234,_mt_raw_s777 --out _mt_asr.json >> "$LOG" 2>&1
    "$DPY" mt_score.py --ch "$ch" --dirs _mt_raw_s42,_mt_raw_s1234,_mt_raw_s777 \
          --asr _mt_asr.json --plan "$PLAN" >> "$LOG" 2>&1
  fi

  echo "--- $ch 拼章 ---" >> "$LOG"
  "$PY" mt_post.py --ch "$ch" --plan "$SCENE" >> "$LOG" 2>&1

  echo "--- $ch 质检 ---" >> "$LOG"
  "$PY" mt_report.py --ch "$ch" >> "$LOG" 2>&1
  if [ -f "_mt_out/${ch}.wav" ]; then
    "$DPY" mt_consist.py --wav "_mt_out/${ch}.wav" >> "$LOG" 2>&1
    "E:/tool/oopz/ffmpeg.exe" -hide_banner -loglevel error -y -i "_mt_out/${ch}.wav" \
           -codec:a libmp3lame -b:a 128k "_mt_out/${ch}.mp3" >> "$LOG" 2>&1
  fi
  "$PY" mt_page.py --out mt_review.html >> "$LOG" 2>&1
done

echo "=== pipeline done $(date '+%F %T') ===" >> "$LOG"
