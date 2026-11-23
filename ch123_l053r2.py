# -*- coding: utf-8 -*-
"""L053 重生成：happy 已去掉（破音根因），但 5 词短句原始语速 370wpm，
   拉伸 0.70 后声纹从 0.69 掉到 0.38。策略：多扫 seed，挑「原始语速最接近 258」的，
   让拉伸幅度最小。
"""
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

TEXT = "Why have you come here?"
SEEDS = [50, 51, 52, 53, 54, 55, 56, 57]
LOCAL = "G:/_setup/_l053r2"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["E"]

for sd in SEEDS:
    name = "L053_s%d.wav" % sd
    out_rel = "_l053r2/" + name
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs):
        os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", TEXT,
           "--request-option", "max_tokens=300", "--seed", str(sd),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 50000
    if ok:
        shutil.copy2(out_abs, os.path.join(LOCAL, name))
    print("seed%-3d %s %.0fs" % (sd, "OK" if ok else "FAIL", time.time() - t0), flush=True)
print("DONE")
