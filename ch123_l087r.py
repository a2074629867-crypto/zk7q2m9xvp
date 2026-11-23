# -*- coding: utf-8 -*-
"""L087 重生成：'I don't know. Quite old, I suppose. Look, then, there's the photograph.'

问题（ch123_scan 检出）：p0 184Hz → p1 256Hz，邻段跳 72Hz；且 "Look, then," 段
比主干响 11dB。三条都打着 sad 标签 —— 短段打 emo 强度随机，这是老问题。
策略：去 emo，多扫 seed，按「邻段 F0 跳变最小 + 段间电平差最小」挑。
"""
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

TEXT = "I don't know. Quite old, I suppose. Look, then, there's the photograph."
SEEDS = [42, 44, 46, 48, 50, 52]
LOCAL = "G:/_setup/_l087r"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["C"]

for sd in SEEDS:
    name = "L087_s%d.wav" % sd
    out_rel = "_l087r/" + name
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs):
        os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", TEXT,
           "--request-option", "max_tokens=520", "--seed", str(sd),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 60000
    if ok:
        shutil.copy2(out_abs, os.path.join(LOCAL, name))
    print("seed%-3d %s %.0fs" % (sd, "OK" if ok else "FAIL", time.time() - t0), flush=True)
print("DONE")
