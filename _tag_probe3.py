# -*- coding: utf-8 -*-
"""默认 tts 模板（生产链实际用法）下的完整标签矩阵。官方语法见 doteBench tests。

  <emo type="happy" level="2">    level 只允许 1..3
  <pitch semitones="-2">
  <rate factor="1.2">
  <pause act="ins"/> / <pause act="red"/>
  无 <volume>
"""
import os
import subprocess
import sys
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
OUT = "G:/_setup/_seam/tag"
BASE = "He walked to the window and looked out onto the copse."
PAUSE_TXT = 'He walked to the window<pause act="%s"/>and looked out onto the copse.'

CASES = [
    ("t_pitch_p5", '<pitch semitones="+5">%s</pitch>' % BASE),
    ("t_pitch_m5", '<pitch semitones="-5">%s</pitch>' % BASE),
    ("t_emo_happy2", '<emo type="happy" level="2">%s</emo>' % BASE),
    ("t_emo_sad2", '<emo type="sad" level="2">%s</emo>' % BASE),
    ("t_emo_angry3", '<emo type="angry" level="3">%s</emo>' % BASE),
    ("t_rate06", '<rate factor="0.6">%s</rate>' % BASE),
    ("t_pause_red", PAUSE_TXT % "red"),
    ("t_volume", '<volume level="0.5">%s</volume>' % BASE),
]


def run(tag, text):
    out = os.path.join(OUT, tag + ".wav")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text,
           "--request-option", "max_tokens=300",
           "--seed", "42", "--num-inference-steps", "8",
           "--session-option", "dots_tts.mem_saver=true",
           "--out", out, "--metrics"]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    log = (r.stdout or "") + (r.stderr or "")
    size = os.path.getsize(out) if os.path.exists(out) else 0
    err = ""
    for line in log.splitlines():
        low = line.lower()
        if "error" in low or "unsupported" in low or "failed" in low or "reject" in low:
            err = line.strip()[:150]
            break
    print("%-14s wall=%5.1fs size=%7d %s" % (tag, time.time() - t0, size, err))
    sys.stdout.flush()


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for tag, text in CASES:
        run(tag, text)
