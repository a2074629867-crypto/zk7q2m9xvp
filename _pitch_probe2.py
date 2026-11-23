"""按官方 App 实际生成的标签写法重测。

apps/edit_playground/editing.py 第 304-311 行生成的是：
    <pitch, semitones=9>...</pitch>
    <rate, factor=0.8>...</rate>
即 **逗号分隔、值不加引号、正数不带 + 号**，且 semitones 只允许 {-9,-7,-5,5,7,9}。

我们之前测的是 <pitch semitones="+5">，三处都不在训练分布里。
这一轮用规范写法，同时测 rate 的精度（0.8 是否真给 1.25x）。
"""
import os
import subprocess
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
SOURCE = "G:/_setup/_mt_raw_s42/N0112.wav"
TEXT = "He went forward quite deliberately, being sure of his way, and unafraid."
OUT = "G:/_setup/_pitch_test"

CASES = [
    ("c_tts_p9p", "tts", '<pitch, semitones=9>%s</pitch>' % TEXT),
    ("c_tts_p9m", "tts", '<pitch, semitones=-9>%s</pitch>' % TEXT),
    ("c_edit_p9p", "edit", '<pitch, semitones=9>%s</pitch>' % TEXT),
    ("c_edit_p9m", "edit", '<pitch, semitones=-9>%s</pitch>' % TEXT),
    ("c_edit_r08", "edit", '<rate, factor=0.8>%s</rate>' % TEXT),
    ("c_edit_r125", "edit", '<rate, factor=1.25>%s</rate>' % TEXT),
]


def run(tag, template, text):
    out = os.path.join(OUT, tag + ".wav")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text,
           "--request-option", "max_tokens=420",
           "--request-option", "template_name=" + template,
           "--seed", "42", "--num-inference-steps", "8",
           "--session-option", "dots_tts.mem_saver=true",
           "--out", out]
    if template == "edit":
        cmd += ["--source-audio", SOURCE]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    dt = time.time() - t0
    size = os.path.getsize(out) if os.path.exists(out) else 0
    err = ""
    for line in (p.stdout + p.stderr).splitlines():
        if "error" in line.lower() or "unknown" in line.lower() or "unsupported" in line.lower():
            err = line.strip()[:110]
            break
    print("%-12s %-5s wall=%5.1fs size=%8d %s" % (tag, template, dt, size, err), flush=True)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for tag, tpl, txt in CASES:
        run(tag, tpl, txt)
    print("DONE", flush=True)
