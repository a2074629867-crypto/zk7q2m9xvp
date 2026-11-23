"""验证 dots.tts.edit 的韵律控制到底走不走神经模型。

论文 B.5 写明：pitch 用 Praat PSOLA、rate 用 SoX WSOLA 做信号级变换，
再由 IndexTTS2 重合成 + 40ms crossfade 拼接 + F5-TTS 修边界。
如果这个 DSP 管线不在我们拿到的 GGUF 里，那么 semitones 数值必然无效。

对照：tts 模板 vs edit 模板（带 source-audio），各跑 0 / +9 / -9 半音。
±9 是论文里 pitch 提案的最大范围（−9..+9），若有响应必然一眼可见。
"""
import os
import subprocess
import sys
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
SOURCE = "G:/_setup/_mt_raw_s42/N0112.wav"
TEXT = "He went forward quite deliberately, being sure of his way, and unafraid."
OUT = "G:/_setup/_pitch_test"

CASES = [
    ("tts_p0", "tts", TEXT),
    ("tts_p9p", "tts", '<pitch semitones="9">%s</pitch>' % TEXT),
    ("tts_p9m", "tts", '<pitch semitones="-9">%s</pitch>' % TEXT),
    ("edit_p0", "edit", TEXT),
    ("edit_p9p", "edit", '<pitch semitones="9">%s</pitch>' % TEXT),
    ("edit_p9m", "edit", '<pitch semitones="-9">%s</pitch>' % TEXT),
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
    print("%-9s %-5s wall=%5.1fs size=%8d %s" % (tag, template, dt, size, err), flush=True)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for tag, tpl, txt in CASES:
        run(tag, tpl, txt)
    print("DONE", flush=True)
