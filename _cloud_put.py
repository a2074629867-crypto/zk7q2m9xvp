# -*- coding: utf-8 -*-
"""_cloud_put.py —— 任意文件分片上传到 ntfy（单片 ≤1.85MB），输出云端取回命令。

用法：
  python _cloud_put.py <本地文件> [云端落地名]

实现：把文件按 1.85MB 切片，每片 PUT 到 ntfy 拿附件 URL，
再 cat 所有 URL 拼成一个 "curl ...; cat p*.bin > out" 的云端命令，直接打印。
"""
import json
import os
import sys
import urllib.request

LIMIT = 1_850_000
OUT = "https://ntfy.sh/tts_o7k2mq"

src = sys.argv[1]
name = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(src)
data = open(src, "rb").read()
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

urls = []
off, part = 0, 0
while off < len(data):
    chunk = data[off:off + LIMIT]
    part += 1
    ok = False
    for attempt in range(3):
        req = urllib.request.Request(OUT, data=chunk, method="PUT")
        req.add_header("Filename", "u%02d.bin" % part)
        req.add_header("Content-Type", "application/octet-stream")
        try:
            with op.open(req, timeout=300) as r:
                d = json.loads(r.read().decode())
            urls.append(d["attachment"]["url"])
            ok = True
            break
        except Exception as e:
            print("切片 %d 第 %d 次失败 %s" % (part, attempt + 1, e), file=sys.stderr)
    if not ok:
        raise SystemExit("切片 %d 上传失败" % part)
    off += LIMIT

print("文件 %s  %.2f MB  分 %d 片" % (name, len(data) / 1e6, part))
cmds = ["cd /home/aistudio/up && mkdir -p in && cd in"]
for k, u in enumerate(urls, 1):
    cmds.append("curl -sSL --max-time 180 -o u%02d.bin '%s'" % (k, u))
cmds.append("cat %s > %s && ls -l %s" % (
    " ".join("u%02d.bin" % k for k in range(1, part + 1)), name, name))
print("\n".join(cmds))
