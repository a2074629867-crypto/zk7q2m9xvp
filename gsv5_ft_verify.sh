#!/bin/bash
# gsv5_ft_verify.sh —— 训练完成后：零样本 vs 微调 克隆效果对比
#
# 做三件事：
#   1. 零样本基线推理（底模 s2Gv5turbo + s1v3）
#   2. 微调版推理（e8 LoRA + GPT e15）
#   3. 声纹对比（anchor = real_trim.wav，真人同段）+ 汇总 json
#
# 用法：bash /g/_setup/gsv5_ft_verify.sh
set -u

export PATH="/e/tool/oopz:$PATH"
export NLTK_DATA=G:/nltk_data
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY 2>/dev/null || true

PY310="G:/Python310/python.exe"
PYHOST="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
OUT="E:/tts-models/acpp/out/v5ft"
SPKDIR="C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab"
ANCHOR="G:/_setup/dots_test/_an_real_trim.wav"   # 真人 real_trim 48k 29.41s
REPO="G:/_setup/gsv5probe"

mkdir -p "$OUT"

# ---- 找最终权重（glob 最新）----
S2=$(ls -t "$REPO"/SoVITS_weights_v5turbo/mcconaughey_v5full_df3hp_e*_l32.pth 2>/dev/null | head -1)
S1=$(ls -t "$REPO"/GPT_weights_v5turbo/mcconaughey_v5full_df3hp-e*.ckpt 2>/dev/null | head -1)

echo "=========================================="
echo " 克隆验证：零样本 vs 微调"
echo "=========================================="
echo "SoVITS(微调): ${S2:-（未找到！）}"
echo "GPT(微调)   : ${S1:-（未找到！）}"
echo "参考音频    : G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav (8.3s)"
echo "声纹基准    : $ANCHOR"
echo

if [ -z "$S2" ] || [ -z "$S1" ]; then
  echo "[错误] 微调权重不齐，训练可能还没跑完。退出。"
  exit 1
fi

# ---- 1) 零样本基线 ----
echo ">>> [1/3] 零样本基线推理 ..."
"$PY310" -u /g/_setup/gsv5_ft_infer.py \
  --tag base --out "$OUT" --speeds 1.0,0.88 2>&1 | tail -12
echo

# ---- 2) 微调版 ----
echo ">>> [2/3] 微调版推理 ..."
"$PY310" -u /g/_setup/gsv5_ft_infer.py \
  --tag ft --out "$OUT" --speeds 1.0,0.88 \
  --vits "$S2" --t2s "$S1" 2>&1 | tail -12
echo

# ---- 3) 声纹对比 ----
echo ">>> [3/3] 声纹对比（anchor=real_trim 真人）..."
"$PYHOST" "$SPKDIR/spk_embed.py" "$ANCHOR" \
  "$OUT/base_1.wav" "$OUT/base_0p88.wav" \
  "$OUT/ft_1.wav"   "$OUT/ft_0p88.wav" 2>&1 | tail -15
echo

echo "=== 产物 ==="
ls -la "$OUT"/*.wav 2>/dev/null
echo
echo "[done] 试听页生成请另跑 build_v5ft_page.py"
