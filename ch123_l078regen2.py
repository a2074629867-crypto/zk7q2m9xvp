# -*- coding: utf-8 -*-
"""L078 慢速 But 重生成。

问题：现版 But 是从 L070 剪来的 0.23s 短音，rubberband tempo=0.30（拉 3.3 倍）
      把 HNR 从 11.3dB 打到 4.1dB —— 这就是用户听到的炸音。
结论：不能再靠拉伸，必须让模型自己念慢。

候选策略：
  A. "No. But I don't know."        —— 给 But 后续上下文，切出前两段
  B. "No. But it had to be sold."   —— 同上
  C. "<rate, factor=0.75>No. But...</rate>" —— 试 rate 标签（未验证是否生效）
  D. "No. But..."                   —— 原写法对照

GPU 单任务：threads=2 + mem_saver=true
"""
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

CASES = [
    ("A", "No. But I don't know.", 42, 300),
    ("A", "No. But I don't know.", 44, 300),
    ("B", "No. But it had to be sold.", 42, 340),
    ("B", "No. But it had to be sold.", 46, 340),
    ("C", "<rate, factor=0.75>No. But...</rate>", 42, 280),
    ("C", "<rate, factor=0.75>No. But...</rate>", 44, 280),
    ("D", "No. But...", 42, 260),
    ("D", "No. But...", 44, 260),
]

LOCAL = "G:/_setup/_l078r2"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["C"]

for tag, text, seed, mt in CASES:
    name = "L078_%s_s%d.wav" % (tag, seed)
    out_rel = "_l078r2/" + name
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs):
        os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", text,
           "--request-option", "max_tokens=%d" % mt, "--seed", str(seed),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 40000
    if ok:
        shutil.copy2(out_abs, os.path.join(LOCAL, name))
    print("%s seed%-3d %s %5.0fs %d  | %s"
          % (tag, seed, "OK  " if ok else "FAIL", time.time() - t0,
             os.path.getsize(out_abs) if ok else 0, text), flush=True)
print("DONE")
