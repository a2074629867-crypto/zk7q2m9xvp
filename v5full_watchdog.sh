#!/bin/bash
# v5full_watchdog.sh —— 监测 GSV 训练，完成后自动跑克隆验证 + 生成试听页 + 写日志
#
# 用法：bash /g/_setup/v5full_watchdog.sh   （建议 run_in_background）
set -u

LOG=/g/_setup/v5full_train_df3hp.log
WL=/g/_setup/_watchdog.log
REPO=/g/_setup/gsv5probe
OUT=E:/tts-models/acpp/out/v5ft
MEM="C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/.workbuddy/memory/2026-10-17.md"

say(){ echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$WL"; }

: > "$WL"
say "===== watchdog 启动 (PID $$) ====="
say "监视日志: $LOG"
say "等待标志: ALLDONE"

# ---------- 阶段 1：等训练完成 ----------
T=0; MAX=21600          # 最长等 6 小时
FOUND=0; ZERO=0
while [ $T -lt $MAX ]; do
  if grep -q "ALLDONE" "$LOG" 2>/dev/null; then FOUND=1; break; fi
  # 异常早退：连续 5 分钟没有 python 进程，且日志无 ALLDONE
  NP=$(tasklist 2>/dev/null | grep -c "python.exe")
  if [ "$NP" -eq 0 ]; then ZERO=$((ZERO+1)); else ZERO=0; fi
  if [ "$ZERO" -ge 5 ]; then
    say "!! 连续 5 分钟无 python 进程且无 ALLDONE —— 判定异常终止"
    tail -40 "$LOG" >> "$WL" 2>&1
    {
      echo ""
      echo "## ⚠️ GSV v5turbo 训练异常终止（$(date '+%m-%d %H:%M')，watchdog 检测）"
      echo ""
      echo "- 日志无 ALLDONE 且 python 进程已退出 ⇒ 训练中途挂了"
      echo "- 日志尾部见 \`_watchdog.log\`"
      echo ""
      echo '```'
      tail -25 "$LOG" 2>/dev/null
      echo '```'
    } >> "$MEM" 2>/dev/null
    exit 3
  fi
  sleep 60; T=$((T+60))
  if [ $((T % 600)) -eq 0 ]; then
    LAST=$(tail -c 200 "$LOG" 2>/dev/null | tr '\r' '\n' | grep -v '^[[:space:]]*$' | tail -1 | cut -c1-90)
    say "等待中 ${T}s | ${LAST}"
  fi
done

if [ $FOUND -ne 1 ]; then
  say "!! 超时 ${MAX}s 仍未出现 ALLDONE —— 检查日志尾部"
  tail -40 "$LOG" >> "$WL" 2>&1
  exit 2
fi
say "检测到 ALLDONE，训练脚本已跑完"

# ---------- 阶段 2：等 python 主进程退出（确保权重落盘） ----------
for i in $(seq 1 40); do
  N=$(tasklist 2>/dev/null | grep -c "python.exe")
  [ "$N" -eq 0 ] && break
  sleep 15
done
sleep 20
say "python 进程残留: $(tasklist 2>/dev/null | grep -c 'python.exe')"

# ---------- 阶段 3：清点权重 ----------
NS2=$(ls -1 "$REPO"/SoVITS_weights_v5turbo/mcconaughey_v5full_df3hp_e*_l32.pth 2>/dev/null | wc -l)
NS1=$(ls -1 "$REPO"/GPT_weights_v5turbo/mcconaughey_v5full_df3hp-e*.ckpt 2>/dev/null | wc -l)
say "权重清点: SoVITS ${NS2} 个 (期望 8) | GPT ${NS1} 个 (期望 15)"
ls -lt --time-style=+%m-%d_%H:%M "$REPO"/SoVITS_weights_v5turbo/ >> "$WL" 2>&1
ls -lt --time-style=+%m-%d_%H:%M "$REPO"/GPT_weights_v5turbo/ >> "$WL" 2>&1

# 训练失败标志检测
if grep -q "Traceback" "$LOG" 2>/dev/null; then
  say "!! 日志含 Traceback："
  grep -n -A6 "Traceback" "$LOG" | tail -40 >> "$WL" 2>&1
fi

# ---------- 阶段 4：克隆验证 ----------
say "=========== 开始克隆验证（零样本 vs 微调）==========="
mkdir -p "$OUT"
bash /g/_setup/gsv5_ft_verify.sh >> "$WL" 2>&1
VE=$?
say "gsv5_ft_verify.sh 退出码 = $VE"

# ---------- 阶段 5：生成试听页 ----------
say "=========== 生成试听页 ==========="
G:/Python310/python.exe -u /g/_setup/build_v5ft_page.py >> "$WL" 2>&1
PE=$?
say "build_v5ft_page.py 退出码 = $PE"

# ---------- 阶段 6：写 memory ----------
{
  echo ""
  echo "## ★ GSV v5turbo 微调完成 + 克隆验证（$(date '+%m-%d %H:%M')，watchdog 自动执行）"
  echo ""
  echo "- 训练：SoVITS LoRA r32 8ep（${NS2} 个权重）+ GPT 15ep（${NS1} 个权重）"
  echo "- 验证：零样本 vs 微调，同文同参考同 seed(42)"
  echo "- 声纹锚点：真人 \`real_trim.wav\`（29.41s）"
  echo "- 产物：\`$OUT\`（base_1/base_0p88/ft_1/ft_0p88 .wav + summary.json）"
  echo "- 试听页：\`reader/_voice_lab/listen_v5ft.html\`"
  echo ""
  echo '```'
  grep -E "声纹|相似度|基准|最像|\[ok\]|\[FAIL\]" "$WL" | tail -30
  echo '```'
} >> "$MEM" 2>/dev/null
say "已写入 memory: $MEM"

say "===== watchdog 结束 (verify=$VE page=$PE) ====="
echo "WATCHDOG_DONE verify=$VE page=$PE"
exit 0
