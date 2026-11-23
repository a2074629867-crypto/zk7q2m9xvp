#!/bin/bash
# v5full_post_retrain.sh —— GPT 重训完成后的全自动验证链
#   1) 等 v5full_gpt_retrain.log 出现 ALLDONE
#   2) 隔离测试（4 组合，确认时长正常）
#   3) 克隆验证（base vs ft，含声纹）
#   4) 生成试听页
set -u
LOG=/g/_setup/v5full_gpt_retrain.log
WLOG=/g/_setup/_post_retrain.log
say() { echo "[$(date +%H:%M:%S)] $*"; }

say "===== post-retrain 链启动 ====="

# ---- 1) 等重训完成 ----
T=0
while [ $T -lt 7200 ]; do
  if grep -q "ALLDONE" "$LOG" 2>/dev/null; then say "检测到 ALLDONE"; break; fi
  sleep 60; T=$((T+60))
  if [ $((T % 300)) -eq 0 ]; then
    LAST=$(tail -c 300 "$LOG" 2>/dev/null | tr '\r' '\n' | grep -v '^\s*$' | tail -1 | cut -c1-100)
    say "等待中 ${T}s | ${LAST}"
  fi
done
if ! grep -q "ALLDONE" "$LOG" 2>/dev/null; then say "超时未完成，退出"; exit 2; fi

# ---- 等 python 退出 + 缓冲 ----
for i in $(seq 1 30); do
  N=$(tasklist 2>/dev/null | grep -c "python.exe")
  [ "$N" -eq 0 ] && break
  sleep 10
done
sleep 20
say "python 进程: $(tasklist 2>/dev/null | grep -c 'python.exe')"

# ---- 2) 新 GPT 权重清点 ----
say "新 GPT 权重:"
ls -lt --time-style=+%H:%M "G:/_setup/gsv5probe/GPT_weights_v5turbo/" 2>/dev/null | head -20

# ---- 3) 隔离测试 ----
say "=========== 隔离测试（4 组合）==========="
bash /g/_setup/_run_iso.sh 2>&1 | grep -E "^\[ok\]|^>>>|^\[FAIL\]|^  [0-9]_|目标时长|Traceback|Error" | tail -20
say "隔离测试完成"

# ---- 4) 克隆验证 ----
say "=========== 克隆验证 ==========="
bash /g/_setup/gsv5_ft_verify.sh 2>&1 | tail -25
say "克隆验证完成"

# ---- 5) 试听页 ----
say "=========== 生成试听页 ==========="
G:/Python310/python.exe -u /g/_setup/build_v5ft_page.py 2>&1 | tail -15
say "试听页完成"

say "===== post-retrain 链结束 ====="
