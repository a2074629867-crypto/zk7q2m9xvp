# -*- coding: utf-8 -*-
"""L051 验证：'Nothing, it's nothing. It's only a pebble.' 首段 268Hz 比后两段高 52Hz。
确认这是不是 calm 标签造成的（如果 3 个 seed 都回到 210-230，说明现在的偏了）。
"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

TEXT = "Nothing, it's nothing. It's only a pebble."
SEEDS = [42, 44, 46]
LOCAL = "G:/_setup/_l051r"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["E"]
for sd in SEEDS:
    name = "L051_s%d.wav" % sd
    out_rel = "_l051r/" + name
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs): os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", TEXT,
           "--request-option", "max_tokens=360", "--seed", str(sd),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 60000
    if ok: shutil.copy2(out_abs, os.path.join(LOCAL, name))
    print("seed%-3d %s %.0fs" % (sd, "OK" if ok else "FAIL", time.time()-t0), flush=True)
print("DONE")
