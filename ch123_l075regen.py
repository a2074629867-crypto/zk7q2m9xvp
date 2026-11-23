# -*- coding: utf-8 -*-
"""L075 口吃段重生成：'I've got...' 的 got 要拖长（省略号=拖音）。

只重生成后两段（I've got... / I've got a picture of him.），前 3 段不动。
"""
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

TEXTS = {
    "dot":  "I've got... I've got a picture of him.",
    "oo":   "I've gooot... I've got a picture of him.",
    "dash": "I've go\u2014t... I've got a picture of him.",
}
SEEDS = [42, 44, 46, 48, 50]
LOCAL = "G:/_setup/_l075regen"
os.makedirs(LOCAL, exist_ok=True)

ref, rt = REFS["C"]
for tag, text in TEXTS.items():
    for sd in SEEDS:
        name = "L075_%s_s%d.wav" % (tag, sd)
        out_rel = "_l075regen/" + name
        out_abs = os.path.join(R.ACPP_DIR, out_rel)
        if os.path.exists(out_abs):
            os.remove(out_abs)
        t0 = time.time()
        cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
               "--backend", "vulkan", "--threads", "2",
               "--voice-ref", ref, "--reference-text", rt, "--text", text,
               "--request-option", "max_tokens=300", "--seed", str(sd),
               "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=R.ACPP_DIR)
        ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 50000
        if ok:
            shutil.copy2(out_abs, os.path.join(LOCAL, name))
        print("%-5s seed%-3d %s %.0fs %d" % (tag, sd, "OK" if ok else "FAIL",
                                             time.time() - t0,
                                             os.path.getsize(out_abs) if ok else 0), flush=True)
        if not ok:
            print("     ", " | ".join((r.stdout + r.stderr).strip().splitlines()[-2:]), flush=True)
print("DONE")
