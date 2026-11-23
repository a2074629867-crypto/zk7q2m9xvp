# -*- coding: utf-8 -*-
"""_cloud_upl_cand.py —— 把候选参考（任意 voice/path/text）打包分片上传。

用法：python _cloud_upl_cand.py _loud_refs.json
输入 json: [{"voice": "Thomas_loud_6", "path": "G:/.../c286_p2.wav", "text": "..."}]
输出：_cloud_up2/voice_lib.tar.gz + 云端取回命令（打印）
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request

HERE = "G:/_setup"
PKG = os.path.join(HERE, "_cloud_up2")
LIMIT = 1_850_000
OUT = "https://ntfy.sh/tts_o7k2mq"

spec = json.load(open(sys.argv[1], encoding="utf-8"))
if os.path.isdir(PKG):
    shutil.rmtree(PKG)
WORK = os.path.join(PKG, "voice_lib")
os.makedirs(WORK, exist_ok=True)

lines, total = [], 0
for it in spec:
    p = (it["path"] or "").replace("/", os.sep)
    if not os.path.exists(p):
        print("缺文件", it["voice"], p)
        continue
    shutil.copy2(p, os.path.join(WORK, it["voice"] + ".wav"))
    lines.append("%s|%s" % (it["voice"], " ".join((it.get("text") or "").split())))
    total += os.path.getsize(p)
with open(os.path.join(PKG, "prompt_text"), "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")

tarp = os.path.join(PKG, "voice_lib.tar.gz")
subprocess.run(["tar", "-czf", tarp, "-C", PKG, "voice_lib", "prompt_text"], check=True)
data = open(tarp, "rb").read()
print("%d 条，原 %.1f MB，压缩 %.1f MB" % (len(lines), total / 1e6, len(data) / 1e6))

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urls, off, part = [], 0, 0
while off < len(data):
    chunk = data[off:off + LIMIT]
    part += 1
    for attempt in range(3):
        req = urllib.request.Request(OUT, data=chunk, method="PUT")
        req.add_header("Filename", "c%02d.bin" % part)
        req.add_header("Content-Type", "application/octet-stream")
        try:
            with op.open(req, timeout=300) as r:
                urls.append(json.loads(r.read().decode())["attachment"]["url"])
            break
        except Exception as e:
            if attempt == 2:
                raise SystemExit("切片 %d 失败 %s" % (part, e))
    off += LIMIT

cmds = ["cd /home/aistudio && mkdir -p up2 && cd up2"]
for k, u in enumerate(urls, 1):
    cmds.append("curl -sSL --max-time 180 -o c%02d.bin '%s'" % (k, u))
cmds.append("cat %s > all.tgz" % " ".join("c%02d.bin" % k for k in range(1, part + 1)))
cmds.append("rm -rf voice_lib && tar xzf all.tgz && ls voice_lib | wc -l")
print("\n".join(cmds))
