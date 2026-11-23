# -*- coding: utf-8 -*-
"""L083 修复：'father' 尾音被硬切。

实测 6 个 seed 结尾全部在 5ms 内从 -40dB 掉到 -93dB —— dots.tts 整段输出尾部硬切，
没有自然衰减。ASR 能识别 father，但韵尾 /ə/ 被砍，听感是"没读完就断了"。

解法：生成时在 father 后面接一个尾随短语，让模型把 father 念完并自然过渡，
再按静音切掉尾随部分。
"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

CASES = [
    ("t1", "Here's the picture. Look, that's my father. Yes."),
    ("t2", "Here's the picture. Look, that's my father, you know."),
    ("t3", "Here's the picture. Look, that's my father. He's old."),
    ("t4", "Here's the picture. Look, that's my father, isn't it."),
]
SEEDS = [42, 44]
LOCAL = "G:/_setup/_l083tail"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["C"]
for tag, text in CASES:
    for sd in SEEDS:
        name = "L083_%s_s%d.wav" % (tag, sd)
        out_rel = "_l083tail/" + name
        out_abs = os.path.join(R.ACPP_DIR, out_rel)
        if os.path.exists(out_abs):
            os.remove(out_abs)
        t0 = time.time()
        cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
               "--backend", "vulkan", "--threads", "2",
               "--voice-ref", ref, "--reference-text", rt, "--text", text,
               "--request-option", "max_tokens=400", "--seed", str(sd),
               "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=R.ACPP_DIR)
        ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 60000
        if ok:
            shutil.copy2(out_abs, os.path.join(LOCAL, name))
        print("%-4s seed%-3d %s %.0fs" % (tag, sd, "OK" if ok else "FAIL", time.time() - t0), flush=True)
print("DONE")
