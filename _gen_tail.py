# -*- coding: utf-8 -*-
"""加长生成再切：极短句（单字/专有名词）在 dots.tts 上单独生成会吞音，
把目标句后面接一个尾随短语一起生成，再按词级时间戳切回目标句。

项目已验证（"father 没读完就断了" → 尾部加尾随短语生成再切）。
用法：
  G:/Python310/python.exe _gen_tail.py --id c3_0837 --text "Moths. What are those?" \
      --ref G:/_setup/_castle_cues/...wav --ref-text "..." --seeds 7,11,23 --out _sweep/cand16
"""
import argparse
import json
import os
import subprocess

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"


def mtok(words):
    return max(120, min(900, int(words * 12 + 120)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-text", default="")
    ap.add_argument("--seeds", default="7,11,23")
    ap.add_argument("--out", default="G:/_setup/_sweep/cand16")
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for s in [int(x) for x in a.seeds.split(",") if x.strip()]:
        out = os.path.join(a.out, "%s__s%d.wav" % (a.id, s))
        cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
               "--backend", "vulkan", "--threads", str(a.threads),
               "--voice-ref", a.ref, "--reference-text", a.ref_text or "",
               "--text", a.text, "--seed", str(s), "--out", out,
               "--request-option", "max_tokens=%d" % mtok(len(a.text.split())),
               "--session-option", "dots_tts.mem_saver=true", "--metrics"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=1200)
        ok = os.path.exists(out) and os.path.getsize(out) > 50000
        print("%s s%d %s" % (a.id, s, "OK" if ok else "FAIL"), flush=True)


if __name__ == "__main__":
    main()
