# -*- coding: utf-8 -*-
"""_push2.py —— 500KB 分片 + curl 直传 ntfy（绕开 413），生成云端拼装命令。"""
import json, os, subprocess, sys, concurrent.futures as cf

SRC = "G:/_setup/_narr16k.tar.gz"
OUT = "G:/_setup/_parts"
CH = 500 * 1024
TOPIC = "https://ntfy.envs.net/ttsx_o7k2mq"
CURL = r"C:/Windows/System32/curl.exe"

os.makedirs(OUT, exist_ok=True)
data = open(SRC, "rb").read()
parts = [data[i:i + CH] for i in range(0, len(data), CH)]
print("%d 片 × %.0fKB" % (len(parts), CH / 1024))


def up(args):
    i, p = args
    fn = os.path.join(OUT, "q%03d.bin" % i)
    open(fn, "wb").write(p)
    r = subprocess.run([CURL, "-s", "--max-time", "90", "-X", "PUT",
                        "-H", "Filename: q%03d.bin" % i,
                        "-H", "Content-Type: application/octet-stream",
                        "--data-binary", "@" + fn, TOPIC],
                       capture_output=True, text=True)
    try:
        return i, json.loads(r.stdout)["attachment"]["url"]
    except Exception:
        return i, None

urls = {}
with cf.ThreadPoolExecutor(4) as ex:
    for i, u in ex.map(up, list(enumerate(parts, 1))):
        if u:
            urls[i] = u
        print("  %d ok=%s" % (i, bool(u)), flush=True)

print("成功 %d/%d" % (len(urls), len(parts)))
if len(urls) == len(parts):
    seq = " ".join(urls[i] for i in sorted(urls))
    cmd = ('cd /home/aistudio && rm -rf in_narr all.bin && mkdir -p in_narr && '
           'for u in %s; do curl -sL "$u" >> all.bin; done && tar -xzf all.bin -C in_narr && '
           'ls in_narr | wc -l') % seq
    open("G:/_setup/_cloud_fetch.sh", "w", encoding="utf-8").write(cmd)
    print("云端命令 -> G:/_setup/_cloud_fetch.sh (%d 字符)" % len(cmd))
