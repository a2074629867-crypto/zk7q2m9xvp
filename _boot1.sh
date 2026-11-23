#!/bin/bash
# 云端引导：只做「看清楚 + 解包」，不做长任务
cd /mnt/workspace/acpp || exit 1
sz() { stat -c%s "$1" 2>/dev/null || echo 0; }
echo "SIZE pkg=$(sz pkg.tgz) gguf=$(sz dots.gguf) bundle=$(sz bundle.tgz)"

if [ ! -d dist ]; then
  mkdir -p dist && tar -xzf pkg.tgz -C dist 2>/dev/null && echo "EXTRACT pkg ok"
else
  echo "EXTRACT pkg cached"
fi
echo "BINS $(find dist -maxdepth 2 -type f -name 'audiocpp*' -printf '%p:%s ' 2>/dev/null)"
echo "TOPLIB $(find dist -maxdepth 2 -type d -printf '%p ' 2>/dev/null | head -c 200)"

if [ ! -d cloud ]; then
  tar -xzf bundle.tgz 2>/dev/null && echo "EXTRACT bundle ok"
fi
echo "CLOUD $(ls cloud 2>/dev/null | tr '\n' ' ')"
echo "DONE stage1"
