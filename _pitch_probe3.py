"""补三点：① seed 1234 的 +9 与无标签对照（排除换 seed 造成的漂移）；
② +5 / -5（看响应是否单调）。

只测 tts 模板——edit 模板下 pitch 两个方向都不动，已可排除。
"""
import os
import subprocess
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
TEXT = "He went forward quite deliberately, being sure of his way, and unafraid."
OUT = "G:/_setup/_pitch_test"

CASES = [
    ("d_p5", "tts", '<pitch, semitones=5>%s</pitch>' % TEXT, 42),
    ("d_m5", "tts", '<pitch, semitones=-5>%s</pitch>' % TEXT, 42),
    ("d_base_s1234", "tts", TEXT, 1234),
    ("d_p9_s1234", "tts", '<pitch, semitones=9>%s</pitch>' % TEXT, 1234),
]


def run(tag, template, text, seed):
    out = os.path.join(OUT, tag + ".wav")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text,
           "--request-option", "max_tokens=420",
           "--request-option", "template_name=" + template,
           "--seed", str(seed), "--num-inference-steps", "8",
           "--session-option", "dots_tts.mem_saver=true",
           "--out", out]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    size = os.path.getsize(out) if os.path.exists(out) else 0
    print("%-14s seed=%-5d wall=%5.1fs size=%8d" % (tag, seed, time.time() - t0, size), flush=True)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for tag, tpl, txt, sd in CASES:
        run(tag, tpl, txt, sd)
    print("DONE", flush=True)
