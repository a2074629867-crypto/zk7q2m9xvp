# -*- coding: utf-8 -*-
"""L085 合并版：6 个 seed 全部把 "Or six." 念成 85% 能量在 4kHz 以上的气流噪声
（HNR −4~−10dB）。这是模型对「独立超短句」的固定行为。
试把 "Or six." 并进前一句（同一句话内用逗号），看噪声段是否消失。
"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

TEXT = "A few years ago. I was about five, or six."
SEEDS = [42, 44, 46]
LOCAL = "G:/_setup/_l085m"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["C"]
for sd in SEEDS:
    name = "L085m_s%d.wav" % sd
    out_rel = "_l085m/" + name
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
