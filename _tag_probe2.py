# -*- coding: utf-8 -*-
"""补齐两块：① 默认 tts 模板（生产链实际用法）下标签会不会被当文本读；② <pause act="red"/>。"""
import os
import subprocess
import sys
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
SRC = "G:/_setup/_seam/a_comma.wav"
OUT = "G:/_setup/_seam/tag"
BASE = "He walked to the window and looked out onto the copse."

# (tag, text, 是否走 edit 模板)
CASES = [
    ("tts_rate16", '<rate factor="1.6">%s</rate>' % BASE, False),
    ("tts_base", BASE, False),
    ("tts_pause", "He walked to the window<pause act=\"ins\"/>and looked out onto the copse.", False),
    ("pause_red", "He walked to the window<pause act=\"red\"/>and looked out onto the copse.", True),
    ("pitch_0", '<pitch semitones="0">%s</pitch>' % BASE, True),
]


def run(tag, text, edit):
    out = os.path.join(OUT, tag + ".wav")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text,
           "--request-option", "max_tokens=300",
           "--seed", "42", "--num-inference-steps", "8",
           "--session-option", "dots_tts.mem_saver=true",
           "--out", out, "--metrics"]
    if edit:
        cmd += ["--source-audio", SRC, "--request-option", "template_name=edit"]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    wall = time.time() - t0
    log = (r.stdout or "") + (r.stderr or "")
    size = os.path.getsize(out) if os.path.exists(out) else 0
    err = ""
    for line in log.splitlines():
        low = line.lower()
        if "error" in low or "unsupported" in low or "failed" in low or "reject" in low:
            err = line.strip()[:160]
            break
    print("%-12s edit=%-5s wall=%5.1fs size=%7d %s" % (tag, edit, wall, size, err))
    sys.stdout.flush()


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for tag, text, edit in CASES:
        run(tag, text, edit)
