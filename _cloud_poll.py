# -*- coding: utf-8 -*-
"""_cloud_poll.py —— 轮询云端推到 filebin 的日志/产物，免截图。

用法：
  python _cloud_poll.py --bin mtdots1030k7 --file run.log --timeout 600
  python _cloud_poll.py --bin mtdots1030k7 --wait done.json     # 等到产物出现
  python _cloud_poll.py --bin mtdots1030k7 --file run.log --tail 25
"""
import argparse
import sys
import time
import urllib.error
import urllib.request

PROXY = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}


def opener():
    if args.no_proxy:
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler(PROXY))


def fetch(url, method="GET"):
    req = urllib.request.Request(url, method=method)
    try:
        with OP.open(req, timeout=45) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return -1, str(e).encode()


ap = argparse.ArgumentParser()
ap.add_argument("--bin", required=True)
ap.add_argument("--file", default="run.log")
ap.add_argument("--wait", default="", help="只等这个文件出现（HEAD），出现即退出")
ap.add_argument("--timeout", type=int, default=600)
ap.add_argument("--interval", type=int, default=20)
ap.add_argument("--tail", type=int, default=20)
ap.add_argument("--no-proxy", action="store_true")
args = ap.parse_args()

OP = opener()
base = "https://filebin.net/" + args.bin

if args.wait:
    t0 = time.time()
    n = 0
    while time.time() - t0 < args.timeout:
        st, _ = fetch(base + "/" + args.wait, "HEAD")
        n += 1
        print("[%3ds] %s -> %s" % (time.time() - t0, args.wait, st), flush=True)
        if st == 200:
            sys.exit(0)
        time.sleep(args.interval)
    print("超时未出现: %s" % args.wait, file=sys.stderr)
    sys.exit(1)

t0 = time.time()
last = None
while time.time() - t0 < args.timeout:
    st, body = fetch(base + "/" + args.file)
    if st == 200:
        txt = body.decode("utf-8", "replace")
        if txt != last:
            last = txt
            lines = [l for l in txt.splitlines() if l.strip()]
            print("---- %s @%ds (%d 行) ----" % (args.file, time.time() - t0, len(lines)))
            for l in lines[-args.tail:]:
                print(l)
            sys.stdout.flush()
    else:
        print("[%3ds] %s -> %s（尚未推出）" % (time.time() - t0, args.file, st), flush=True)
    time.sleep(args.interval)
print("轮询结束")
