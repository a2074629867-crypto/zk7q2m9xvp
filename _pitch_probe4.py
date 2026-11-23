"""局部重音测试：只给一个词包 <pitch, semitones=9>，看该词是否被抬高。

基线用已有的 n0194_base.wav（seed 42 / 8 步 / 无标签 / 同文本），可直接逐词对比。
再并一条 <rate, factor=0.7> 做对照——已知 rate 局部拉长有效。
"""
import os
import subprocess
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
OUT = "G:/_setup/_stress_test"

TGT = "slowly"
FULL = "Edmund Hooper went %s up the four flights of stairs to his own bedroom."

CASES = [
    ("n0194_pitch9", '<pitch, semitones=9>%s</pitch>' % TGT),
    ("n0194_rate07", '<rate, factor=0.7>%s</rate>' % TGT),
]


def run(tag, wrapped):
    text = FULL % wrapped
    out = os.path.join(OUT, tag + ".wav")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text,
           "--request-option", "max_tokens=420",
           "--seed", "42", "--num-inference-steps", "8",
           "--session-option", "dots_tts.mem_saver=true",
           "--out", out]
    t0 = time.time()
    subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    print("%-14s wall=%5.1fs size=%8d" % (tag, time.time() - t0,
                                          os.path.getsize(out) if os.path.exists(out) else 0), flush=True)


if __name__ == "__main__":
    for tag, w in CASES:
        run(tag, w)
    print("DONE", flush=True)
