# -*- coding: utf-8 -*-
"""_cloud_pack.py —— 把本地参考库打成云端 voice_lib 包（voice 名以 lib 下标为准）。

为什么按 lib 下标命名：`Thomas_wary_2` 的物理文件名其实是 `Thomas_wary_3.wav`
（`_reg_refs2.py` 当初从 3 起编号）。人工按文件名猜必然错位，
所以云端一律用「lib 下标 → voice 名」，与 plan/voice 完全一致。

产物：
  _cloud_pack/voice_lib/*.wav   99 条（voice 名）
  _cloud_pack/prompt_text       <voice>|<text>
  _cloud_pack/voice_lib.tar.gz
"""
import json
import os
import shutil
import subprocess
import sys

HERE = "G:/_setup"
PKG = os.path.join(HERE, "_cloud_pack")
LIBD = os.path.join(PKG, "voice_lib")

lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
if os.path.isdir(PKG):
    shutil.rmtree(PKG)
os.makedirs(LIBD, exist_ok=True)

lines, n = [], 0
for role in sorted(lib):
    for emo in sorted(lib[role]):
        for k, it in enumerate(lib[role][emo], 1):
            p = it.get("path") if isinstance(it, dict) else it
            p = (p or "").replace("/", os.sep)
            text = (it.get("text") or "") if isinstance(it, dict) else ""
            if not p or not os.path.exists(p):
                print("缺文件", role, emo, k, p)
                continue
            voice = "%s_%s_%d" % (role, emo, k)
            shutil.copy2(p, os.path.join(LIBD, voice + ".wav"))
            lines.append("%s|%s" % (voice, " ".join(text.split())))
            n += 1

with open(os.path.join(PKG, "prompt_text"), "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")

tarp = os.path.join(PKG, "voice_lib.tar.gz")
subprocess.run(["tar", "-czf", tarp, "-C", PKG, "voice_lib", "prompt_text"], check=True)
print("打包 %d 条参考，%.1f MB" % (n, os.path.getsize(tarp) / 1e6))
print("缺文本的:", [l for l in lines if l.endswith("|")][:6])
