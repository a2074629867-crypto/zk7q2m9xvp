# -*- coding: utf-8 -*-
"""L068 + L083 重生成。

L068: "We can't help that." 第二句音色变怪物 —— 用户明确要求重新生成。
      判据：逐段声纹，第二段必须 >=0.60（之前 s42 只有 0.539）。
L083: "father" 尾音硬切 —— 生成时接尾随短语，让模型把 father 念完再切掉。
"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

def run(tag_dir, name, text, ref, rt, mt, seed):
    out_rel = "%s/%s" % (tag_dir, name)
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs):
        os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", text,
           "--request-option", "max_tokens=%d" % mt, "--seed", str(seed),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 60000
    if ok:
        shutil.copy2(out_abs, os.path.join("G:/_setup", tag_dir, name))
    print("%-22s %s %.0fs" % (name, "OK" if ok else "FAIL", time.time() - t0), flush=True)
    return ok

# ---------- L068：整条重生成，扫 8 个 seed ----------
L068 = "Well, my mother can't afford to buy us a house, can she? We can't help that."
ref, rt = REFS["C"]
os.makedirs("G:/_setup/_l068r2", exist_ok=True)
for sd in [42, 43, 44, 45, 46, 47, 48, 49]:
    run("_l068r2", "L068_s%d.wav" % sd, L068, ref, rt, 480, sd)

# ---------- L083：接尾随短语 ----------
os.makedirs("G:/_setup/_l083tail", exist_ok=True)
CASES = [
    ("t1", "Here's the picture. Look, that's my father. Yes."),
    ("t2", "Here's the picture. Look, that's my father, you know."),
    ("t3", "Here's the picture. Look, that's my father. He's old."),
]
for tag, text in CASES:
    for sd in [42, 44, 46]:
        run("_l083tail", "L083_%s_s%d.wav" % (tag, sd), text, ref, rt, 420, sd)

print("DONE")
