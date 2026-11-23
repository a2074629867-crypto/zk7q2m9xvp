# -*- coding: utf-8 -*-
"""按 doteBench 官方测试用例的语法，实测 dots.tts.edit 四类标签是否生效。

权威语法（来自 doteBench tests/instructions/test_parser.py）：
  <pitch semitones="-2">text</pitch>
  <rate factor="1.2">text</rate>
  <pause act="ins"/>   /   <pause act="red"/>
  <emo type="happy" level="2">text</emo>
  不存在 <volume>
  不能嵌套：<emo><rate></rate></emo> 被拒
  反例：'<rate, factor=1.2>x</rate>' 非法（带逗号+不带引号）
"""
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

CASES = [
    ("base", BASE),
    ("rate16", '<rate factor="1.6">%s</rate>' % BASE),
    ("rate06", '<rate factor="0.6">%s</rate>' % BASE),
    ("pitch_p5", '<pitch semitones="+5">%s</pitch>' % BASE),
    ("pitch_m5", '<pitch semitones="-5">%s</pitch>' % BASE),
    ("pitch_p12", '<pitch semitones="+12">%s</pitch>' % BASE),
    ("pause_ins", "He walked to the window<pause act=\"ins\"/>and looked out onto the copse."),
    ("volume", '<volume level="0.5">%s</volume>' % BASE),
]


def run(tag, text):
    out = os.path.join(OUT, tag + ".wav")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--source-audio", SRC,
           "--text", text,
           "--request-option", "max_tokens=300",
           "--request-option", "template_name=edit",
           "--seed", "42", "--num-inference-steps", "8",
           "--session-option", "dots_tts.mem_saver=true",
           "--out", out, "--metrics"]
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
    print("%-10s wall=%5.1fs size=%7d %s" % (tag, wall, size, err))
    sys.stdout.flush()
    return out


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1:] or None
    for tag, text in CASES:
        if only and tag not in only:
            continue
        run(tag, text)
