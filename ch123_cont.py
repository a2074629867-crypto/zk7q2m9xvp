# -*- coding: utf-8 -*-
"""L063 / L087 连贯性重做。

L063 "Yes. No. Well, it was in somebody's house."
  p1(No) 176Hz -> p2(Well) 208Hz，中间 0.35s 停顿 ⇒ 用户："no 和后面应该更连贯，语调差别好大"
  试：No 与 Well 用逗号连读 / 省略号 / 原写法换 seed

L087 "I don't know. Quite old, I suppose. Look, then, there's the photograph."
  p0 184Hz -> p1 256Hz，跳 72Hz(570 cent) ⇒ 用户："后面突然变语气和语调了，变化太大"
  试：首句并入下句（逗号）/ 省略号 / 原写法换 seed
"""
import os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

CASES = [
    # (key, tag, text, mt, seed)
    ("L063", "A", "Yes. No, well, it was in somebody's house.", 340, 42),
    ("L063", "A", "Yes. No, well, it was in somebody's house.", 340, 44),
    ("L063", "B", "Yes. No... well, it was in somebody's house.", 340, 42),
    ("L063", "C", "Yes. No. Well, it was in somebody's house.", 340, 42),
    ("L063", "C", "Yes. No. Well, it was in somebody's house.", 340, 44),
    ("L087", "A", "I don't know, quite old, I suppose. Look, then, there's the photograph.", 400, 42),
    ("L087", "A", "I don't know, quite old, I suppose. Look, then, there's the photograph.", 400, 44),
    ("L087", "B", "I don't know... quite old, I suppose. Look, then, there's the photograph.", 400, 42),
    ("L087", "B", "I don't know... quite old, I suppose. Look, then, there's the photograph.", 400, 44),
    ("L087", "C", "I don't know. Quite old, I suppose. Look, then, there's the photograph.", 400, 42),
]

LOCAL = "G:/_setup/_cont"
os.makedirs(LOCAL, exist_ok=True)
ref, rt = REFS["C"]

for key, tag, text, mt, sd in CASES:
    name = "%s_%s_s%d.wav" % (key, tag, sd)
    out_rel = "_cont/" + name
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    if os.path.exists(out_abs):
        os.remove(out_abs)
    t0 = time.time()
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", text,
           "--request-option", "max_tokens=%d" % mt, "--seed", str(sd),
           "--out", out_rel, "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=R.ACPP_DIR)
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 50000
    if ok:
        shutil.copy2(out_abs, os.path.join(LOCAL, name))
    print("%-5s %s s%-3d %s %5.0fs | %s" % (key, tag, sd, "OK  " if ok else "FAIL",
                                            time.time() - t0, text[:46]), flush=True)
print("DONE")
