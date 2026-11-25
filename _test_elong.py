# -*- coding: utf-8 -*-
"""验证 dots.tts 原生「词级 rate 标签」能不能做省略号的延长音。

背景：用户 2026-11-24 ——「之前解决过延长音，是原 dots 引擎自己生成的，
能加标签自己加上去，LLM 标注加上去的，延长的是元音那些音。」
出处：`DOTS_MARKUP_RULES.md` §七 + `DOTS_ANNOTATION_RULES.md` §4.2
  —— `tts` 任务下**整段 rate 无效（2~6%）**，**单词 rate 有效（兑现约 80%）**；
  实测 `tussle` 0.40s → 0.72s（factor 0.50）。

用法：
  python _test_elong.py --id c2_0368 --ref G:/_setup/_refs_v3/Charles_soft.wav
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, "G:/_setup")
import _paths as P  # noqa: E402
import _align_gate as AG  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402


def run(text, out, ref, seed=42, mtok=300):
    cmd = [P.ACPP, "--task", "tts", "--family", "dots_tts",
           "--model", P.MODEL, "--backend", P.ACPP_BACKEND,
           "--threads", str(P.ACPP_THREADS),
           "--voice-ref", ref, "--reference-text", "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % mtok]
    cmd += P.mem_saver_args()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        print("  FAIL:", (r.stderr or r.stdout)[-300:])
        return False
    return True


def word_dur(path, text):
    """返回 {word: ms}，用 forced_align。"""
    proc, model = AG.load_model()
    r = AG.align(proc, model, path, text)
    if not r:
        return {}, 0.0
    words, cur = [], []
    for t in r["tokens"]:
        if t["tok"] == "|":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        words.append(cur)
    out = {}
    for w in words:
        k = "".join(x["tok"] for x in w)
        out[k] = round((w[-1]["end"] - w[0]["start"]) * 20.0, 1)
    y, sr = sf.read(path, dtype="float32")
    return out, len(y) / sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="c2_0368")
    ap.add_argument("--ref", default="G:/_setup/_refs_v3/Charles_soft.wav")
    ap.add_argument("--out", default="G:/_setup/_elong")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    # 原文：‘I think... I don’t know. I think it’s free.’
    base = "I think... I don't know. I think it's free."
    variants = [
        ("v0_plain", base),
        ("v1_rate080_think", "I <rate, factor=0.80>think</rate>... I don't know. I think it's free."),
        ("v2_rate060_think", "I <rate, factor=0.60>think</rate>... I don't know. I think it's free."),
        ("v3_rate060_ithink", "<rate, factor=0.60>I think</rate>... I don't know. I think it's free."),
        ("v4_rate050_think", "I <rate, factor=0.50>think</rate>... I don't know. I think it's free."),
    ]

    res = []
    for tag, txt in variants:
        p = os.path.join(a.out, "%s.wav" % tag)
        print("[%s] %s" % (tag, txt[:70]))
        if not run(txt, p, a.ref, a.seed):
            continue
        wd, dur = word_dur(p, base.replace("'", " "))
        th = wd.get("THINK", 0)
        print("  总 %.2fs  第一处 THINK=%sms  词表=%s" % (dur, th, wd))
        res.append({"tag": tag, "text": txt, "path": p, "dur": round(dur, 2),
                    "think_ms": th, "words": wd})

    print("\n%-20s %8s %10s" % ("variant", "总时长", "think ms"))
    for x in res:
        print("%-20s %7.2fs %9.0f" % (x["tag"], x["dur"], x["think_ms"]))
    json.dump(res, open(os.path.join(a.out, "report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
