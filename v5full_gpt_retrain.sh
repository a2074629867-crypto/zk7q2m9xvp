#!/bin/bash
# v5full_gpt_retrain.sh —— 干净重训 GPT(s1)，不续训旧库 checkpoint
#
# 背景：s1_train.py:142-147 会 get_newest_ckpt() 自动从 ckpt/ 目录续训。
#       该目录里是上一轮【旧库代码】训出的 epoch=12/14 checkpoint，
#       旧库 AR 实现（t2s_model.py / t2s_lightning_module.py / optim.py / dataset.py）
#       与新库不同 ⇒ 旧权重灌进新架构 ⇒ loss 从 1169 反弹到 1885、输出被截断。
# 做法：清空 ckpt/ 目录 + 归档旧权重 ⇒ 从官方 s1v3.ckpt 重新训练。
set -u

REPO=/g/_setup/gsv5probe
PY="G:/Python310/python.exe"
EXP="mcconaughey_v5full_df3hp"
VER="v5turbo"
LOG=/g/_setup/v5full_gpt_retrain.log

export PATH="/e/tool/oopz:$PATH"
export NLTK_DATA=G:/nltk_data
export HF_HOME="C:/Users/86178/.cache/huggingface"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export version="$VER"
export EXP="$EXP"
export PYTHONUNBUFFERED=1

cd "$REPO" || exit 1
ts() { date +"%H:%M:%S"; }
say() { echo "[$(ts)] $*"; }

CKPT="logs/$EXP/logs_s1_$VER/ckpt"

say "===== GPT 干净重训开始 ====="
say "前置检查:"
[ -s "TEMP/tmp_s1.yaml" ] && say "  OK  TEMP/tmp_s1.yaml" || { say "  MISS tmp_s1.yaml"; exit 1; }
[ -s "logs/$EXP/6-name2semantic.tsv" ] && say "  OK  6-name2semantic.tsv ($(wc -l < logs/$EXP/6-name2semantic.tsv) 行)" || { say "  MISS semantic"; exit 1; }
[ -s "logs/$EXP/2-name2text.txt" ] && say "  OK  2-name2text.txt ($(wc -l < logs/$EXP/2-name2text.txt) 行)" || { say "  MISS phoneme"; exit 1; }
[ -s "GPT_SoVITS/pretrained_models/s1v3.ckpt" ] && say "  OK  s1v3.ckpt 底模" || { say "  MISS s1v3.ckpt"; exit 1; }

say "清理自动续训点: $CKPT"
ls -la "$CKPT" 2>/dev/null
rm -rf "$CKPT"
mkdir -p "$CKPT"
say "  已清空（原为旧库 checkpoint，会自动续训导致崩溃）"

say "归档旧库 GPT 权重 -> GPT_weights_$VER/_oldlib_broken/"
mkdir -p "GPT_weights_$VER/_oldlib_broken"
mv GPT_weights_$VER/$EXP-e*.ckpt "GPT_weights_$VER/_oldlib_broken/" 2>/dev/null
say "  归档完成，剩余: $(ls GPT_weights_$VER/*.ckpt 2>/dev/null | wc -l) 个 .ckpt"

say "=========== 训练 GPT（t2s, 15 epoch，从官方 s1v3 起）==========="
_CUDA_VISIBLE_DEVICES=0 hz=25hz "$PY" -s GPT_SoVITS/s1_train.py --config_file TEMP/tmp_s1.yaml
RC=$?
say "GPT 训练结束 (exit=$RC)"
ls -lt --time-style=+%H:%M "GPT_weights_$VER/" 2>/dev/null | head -20
say "ALLDONE"
