# -*- coding: utf-8 -*-
"""_cloud_tail.py —— 拉云端 run.log.gz 并解压显示尾部（只看，不投命令）。

  python _cloud_tail.py            # 尾部 60 行
  python _cloud_tail.py -n 200
  python _cloud_tail.py --file ENV_READY.gz
"""
import argparse
import gzip
import subprocess
import sys

BIN = "https://filebin.net/mtdots1030r2"
PROXY = "http://127.0.0.1:7897"

ap = argparse.ArgumentParser()
ap.add_argument("-n", type=int, default=60)
ap.add_argument("--file", default="run.log.gz")
ap.add_argument("--bin", default=BIN)
ap.add_argument("--proxy", default=PROXY)
ap.add_argument("--no-proxy", action="store_true")
a = ap.parse_args()

url = "%s/%s" % (a.bin, a.file)
cmd = ["curl", "-sL", "--max-time", "60", "-w", "\n%{http_code}", url]
if not a.no_proxy:
    cmd[1:1] = ["-x", a.proxy]
r = subprocess.run(cmd, capture_output=True, timeout=90)
raw = r.stdout or b""
idx = raw.rfind(b"\n")
code = raw[idx + 1:].strip().decode() if idx > 0 else "0"
body = raw[:idx] if idx > 0 else b""
print("[%s] HTTP %s  %d bytes" % (a.file, code, len(body)))
if code not in ("200", "302") or not body:
    sys.exit(1)
try:
    txt = gzip.decompress(body).decode("utf-8", "replace")
except Exception:
    txt = body.decode("utf-8", "replace")
lines = txt.splitlines()
print("---- 共 %d 行，显示末 %d ----" % (len(lines), a.n))
print("\n".join(lines[-a.n:]))
