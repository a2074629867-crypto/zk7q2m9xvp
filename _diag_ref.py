# -*- coding: utf-8 -*-
"""_diag_ref.py —— 定位「短参考导致复读」到底是参考的问题还是 reference-text 的问题

三组对照，同一句正文、同一 seed，只有参考/参考文本在变：
  A  原参考 13.39s + 原 4 句文本     （基线，应 ~4.8s）
  B  修正参考 7.93s + 原 4 句文本    （文本与音频长度不匹配：文本多出借用段）
  C  修正参考 7.93s + 空 reference-text（不给文本，让模型自己听）

判读：
  A 正常 C 正常、B 异常  → reference-text 与参考音频不匹配是元凶（不是参考本身脏）
  A 正常、B 正常、C 正常  → 复读与两者无关，是 7.93s 太短触发（参考长度下限问题）
  三组都异常              → 参考文件本身有问题
"""
import json
import os
import subprocess
import sys
import time

import soundfile as sf

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
OUT = "G:/_setup/_diag_ref"
TEXT = "‘I will not live there again, until it belongs to me,’ his father had said."
T_ORIG = ("It's by Henri King on the death of his wife. It's all contactless now, yes. "
          "My father was a reserved man. She was looking at me as if she was sorry for me.")
T_FIX = ("It's by Henri King on the death of his wife. It's all contactless now, yes. "
         "My father was a reserved man.")

CASES = [
    ("A_orig_ref_13s", "G:/_setup/_ref9/Joseph_normal.wav", T_ORIG),
    ("B_fix_ref_79s", "G:/_setup/_ref9_fix/Joseph_normal.wav", T_ORIG),
    ("C_fix_ref_7s_notxt", "G:/_setup/_ref9_fix/Joseph_normal.wav", None),
    ("D_fix_ref_7s_3txt", "G:/_setup/_ref9_fix/Joseph_normal.wav", T_FIX),
]


def mtok(words):
    return max(120, min(900, int(words * 12 + 120)))


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, ref, rtext in CASES:
        out = os.path.join(OUT, name + ".wav")
        if os.path.exists(out) and os.path.getsize(out) > 50000:
            print("%-22s 已有 %.2fs，跳过" % (name, sf.info(out).duration), flush=True)
            continue
        cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
               "--backend", "vulkan", "--threads", "2",
               "--voice-ref", ref,
               "--text", TEXT, "--seed", "42", "--out", out,
               "--request-option", "max_tokens=%d" % mtok(len(TEXT.split())),
               "--session-option", "dots_tts.mem_saver=true"]
        if rtext:
            cmd[cmd.index("--text"):cmd.index("--text")] = ["--reference-text", rtext]
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=ACPP_DIR, timeout=1800)
        if os.path.exists(out) and os.path.getsize(out) > 50000:
            print("%-22s ref %.2fs  →  生成 %.2fs  (%.0fs)" % (
                name, sf.info(ref).duration, sf.info(out).duration, time.time() - t), flush=True)
        else:
            print("%-22s FAIL %s" % (name, (r.stderr or "")[-200:]), flush=True)


if __name__ == "__main__":
    main()
