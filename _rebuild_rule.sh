#!/bin/bash
cd /g/_setup
PY="G:/Python310/python.exe"
for ch in ch1 ch2 ch3; do
  echo "=== $ch ==="
  "$PY" -u mt_post.py --ch $ch --plan mt_plan3b.json 2>&1 | tail -5
done
