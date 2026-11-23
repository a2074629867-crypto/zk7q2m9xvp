# -*- coding: utf-8 -*-
"""_cloud_cmd.py —— 向云端 watcher 投递一条命令并取回输出（免打字、免截图）。

原理：云端 watch_cmd.sh 每 8 秒拉一次 $BIN/cmd.gz，md5 变了就执行，
       结果 gzip 推到 $BIN/out.gz。

用法：
  python _cloud_cmd.py "pip install -q --no-deps importlib_resources"
  python _cloud_cmd.py --file _cmds/step1.sh --timeout 300
  python _cloud_cmd.py --wait-only          # 只看当前 out.gz
"""
import argparse
import gzip
import hashlib
import io
import sys
import time
import urllib.error
import urllib.request

PROXY = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
BIN = "https://filebin.net/mtdots1030r2"


def op(no_proxy=False):
    h = urllib.request.ProxyHandler({} if no_proxy else PROXY)
    return urllib.request.build_opener(h)


def get(o, url, timeout=45):
    """用 curl -L：filebin 返回 302 到 S3，urllib 在本机代理下不跟随。"""
    import subprocess
    cmd = ["curl", "-sL", "--max-time", str(int(timeout)), "-o", "-",
           "-w", "\n%{http_code}", url]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout + 20)
        raw = r.stdout or b""
        idx = raw.rfind(b"\n")
        code = raw[idx + 1:].strip().decode() if idx > 0 else "0"
        body = raw[:idx] if idx > 0 else b""
        return int(code) if code.isdigit() else 0, body
    except Exception as e:
        return -1, str(e).encode()


def put(o, url, data, ctype="application/gzip"):
    """用 curl 发 PUT：urllib 走本地代理 PUT 会报 Errno 2。"""
    import os
    import subprocess
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".gz")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        cmd = ["curl", "-s", "-X", "PUT", "--data-binary", "@" + tmp]
        # filebin 本机可直连；走本地代理 PUT 会失败（http_code 0）
        cmd += ["-H", "Content-Type: %s" % ctype, "-o", os.devnull,
                "-w", "%{http_code}", url]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = (r.stdout or "").strip()
        return int(out) if out.isdigit() else (out or r.stderr.strip()[:80])
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


ap = argparse.ArgumentParser()
ap.add_argument("cmd", nargs="?", default="")
ap.add_argument("--file")
ap.add_argument("--bin", default=BIN)
ap.add_argument("--timeout", type=int, default=240)
ap.add_argument("--wait-only", action="store_true")
ap.add_argument("--no-proxy", action="store_true")
a = ap.parse_args()

o = op(a.no_proxy)

if a.wait_only:
    st, body = get(o, a.bin + "/out.gz")
    print("out.gz ->", st)
    if body:
        sys.stdout.write(gzip.decompress(body).decode("utf-8", "replace"))
    sys.exit(0)

script = open(a.file, encoding="utf-8").read() if a.file else a.cmd
if not script.strip():
    raise SystemExit("没有命令")

# 取当前 out 指纹，用于判断「这次执行」产生了新输出
_, cur = get(o, a.bin + "/out.gz")
before = hashlib.md5(cur).hexdigest() if cur else ""

buf = io.BytesIO()
with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as f:
    f.write(script.encode("utf-8"))
blob = buf.getvalue()

print("投递 %d 字节命令 → %s" % (len(blob), a.bin + "/cmd.gz"))
st = put(o, a.bin + "/cmd.gz", blob)
print("PUT:", st)
if not isinstance(st, int) or st // 100 != 2:
    sys.exit(1)

t0 = time.time()
while time.time() - t0 < a.timeout:
    time.sleep(6)
    st, body = get(o, a.bin + "/out.gz")
    if st not in (200, 302) or not body:
        continue
    h = hashlib.md5(body).hexdigest()
    if h != before:
        try:
            txt = gzip.decompress(body).decode("utf-8", "replace")
        except Exception:
            txt = body.decode("utf-8", "replace")
        print("---- 云端输出（%.0fs）----" % (time.time() - t0))
        print(txt)
        sys.exit(0)
print("超时：%ds 内未见新输出" % a.timeout)
sys.exit(2)
