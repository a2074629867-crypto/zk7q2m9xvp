# -*- coding: utf-8 -*-
"""重启后重生成：L061 换音色合格的慢版；L071 极短句改用「与下一句合并再切」。"""
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

LOCAL = "G:/_setup/_regen2"
os.makedirs(LOCAL, exist_ok=True)

# key, text, seeds, max_tokens, who
CASES = [
    ("L061", "In a flat.", [42, 43, 44, 45, 46, 47], 260, "C"),
    ("L071M", "I don't know. To pay off all his debts.", [42, 44, 46, 48], 380, "C"),
]

for key, text, seeds, mt, who in CASES:
    ref, rt = REFS[who]
    for sd in seeds:
        name = "%s_s%d.wav" % (key, sd)
        out_rel = "_regen2/" + name
        out_abs = os.path.join(R.ACPP_DIR, out_rel)
        if os.path.exists(out_abs):
            os.remove(out_abs)
        t0 = time.time()
        cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
               "--backend", "vulkan", "--threads", "2",
               "--voice-ref", ref, "--reference-text", rt, "--text", text,
               "--request-option", "max_tokens=%d" % mt, "--seed", str(sd),
               "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=R.ACPP_DIR)
        ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 40000
        if ok:
            shutil.copy2(out_abs, os.path.join(LOCAL, name))
        print("%-6s seed%-3d %s %.0fs %d" % (key, sd, "OK" if ok else "FAIL",
                                             time.time() - t0,
                                             os.path.getsize(out_abs) if ok else 0), flush=True)
        if not ok:
            tail = (r.stdout + r.stderr).strip().splitlines()[-2:]
            print("      ", " | ".join(tail), flush=True)
print("DONE")
