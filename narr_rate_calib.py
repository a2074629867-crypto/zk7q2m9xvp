# -*- coding: utf-8 -*-
"""narr_rate_calib.py —— <rate> tag 兑现率标定（旁白链）。

为什么必须实测：现有 RATE_MIN=0.78 是拍出来的，历史 L084 那批 0.70/0.74/0.78
实测方向甚至是反的（0.78→0.908、0.70→0.965 相对无 tag），更像 seed 抖动。
在不知道 0.72 能不能兑现之前，任何「特定情节减速」都是空谈。

用法：
  G:/Python310/python.exe -u narr_rate_calib.py --rates 0.84,0.80,0.76,0.72,0.70
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

ACPP = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
EXE = os.path.join(ACPP, "audiocpp_cli.exe")
MODEL = r"E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = r"G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."

# 2 句 18 词 ≈ 7~8s，避开 max_tokens≤260 的 OOM 线
SENTS = [
    "Zoe sat up in bed and looked around her room.",
    "Starlight cast a soft glow across the room.",
]
WORDS = sum(len(s.split()) for s in SENTS)


def gen(text, out, seed=42, max_tokens=260):
    cmd = [EXE, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % max_tokens,
           "--session-option", "dots_tts.mem_saver=true"]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ACPP, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout or "").splitlines()
            if "audio_out" in l or "error" in l.lower()]
    return r.returncode, " | ".join(tail[-2:]), time.time() - t0


def voiced_stats(path):
    """voiced 时长与 RMS。阈值用本文件 p90−30dB（相对），剔除首尾静音。"""
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    hop = int(0.02 * sr)
    n = len(x) // hop
    if n < 3:
        return None
    db = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1)) + 1e-12)
    p90 = float(np.percentile(db, 90))
    v = db > (p90 - 30.0)
    # 填 <5 帧的洞，去掉 <5 帧的孤立段
    i = 0
    while i < len(v):
        if not v[i]:
            j = i
            while j < len(v) and not v[j]:
                j += 1
            if i > 0 and j < len(v) and (j - i) < 5:
                v[i:j] = True
            i = j
        else:
            i += 1
    idx = np.where(v)[0]
    if len(idx) < 3:
        return None
    voiced_s = len(idx) * 0.02
    return dict(voiced=round(voiced_s, 3), total=round(len(x) / sr, 3),
                wpm=round(WORDS / voiced_s * 60, 1), p90=round(p90, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rates", default="0.84,0.80,0.76,0.72,0.70")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=r"G:/_setup/_rate_calib")
    ap.add_argument("--max-tokens", type=int, default=260)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    rates = [float(x) for x in a.rates.split(",")]

    # 每句各挂一个 rate span（chapter_run 的写法，句数 ≤10 不丢词）
    rows = []
    for r in rates:
        tag = " ".join("<rate, factor=%.2f>%s</rate>" % (r, s) for s in SENTS)
        wav = os.path.join(a.out, "r%.2f.wav" % r)
        if os.path.exists(wav) and sf.info(wav).duration > 1.0:
            print("[skip] r=%.2f 已存在" % r, flush=True)
        else:
            rc, msg, el = gen(tag, wav, a.seed, a.max_tokens)
            print("[gen ] r=%.2f rc=%d %.1fs %s" % (r, rc, el, msg[:80]), flush=True)
            if rc != 0 or not os.path.exists(wav):
                rows.append(dict(rate=r, status="fail", err=msg[:120]))
                continue
        st = voiced_stats(wav)
        if not st:
            rows.append(dict(rate=r, status="unmeasurable"))
            continue
        rows.append(dict(rate=r, status="ok", **st))
        print("       voiced %.3fs  wpm %.1f" % (st["voiced"], st["wpm"]), flush=True)

    ok = [x for x in rows if x.get("status") == "ok"]
    print()
    if len(ok) >= 2:
        base = max(ok, key=lambda x: x["rate"])      # 最大 rate = 最快 = 最短
        print("== 兑现率（基准 rate=%.2f, voiced %.3fs）==" % (base["rate"], base["voiced"]))
        print("%-7s %9s %9s %9s %8s" % ("rate", "voiced", "实测比", "期望比", "兑现"))
        for x in sorted(ok, key=lambda z: -z["rate"]):
            exp = base["rate"] / x["rate"]
            got = x["voiced"] / base["voiced"] if base["voiced"] else float("nan")
            pct = (got - 1) / (exp - 1) * 100 if abs(exp - 1) > 1e-6 else float("nan")
            print("%-7.2f %8.3fs %9.3f %9.3f %7.0f%%" % (x["rate"], x["voiced"], got, exp, pct))
        json.dump(rows, open(os.path.join(a.out, "calib.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print()
        print("明细: %s" % os.path.join(a.out, "calib.json"))


if __name__ == "__main__":
    main()
