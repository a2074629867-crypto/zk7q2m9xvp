# -*- coding: utf-8 -*-
"""重音注入实验：用 <rate factor> 局部拉长目标词，检验是否形成可测的重音。

判定标准（三条都要满足才算"注入成功"）：
  1. 目标词时长显著变长（相对整句语音段的占比上升）
  2. 非目标词的时长基本不变（局部性，变化 <10%）
  3. 目标词的突出度（时长 z + F0 z + 能量 z）排名上升
"""
import os
import subprocess
import sys
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
OUT = "G:/_setup/_stress_test"

# (tag, text, 目标词列表)
CASES = [
    ("n0194_base", "Edmund Hooper went slowly up the four flights of stairs to his own bedroom.", []),
    ("n0194_r06", 'Edmund Hooper went <rate factor="0.6">slowly</rate> up the four flights of stairs to his own bedroom.', ["slowly"]),
    ("n0194_r04", 'Edmund Hooper went <rate factor="0.4">slowly</rate> up the four flights of stairs to his own bedroom.', ["slowly"]),
    ("n0112_base", "He went forward quite deliberately, being sure of his way, and unafraid.", []),
    ("n0112_r06", 'He went forward quite <rate factor="0.6">deliberately</rate>, being sure of his way, and unafraid.', ["deliberately"]),
    ("n0112_r04", 'He went forward quite <rate factor="0.4">deliberately</rate>, being sure of his way, and unafraid.', ["deliberately"]),
    ("n0167_base", "Moonlight came through the window, coldly, on to the glass.", []),
    ("n0167_r06", 'Moonlight came through the window, <rate factor="0.6">coldly</rate>, on to the glass.', ["coldly"]),
]


def run(tag, text):
    out = os.path.join(OUT, tag + ".wav")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text, "--request-option", "max_tokens=420",
           "--seed", "42", "--num-inference-steps", "8",
           "--session-option", "dots_tts.mem_saver=true",
           "--out", out, "--metrics"]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    log = (r.stdout or "") + (r.stderr or "")
    size = os.path.getsize(out) if os.path.exists(out) else 0
    err = ""
    for line in log.splitlines():
        low = line.lower()
        if "error" in low or "unsupported" in low or "failed" in low:
            err = line.strip()[:140]
            break
    print("%-12s wall=%5.1fs size=%7d %s" % (tag, time.time() - t0, size, err))
    sys.stdout.flush()


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1:] or None
    for tag, text, _ in CASES:
        if only and tag not in only:
            continue
        run(tag, text)
