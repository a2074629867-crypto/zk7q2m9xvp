#!/bin/bash
# 反复重试 uv sync：Windows 上 sdist 的 build/ 残留会触发 WinError 183，
# 每次清掉 builds-v0 + 对应 sdists 后重试即可通过。
cd /g/_setup/index-tts || exit 1
export PATH="/c/Users/86178/.local/bin:$PATH"
export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897
export UV_HTTP_TIMEOUT=300 UV_LINK_MODE=copy
CACHE="/c/Users/86178/AppData/Local/uv/cache"

for i in $(seq 1 8); do
  echo "===== ATTEMPT $i ====="
  uv sync > /g/_setup/_itts_sync_try.log 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then
    echo "SUCCESS on attempt $i"
    /g/_setup/index-tts/.venv/Scripts/python.exe -c "import torch;print('torch',torch.__version__)"
    exit 0
  fi
  # 找出这次失败的包名
  pkg=$(grep -aoE "Failed to build \`[^\`]+\`" /g/_setup/_itts_sync_try.log | head -1 | sed -E 's/.*`([^`]+)`.*/\1/')
  echo "failed: $pkg"
  rm -rf "$CACHE/builds-v0"
  if [ -n "$pkg" ]; then
    rm -rf "$CACHE/sdists-v9/pypi/$pkg"
  fi
  # 该包的临时构建目录
  find "$CACHE/sdists-v9" -maxdepth 4 -type d -name "*$pkg*" -exec rm -rf {} + 2>/dev/null
done
echo "GAVE UP"
tail -20 /g/_setup/_itts_sync_try.log
exit 1
