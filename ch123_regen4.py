# -*- coding: utf-8 -*-
"""重生成 0.7 倍也压不下来的 4 条（GPU 走 mem_saver + threads=2）。"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

OUT = "G:/_setup/_regen"
os.makedirs(OUT, exist_ok=True)

CASES = [
    ("L061", "In a flat.", 3, [42, 44, 46]),
    ("L071", "I don't know.", 3, [42, 44, 46]),
    ("L050", "Oh, what is it? What have you found?", 8, [42, 44]),
    ("L084", "When did he die, I said.", 6, [42, 44]),
]
WHO = {"L061": "C", "L071": "C", "L050": "C", "L084": "E"}

for key, text, n, seeds in CASES:
    ref, rt = REFS[WHO[key]]
    mt = max(220, n * 26 + 160)
    for sd in seeds:
        out = os.path.join(OUT, "%s_s%d.wav" % (key, sd))
        t0 = time.time()
        cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
               "--backend", "vulkan", "--threads", "2",
               "--voice-ref", ref, "--reference-text", rt, "--text", text,
               "--request-option", "max_tokens=%d" % mt, "--seed", str(sd),
               "--out", out, "--session-option", "dots_tts.mem_saver=true"]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=R.ACPP_DIR)
        ok = os.path.exists(out) and os.path.getsize(out) > 40000
        print("%-5s seed%-3d %s %.0fs %d" % (key, sd, "OK" if ok else "FAIL",
                                             time.time() - t0,
                                             os.path.getsize(out) if ok else 0), flush=True)
        if not ok:
            tail = (r.stdout + r.stderr).strip().splitlines()[-2:]
            print("     ", " | ".join(tail), flush=True)
