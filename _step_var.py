# -*- coding: utf-8 -*-
"""步数是否提升稳定性：同句、同步数、换 seed，看目标词名次的离散度。

N0112 是三步数下最不稳定的一句（目标词名次 1/4/1/5）。
6 步 vs 16 步，各补 2 个 seed（42 已有），共 4 条。
"""
import os
import subprocess
import sys
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
OUT = "G:/_setup/_step_var"

TEXT = "He went forward quite deliberately, being sure of his way, and unafraid."
JOBS = [(6, 1234), (6, 31337), (16, 1234), (16, 31337)]


def run(steps, seed):
    out = os.path.join(OUT, "n0112_s%d_seed%d.wav" % (steps, seed))
    if os.path.exists(out) and os.path.getsize(out) > 10000:
        print(os.path.basename(out), "skip")
        return
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", TEXT, "--request-option", "max_tokens=420",
           "--seed", str(seed), "--num-inference-steps", str(steps),
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
            err = line.strip()[:110]
            break
    print("%-26s wall=%6.1fs size=%7d %s" % (os.path.basename(out), time.time() - t0, size, err))
    sys.stdout.flush()


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for s, sd in JOBS:
        run(s, sd)
