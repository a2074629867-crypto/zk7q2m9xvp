# -*- coding: utf-8 -*-
"""步数对重音的影响：固定 seed、固定文本、固定参考音频，只改 --num-inference-steps。

设计：
- 3 条句子（11 / 13 / 14 词，各含一个明确目标副词）
- 步数 6 / 8 / 10 / 16 / 24 / 32（8 步已有，不重跑）
- seed 固定 42 ⇒ 排除 seed 变量

输出 _step_test/{tag}_s{steps}.wav
"""
import os
import subprocess
import sys
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
OUT = "G:/_setup/_step_test"

CASES = [
    ("n0167", "Moonlight came through the window, coldly, on to the glass.", "coldly"),
    ("n0112", "He went forward quite deliberately, being sure of his way, and unafraid.", "deliberately"),
    ("n0194", "Edmund Hooper went slowly up the four flights of stairs to his own bedroom.", "slowly"),
]

STEPS = [6, 10, 16, 24]


def run(tag, text, steps):
    out = os.path.join(OUT, "%s_s%d.wav" % (tag, steps))
    if os.path.exists(out) and os.path.getsize(out) > 10000:
        print("%-14s skip (exists)" % os.path.basename(out))
        return
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text, "--request-option", "max_tokens=420",
           "--seed", "42", "--num-inference-steps", str(steps),
           "--session-option", "dots_tts.mem_saver=true",
           "--out", out, "--metrics"]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    log = (r.stdout or "") + (r.stderr or "")
    size = os.path.getsize(out) if os.path.exists(out) else 0
    err = ""
    for line in log.splitlines():
        low = line.lower()
        if "error" in low or "unsupported" in low or "failed" in low:
            err = line.strip()[:120]
            break
    print("%-14s wall=%6.1fs size=%7d %s" % (os.path.basename(out), time.time() - t0, size, err))
    sys.stdout.flush()


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1:] or None
    for tag, text, _ in CASES:
        if only and tag not in only:
            continue
        for s in STEPS:
            run(tag, text, s)
