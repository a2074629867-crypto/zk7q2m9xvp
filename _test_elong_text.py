# -*- coding: utf-8 -*-
"""_test_elong_text.py —— 本地 RX580(Vulkan) 小批量测「文本侧能否逼出原生延长」。

背景：
  · `<rate>` 等标签属 `dots.tts.edit` 入口（doteBench 的方言是 `<rate, factor=1.20>`），
    本机 audiocpp 0.9.1 只注册了 `dots_tts: tts, clon`，没有 edit 任务 ⇒ 标签在 tts 路上无效。
  · 所以只剩「改文本写法」这一条引擎原生路线：模型自己读、自己决定拖多久，无后处理痕迹。

测 5 组，同参考 / 同 seed / 同参数，唯一变量是文本：
  T0 基线      I think... I don't know.
  T1 原生方言  <rate, factor=1.20>I think</rate>...        （验证 doteBench 方言在 tts 路上有没有效）
  T2 原生方言  <rate, factor=1.60>think</rate>...
  T3 重复元音  I thiiink...
  T4 拖音符    I thi-ink...                                （连字符，看会不会按音节拆读）

判据：forced_align 量 THINK 的实际时长 + F0 + 有无吃字。只看「时长变长且 F0/字数不变」。
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _align_gate as AG      # noqa: E402
import _paths as P            # noqa: E402

SR = 48000
REF = "G:/_setup/_refs_v3/Charles_neutral.wav"
OUT = "G:/_setup/_elong_txt"

CASES = [
    ("T0_base",  "I think... I don't know."),
    ("T1_rate12", "<rate, factor=1.20>I think</rate>... I don't know."),
    ("T2_rate16", "<rate, factor=1.60>think</rate>... I don't know."),
    ("T3_double", "I thiiink... I don't know."),
    ("T4_hyphen", "I thi-ink... I don't know."),
]


def gen(text, out):
    cmd = [P.ACPP,
           "--task", "tts", "--family", "dots_tts", "--model", P.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", "",
           "--text", text, "--seed", "42", "--out", out,
           "--request-option", "max_tokens=320",
           "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, cwd=P.ACPP_DIR, capture_output=True, text=True, timeout=900)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def think_ms(path, text):
    proc, model = _M
    r = AG.align(proc, model, path, text)
    if not r:
        return None
    words, cur = [], []
    for tk in r["tokens"]:
        if tk["tok"] == "|":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(tk)
    if cur:
        words.append(cur)
    for w in words:
        k = "".join(x["tok"] for x in w).lower()
        if "think" in k or k.startswith("thi"):
            return (w[-1]["end"] * 0.02 - w[0]["start"] * 0.02) * 1000
    return None


_M = None

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    _M = AG.load_model()

    rows = {}
    for name, text in CASES:
        if a.only and name not in a.only.split(","):
            continue
        p = os.path.join(OUT, "%s.wav" % name)
        if not (os.path.exists(p) and os.path.getsize(p) > 10000):
            rc, log = gen(text, p)
            if rc != 0 or not os.path.exists(p):
                print("%-10s 生成失败 rc=%d %s" % (name, rc, log[-300:]))
                continue
        y, sr = sf.read(p, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        ms = think_ms(p, text)
        rows[name] = dict(text=text, dur=round(len(y) / sr, 2),
                          think_ms=round(ms, 1) if ms else None,
                          peak=round(float(np.abs(y).max()), 3))
        print("%-10s 总 %5.2fs  THINK %s  peak %.2f  | %s"
              % (name, len(y) / sr,
                 ("%5.1fms" % ms) if ms else "  n/a ", rows[name]["peak"], text[:46]))

    if rows:
        base = rows.get("T0_base", {}).get("think_ms")
        if base:
            print()
            print("相对基线 T0=%.0fms：" % base)
            for k, v in rows.items():
                if v["think_ms"]:
                    print("  %-10s %5.0fms  x%.2f" % (k, v["think_ms"], v["think_ms"] / base))
        json.dump(rows, open(os.path.join(OUT, "_log.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
