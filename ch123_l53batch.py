# -*- coding: utf-8 -*-
"""L052/L053/L054 重生成：happy 标签导致 F0 飙到 300-445Hz（破音）。去 emo。"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

CASES = [
    ("L052", "I didn't want you to come here.", 7, [42, 44, 46, 48]),
    ("L053", "Why have you come here?", 5, [42, 44, 46, 48]),
    ("L054", "Why did you have to find somewhere new to live?", 10, [42, 44, 46, 48]),
]
LOCAL = "G:/_setup/_l53regen"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["E"]
for key, text, n, seeds in CASES:
    mt = max(240, n * 28 + 160)
    for sd in seeds:
        name = "%s_s%d.wav" % (key, sd)
        out_rel = "_l53regen/" + name
        out_abs = os.path.join(R.ACPP_DIR, out_rel)
        if os.path.exists(out_abs): os.remove(out_abs)
        t0 = time.time()
        cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
               "--backend", "vulkan", "--threads", "2",
               "--voice-ref", ref, "--reference-text", rt, "--text", text,
               "--request-option", "max_tokens=%d" % mt, "--seed", str(sd),
               "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=R.ACPP_DIR)
        ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 50000
        if ok: shutil.copy2(out_abs, os.path.join(LOCAL, name))
        print("%-5s seed%-3d %s %.0fs" % (key, sd, "OK" if ok else "FAIL", time.time()-t0), flush=True)
print("DONE")
