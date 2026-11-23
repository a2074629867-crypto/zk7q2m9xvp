# -*- coding: utf-8 -*-
"""L078 同源重生成：`No. But...` 的 No 和 But 现在来自两次不同生成，
COL 只有 2.92（NISQA 判定音色染色）。改成从同一句话里切两段。

历史上 `No. But...` 整句必崩（只吐 0.11s 弱音），
所以带内容生成（"No, but it had to be sold."），再把 No 和 But 切出来。
"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, "G:/_setup")
import bk_resplit as R
from ch123_plan import REFS

CASES = [
    ("A", "No, but it had to be sold.", 42),
    ("A", "No, but it had to be sold.", 44),
    ("A", "No, but it had to be sold.", 46),
    ("B", "No. But it had to be sold.", 42),
    ("B", "No. But it had to be sold.", 44),
    ("B", "No. But it had to be sold.", 46),
]
LOCAL = "G:/_setup/_l078same"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["C"]

for tag, text, seed in CASES:
    name = "L078_%s_s%d.wav" % (tag, seed)
    out_rel = "_l078same/" + name
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs):
        os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", text,
           "--request-option", "max_tokens=380", "--seed", str(seed),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 50000
    if ok:
        shutil.copy2(out_abs, os.path.join(LOCAL, name))
    print("%s seed%-3d %s %5.0fs | %s" % (tag, seed, "OK  " if ok else "FAIL",
                                          time.time() - t0, text), flush=True)
print("DONE")
