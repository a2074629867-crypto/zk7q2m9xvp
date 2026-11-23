#!/usr/bin/env bash
# 从 hf-mirror 拉 GPT-SoVITS v2 所需的预训练模型
set -u
export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897
M="https://hf-mirror.com"
PM="/g/GPT-SoVITS/GPT_SoVITS/pretrained_models"
LOG="/g/_setup/log_models.txt"
: > "$LOG"

dl () {  # dl <url> <outfile>
  local url="$1" out="$2"
  mkdir -p "$(dirname "$out")"
  if [ -s "$out" ]; then
    echo "  已有 $(basename "$out") ($(stat -c%s "$out") bytes) 跳过" | tee -a "$LOG"
    return 0
  fi
  echo "  下载 $(basename "$out") ..." | tee -a "$LOG"
  curl -L -s --retry 5 --retry-delay 3 -C - -m 3600 -o "$out" "$url" >>"$LOG" 2>&1
  local rc=$?
  local sz=0; [ -f "$out" ] && sz=$(stat -c%s "$out")
  echo "    rc=$rc size=$sz" | tee -a "$LOG"
  return $rc
}

echo "=== 1/4 chinese-hubert-base (lj1995/GPT-SoVITS) ==="
for f in config.json preprocessor_config.json pytorch_model.bin; do
  dl "$M/lj1995/GPT-SoVITS/resolve/main/chinese-hubert-base/$f" "$PM/chinese-hubert-base/$f"
done

echo "=== 2/4 chinese-roberta-wwm-ext-large (hfl) ==="
for f in config.json pytorch_model.bin tokenizer.json tokenizer_config.json vocab.txt special_tokens_map.json; do
  dl "$M/hfl/chinese-roberta-wwm-ext-large/resolve/main/$f" "$PM/chinese-roberta-wwm-ext-large/$f"
done

echo "=== 3/4 s1 bert ckpt ==="
dl "$M/lj1995/GPT-SoVITS/resolve/main/s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt" \
   "$PM/s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt"

echo "=== 4/4 gsv-v2final-pretrained ==="
for f in s2G2333k.pth s2D2333k.pth s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt; do
  dl "$M/lj1995/GPT-SoVITS/resolve/main/gsv-v2final-pretrained/$f" "$PM/gsv-v2final-pretrained/$f"
done

echo "=== 结果 ===" | tee -a "$LOG"
find "$PM" -type f -size +1M -printf "%10s  %p\n" 2>/dev/null | tee -a "$LOG"
du -sh "$PM" 2>/dev/null | tee -a "$LOG"
echo "DONE" | tee -a "$LOG"
