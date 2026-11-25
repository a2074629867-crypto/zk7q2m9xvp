# -*- coding: utf-8 -*-
"""测「省略号处到底有没有拖长/停顿」。

用户 2026-11-24：「'I think... 这里应该延长的」
规则（用户 2026-11-23 定过）：省略号 = 自然拖音 —— **只拉元音、辅音原速、末尾渐弱**，
后面还要有真实停顿。
"""
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _align_gate as AG  # noqa: E402


def gaps_from_energy(y, sr, thr_db=-42.0, min_ms=60):
    """按 10ms 帧找低于阈值的连续段（相对最响帧 -42dB）。"""
    w = int(0.01 * sr)
    n = len(y) // w
    fr = np.sqrt((y[: n * w].reshape(n, w) ** 2).mean(1)) + 1e-12
    db = 20 * np.log10(fr)
    ref = np.percentile(db, 95)
    q = db < ref + thr_db
    runs, cur = [], None
    for i, v in enumerate(q):
        if v and cur is None:
            cur = i
        elif not v and cur is not None:
            runs.append((cur * 0.01, i * 0.01))
            cur = None
    if cur is not None:
        runs.append((cur * 0.01, n * 0.01))
    return [(a, b) for a, b in runs if (b - a) * 1000 >= min_ms]


def probe(path, text, target_words=("think",)):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    proc, model = _M
    r = AG.align(proc, model, path, text)
    if not r:
        print("  对齐失败")
        return
    # 拼词
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

    gs = gaps_from_energy(y, sr)
    print("  总时长 %.2fs   能量低谷段(>=60ms): %s"
          % (len(y) / sr, ["%.2f-%.2f(%.0fms)" % (a, b, (b - a) * 1000) for a, b in gs]))
    print("  %-12s %-8s %-8s %-8s" % ("词", "起点", "时长", "后接间隔"))
    for i, w in enumerate(words):
        tok = "".join(x["tok"] for x in w).replace("▁", "")
        st_s = w[0]["start"] * 0.02          # 帧号 × 20ms
        en_s = w[-1]["end"] * 0.02
        dur = en_s - st_s
        nxt_s = (words[i + 1][0]["start"] * 0.02) if i + 1 < len(words) else None
        gap = (nxt_s - en_s) if nxt_s is not None else 0.0
        mark = "  ←" if tok.lower().strip("'") in target_words else ""
        print("  %-12s %6.2fs %6.0fms %7.0fms%s" % (tok, st_s, dur * 1000, gap * 1000, mark))


_M = None

if __name__ == "__main__":
    _M = AG.load_model()
    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
    rid = sys.argv[1] if len(sys.argv) > 1 else "c2_0368"
    files = sys.argv[2:] or ["G:/_setup/_audio_ch123/out/%s.wav" % rid,
                             "G:/_setup/_regen_tense/ts_%s__s42.wav" % rid]
    for p in files:
        if not os.path.exists(p):
            print("%s 缺文件" % p)
            continue
        print("=== %s" % p)
        probe(p, rows[rid]["text"])
        print()
