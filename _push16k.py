# -*- coding: utf-8 -*-
"""_push16k.py —— 把 16k 包切成 1.5MB 分片逐片上传，输出云端拼装命令。"""
import os, sys
sys.path.insert(0, "G:/_setup")
import rcc

SRC = "G:/_setup/_narr16k.tar.gz"
CH = 1300 * 1024

data = open(SRC, "rb").read()
parts = [data[i:i + CH] for i in range(0, len(data), CH)]
os.makedirs("G:/_setup/_parts", exist_ok=True)

urls = []
for i, p in enumerate(parts, 1):
    fn = "G:/_setup/_parts/p%02d.bin" % i
    open(fn, "wb").write(p)
    try:
        u = rcc.put_file(fn, "p%02d.bin" % i)
    except Exception as e:
        print("FAIL part %d: %s" % (i, e))
        continue
    urls.append(u)
    print("  part %d/%d ok  %.1fMB" % (i, len(parts), len(p) / 1024 / 1024), flush=True)

print("\nOK %d/%d 片" % (len(urls), len(parts)))
with open("G:/_setup/_parts/urls.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(urls))
print("urls -> G:/_setup/_parts/urls.txt")
