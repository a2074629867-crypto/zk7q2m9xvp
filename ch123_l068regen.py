# -*- coding: utf-8 -*-
"""L068 整句重生成：第二句音色跑偏（段声纹 0.238），无 emo 扫 seed。"""
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

TEXT = "Well, my mother can't afford to buy us a house, can she? We can't help that."
SEEDS = [42, 43, 44, 45, 46, 47]
LOCAL = "G:/_setup/_l068regen"
os.makedirs(LOCAL, exist_ok=True)

ref, rt = REFS["C"]
for sd in SEEDS:
    name = "L068_s%d.wav" % sd
    out_rel = "_l068regen/" + name
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs):
        os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", TEXT,
           "--request-option", "max_tokens=420", "--seed", str(sd),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 60000
    if ok:
        shutil.copy2(out_abs, os.path.join(LOCAL, name))
    print("seed%-3d %s %.0fs %d" % (sd, "OK" if ok else "FAIL", time.time() - t0,
                                    os.path.getsize(out_abs) if ok else 0), flush=True)
    if not ok:
        print("     ", " | ".join((r.stdout + r.stderr).strip().splitlines()[-2:]), flush=True)
print("DONE")
