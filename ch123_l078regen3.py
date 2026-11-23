# -*- coding: utf-8 -*-
"""L078 But：必须让 But 独立成句（后面句号），/t/ 才会闭合。
之前 "But it had to be sold." 里 /t/ 和 it 连读，任何切点都会带出 "it"。
"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

CASES = [
    ("E", "But. No.", 42, 280),
    ("E", "But. No.", 44, 280),
    ("E", "But. No.", 46, 280),
    ("F", "But no.", 42, 260),
    ("F", "But no.", 44, 260),
    ("G", "No. But.", 42, 280),
    ("G", "No. But.", 44, 280),
]
LOCAL = "G:/_setup/_l078r3"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["C"]
for tag, text, seed, mt in CASES:
    name = "L078_%s_s%d.wav" % (tag, seed)
    out_rel = "_l078r3/" + name
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
    print("%s seed%-3d %s %5.0fs | %s" % (tag, seed, "OK  " if ok else "FAIL",
                                          time.time() - t0, text), flush=True)
print("DONE")
