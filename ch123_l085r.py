# -*- coding: utf-8 -*-
"""L085 重生成：末段 "Or six." 85% 能量在 4kHz 以上（是气流噪声不是人声），
HNR -9.4dB。原版打的是 sad。
"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

TEXT = "A few years ago. I was about five. Or six."
SEEDS = [42, 44, 46, 48, 50, 52]
LOCAL = "G:/_setup/_l085r"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["C"]
for sd in SEEDS:
    name = "L085_s%d.wav" % sd
    out_rel = "_l085r/" + name
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs): os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", TEXT,
           "--request-option", "max_tokens=400", "--seed", str(sd),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 60000
    if ok: shutil.copy2(out_abs, os.path.join(LOCAL, name))
    print("seed%-3d %s %.0fs" % (sd, "OK" if ok else "FAIL", time.time()-t0), flush=True)
print("DONE")
