# -*- coding: utf-8 -*-
"""L050 重生成：原速 375wpm 太快，重生成版 COL 只有 2.17（音色染色）。
多扫 seed，选 COL 高且语速接近 260 的。"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, "G:/_setup")
import bk_resplit as R
from ch123_plan import REFS

TEXT = "Oh, what is it? What have you found?"
SEEDS = [50, 52, 54, 56, 58, 60]
LOCAL = "G:/_setup/_l050r"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["C"]
for sd in SEEDS:
    name = "L050_s%d.wav" % sd
    out_rel = "_l050r/" + name
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs): os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", TEXT,
           "--request-option", "max_tokens=320", "--seed", str(sd),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 50000
    if ok: shutil.copy2(out_abs, os.path.join(LOCAL, name))
    print("seed%-3d %s %.0fs" % (sd, "OK" if ok else "FAIL", time.time()-t0), flush=True)
print("DONE")
