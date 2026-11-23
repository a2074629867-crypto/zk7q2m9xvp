#!/usr/bin/env bash
# 守护：等 GPT-SoVITS 训练跑完 -> 自动出样 + 打分 + 生成离线试听页
#
# ⚠️ 存活判定不能只看 train_*.log —— s1（PyTorch Lightning）的进度条**不落盘**，
#    日志会长时间不更新，只看日志会把"正在训练"误判成"已结束"（踩过）。
#    改为同时看**检查点目录 mtime**（SAVE_EVERY=2 → 约 5 分钟必然动一次）。
#
# 结束判定：
#   1) master 出现「全部完成」                    -> 正常结束
#   2) master 出现 失败/中止 且 静默>300s         -> 真失败
#   3) 所有信号静默 >1200s                       -> 判定结束
set -u
export PATH="/e/tool/oopz:$PATH"
export NLTK_DATA="G:/nltk_data" HF_HOME="G:/hf_cache" HF_ENDPOINT="https://hf-mirror.com"
export PYTHONUNBUFFERED=1
unset http_proxy https_proxy 2>/dev/null || true

MASTER=/g/_setup/train_master.log
MARK=/g/_setup/.post_done
LOCK=/g/_setup/.post_lock
EXP=/g/GPT-SoVITS/logs/mcconaughey_calm
exec >> /g/_setup/watch.log 2>&1

echo "=== watcher start $(date '+%F %T') ==="

gap_of() {   # 最近一次"有动静"距今多少秒（日志 + 检查点目录）
  local now last=0 m f
  now=$(date +%s)
  for f in /g/_setup/train_s2.log /g/_setup/train_s1.log \
           /g/GPT-SoVITS/GPT_weights_v2 /g/GPT-SoVITS/SoVITS_weights_v2 \
           "$EXP/logs_s1_v2/ckpt" "$EXP/logs_s2_v2"; do
    [ -e "$f" ] || continue
    m=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    [ "$m" -gt "$last" ] && last=$m
  done
  [ "$last" -eq 0 ] && { echo 999999; return; }
  echo $((now - last))
}

# --- 先等训练起来 ---
for i in $(seq 1 20); do
  g=$(gap_of)
  [ "$g" -lt 120 ] && { echo "$(date '+%T') 训练已活跃 (静默 ${g}s)"; break; }
  echo "$(date '+%T') 等训练启动中 (静默 ${g}s)"
  sleep 30
done

while :; do
  g=$(gap_of)
  if [ -f "$MASTER" ]; then
    if grep -q "全部完成" "$MASTER" 2>/dev/null; then echo "$(date '+%T') master=完成"; break; fi
    if [ "$g" -gt 300 ] && grep -qE "训练失败|失败，中止|中止" "$MASTER" 2>/dev/null; then
      echo "$(date '+%T') master=失败且已静默 ${g}s"; break
    fi
  fi
  echo "$(date '+%T') 训练中 静默 ${g}s"
  if [ "$g" -gt 1200 ]; then echo "$(date '+%T') 全部信号静默>20min，判定结束"; break; fi
  sleep 60
done

if [ -f "$MARK" ]; then echo "已有产物标记 $MARK，跳过"; exit 0; fi
if [ -f "$LOCK" ]; then echo "已有任务在跑，跳过"; exit 0; fi
touch "$LOCK"

echo "=== 开始后处理 $(date '+%F %T') ==="
/g/Python310/python.exe -u /g/_setup/post_train.py --out E:/tts-models/out/gsv
rc=$?
echo "post_train EXIT=$rc"
if [ "$rc" -eq 0 ]; then touch "$MARK"; fi
rm -f "$LOCK"
echo "=== 结束 $(date '+%F %T') ==="
