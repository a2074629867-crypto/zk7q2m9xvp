# -*- coding: utf-8 -*-
"""带语速控制的生成：dots.tts 的 --speaking-rate / --target-duration-seconds。

用途：平静台词「念太快」，需要在生成期降速（比后期 time-stretch 无 artifacts）。
用法：
  G:/Python310/python.exe _gen_rate.py --id c2_0312 --text "..." --ref ... \
      --seeds 7,11 --rate 0.85 --out G:/_setup/_sweep/r45
"""
import argparse
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
    ap.add_argument("--seeds", default="7,11")
    ap.add_argument("--rate", type=float, default=0.0, help="speaking-rate；0=不传")
    ap.add_argument("--target-dur", type=float, default=0.0, help="target-duration-seconds")
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for s in [int(x) for x in a.seeds.split(",") if x.strip()]:
        tag = "r%02d" % int(round(a.rate * 100)) if a.rate else ("d%02d" % int(a.target_dur * 10))
        out = os.path.join(a.out, "%s__%s_s%d.wav" % (a.id, tag, s))
        cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
               "--backend", "vulkan", "--threads", str(a.threads),
               "--voice-ref", a.ref, "--reference-text", a.ref_text or "",
               "--text", a.text, "--seed", str(s), "--out", out,
               "--request-option", "max_tokens=%d" % mtok(len(a.text.split())),
               "--session-option", "dots_tts.mem_saver=true", "--metrics"]
        if a.rate:
            cmd += ["--speaking-rate", str(a.rate)]
        if a.target_dur:
            cmd += ["--target-duration-seconds", str(a.target_dur)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=1200)
        ok = os.path.exists(out) and os.path.getsize(out) > 50000
        dur = ""
        try:
            import soundfile as sf
            dur = "%.2fs" % sf.info(out).duration
        except Exception:
            pass
        print("%s %s s%d %s %s" % (a.id, tag, s, "OK" if ok else "FAIL", dur), flush=True)
        if not ok:
            print((r.stdout or "")[-300:], (r.stderr or "")[-300:], flush=True)


if __name__ == "__main__":
    main()
