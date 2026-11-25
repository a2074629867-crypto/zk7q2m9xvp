# -*- coding: utf-8 -*-
"""_test_rate_mono.py —— 判 `<rate, factor=N>` 在 tts 路上是否真的生效（单调性检验）。

为什么必须做这个：单条对比无法区分「标签生效」和「换了 token 序列导致的随机差异」。
唯一干净的判据是**单调性**：factor 1.20 / 1.60 / 2.00 三档 × 3 个 seed，
若 think 时长随 factor 单调上升，且跨度 > seed 间波动，才算生效。
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

REF = "G:/_setup/_refs_v3/Charles_neutral.wav"
OUT = "G:/_setup/_elong_mono"
TAIL = "... I don't know."


def gen(text, out, seed):
    cmd = [P.ACPP, "--task", "tts", "--family", "dots_tts", "--model", P.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=320",
           "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, cwd=P.ACPP_DIR, capture_output=True, text=True, timeout=1500)
    return r.returncode


def think_ms(path, text):
    proc, model = _M
    r = AG.align(proc, model, path, text)
    if not r:
        return None
    words, cur = [], []
    for tk in r["tokens"]:
        if tk["tok"] == "|":
            if words or cur:
                words.append(cur)
            cur = []
        else:
            cur.append(tk)
    if cur:
        words.append(cur)
    out = []
    for w in words:
        k = "".join(x["tok"] for x in w).lower()
        out.append((k, (w[-1]["end"] - w[0]["start"]) * 0.02 * 1000))
    return out


_M = None

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--factors", default="1.20,1.60,2.00")
    ap.add_argument("--seeds", default="42,43,44")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    _M = AG.load_model()

    res = {}
    for f in a.factors.split(","):
        text = "<rate, factor=%s>I think</rate>%s" % (f, TAIL)
        row = []
        for sd in a.seeds.split(","):
            p = os.path.join(OUT, "f%s_s%s.wav" % (f, sd))
            if not (os.path.exists(p) and os.path.getsize(p) > 10000):
                if gen(text, p, int(sd)) != 0 or not os.path.exists(p):
                    print("f%s s%s 失败" % (f, sd))
                    continue
            y, sr = sf.read(p, dtype="double")
            if y.ndim > 1:
                y = y.mean(1)
            ws = think_ms(p, text)
            th = next((d for k, d in ws if k.startswith("think") or k == "think"), None) if ws else None
            row.append(dict(seed=sd, dur=round(len(y) / sr, 2),
                            think=round(th, 1) if th else None,
                            words=len(ws) if ws else 0))
            print("f%-5s s%-3s 总%5.2fs think %s 词数 %s"
                  % (f, sd, len(y) / sr, ("%.0fms" % th) if th else "n/a", len(ws) if ws else 0))
        vals = [r["think"] for r in row if r["think"]]
        if vals:
            print("   => f%-5s think 均值 %.0fms  跨度 %.0f~%.0f  seed间波动 %+0.fms"
                  % (f, np.mean(vals), min(vals), max(vals), np.std(vals)))
        res[f] = row

    json.dump(res, open(os.path.join(OUT, "_mono.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    means = {f: np.mean([r["think"] for r in v if r["think"]]) for f, v in res.items()
             if any(r["think"] for r in v)}
    if len(means) >= 2:
        order = [means[f] for f in a.factors.split(",") if f in means]
        mono = all(b > a2 for a2, b in zip(order, order[1:]))
        print()
        print("均值序列:", " → ".join("%.0fms" % v for v in order),
              "  单调递增:", "是 ⇒ 标签生效" if mono else "否 ⇒ 标签未生效/被随机淹没")
