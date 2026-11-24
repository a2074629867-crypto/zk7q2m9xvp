#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""语速检测：只用有声段（articulation rate），把逗号/句号/呼吸处的静音全部排除。

为什么改（2026-11-24 用户要求）：
  原来用「首尾有声跨度」(span) 当分母，句内停顿也被算成说话时间，
  于是模型在逗号后多停 0.3s，就被判成「语速慢 30%」。这是错的 ——
  停顿时长属于韵律，不属于语速。

现在的口径：
  把音频切成 10ms 帧，> -50 dBFS 记有声；相邻有声段间隔 < 120ms 视为同一个词内部
  （塞音闭合、协同发音），合并；最后
      wpm = 词数 / Σ(有声段时长) × 60
  句读处 ≥120ms 的停顿、首尾静音、尾部补的静音，全部不计入分母。

用法：
  python _rate.py --wav a.wav --text "I will not live there again."
  python _rate.py --pair c1_0002            # 对比 out/ 与 _sweep/notxt66_trim/
  python _rate.py --verdict                 # 重算 66 条的语速裁决
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

THR = -50.0        # dBFS，绝对阈值（与 _post_fix / _dn_scan / _trim_notxt66 一致）
HOP = 0.010
WIN = 0.025
MERGE_GAP = 0.120  # 小于这个间隔算词内，不切开


def wcount(s):
    return len(re.findall(r"[A-Za-z']+", s or ""))


def voiced_runs(y, sr):
    """返回 [(t0, t1), ...] 有声段（秒），已按 MERGE_GAP 合并。"""
    hop, win = int(HOP * sr), int(WIN * sr)
    n = 1 + (len(y) - win) // hop
    if n < 1:
        return []
    idx = np.clip(np.arange(win)[None, :] + hop * np.arange(n)[:, None], 0, len(y) - 1)
    db = 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12)
    on = db > THR
    runs, i = [], 0
    while i < n:
        if not on[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and on[j + 1]:
            j += 1
        runs.append([i * hop / sr, (j * hop + win) / sr])
        i = j + 1
    if not runs:
        return []
    merged = [runs[0]]
    for t0, t1 in runs[1:]:
        if t0 - merged[-1][1] < MERGE_GAP:
            merged[-1][1] = t1
        else:
            merged.append([t0, t1])
    return [(a, b) for a, b in merged]


def rate(path, text=None, words=None):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    runs = voiced_runs(y, sr)
    total = len(y) / sr
    speech = sum(b - a for a, b in runs)
    gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
    w = words if words is not None else wcount(text)
    return {
        "dur": round(total, 3),
        "speech": round(speech, 3),
        "span": round(runs[-1][1] - runs[0][0], 3) if runs else 0.0,
        "n_runs": len(runs),
        "max_gap": round(max(gaps), 3) if gaps else 0.0,
        "pause_total": round(sum(g for g in gaps if g >= MERGE_GAP), 3),
        "wpm": round(w / speech * 60, 1) if speech > 0.05 else None,   # articulation
        "wpm_span": round(w / (runs[-1][1] - runs[0][0]) * 60, 1)
        if runs and (runs[-1][1] - runs[0][0]) > 0.05 else None,
        "words": w,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--text", default="")
    ap.add_argument("--pair")
    ap.add_argument("--verdict", action="store_true")
    a = ap.parse_args()
    root = HERE

    if a.wav:
        r = rate(a.wav if os.path.isabs(a.wav) else os.path.join(root, a.wav), a.text)
        print(json.dumps(r, ensure_ascii=False))
        return

    plan = {}
    with open(os.path.join(root, "_dlg_plan_v2.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                plan[d["id"]] = d

    if a.pair:
        rid = a.pair
        o = rate(os.path.join(root, "_audio_ch123/out/%s.wav" % rid), plan[rid]["text"])
        n = rate(os.path.join(root, "_sweep/notxt66_trim/%s__s42.wav" % rid), plan[rid]["text"])
        print(rid, plan[rid]["who"], plan[rid]["emo"])
        print("  旧", json.dumps(o, ensure_ascii=False))
        print("  新", json.dumps(n, ensure_ascii=False))
        print("  语速变化 %+.0f%%（articulation）" % ((n["wpm"] / o["wpm"] - 1) * 100))
        return

    if a.verdict:
        v = json.load(open(os.path.join(root, "_notxt66_verdict.json"), encoding="utf-8"))
        ids = v["accept"] + [x[0] for x in v["watch"]] + v["reject"]
        out = []
        for rid in ids:
            op = os.path.join(root, "_audio_ch123/out/%s.wav" % rid)
            npth = os.path.join(root, "_sweep/notxt66_trim/%s__s42.wav" % rid)
            if not (os.path.exists(op) and os.path.exists(npth)):
                continue
            o = rate(op, plan[rid]["text"])
            n = rate(npth, plan[rid]["text"])
            d = (n["wpm"] / o["wpm"] - 1) if (o["wpm"] and n["wpm"]) else 0
            out.append({"id": rid, "who": plan[rid]["who"], "emo": plan[rid]["emo"],
                        "old_wpm": o["wpm"], "new_wpm": n["wpm"], "delta": round(d, 3),
                        "old_pause": o["pause_total"], "new_pause": n["pause_total"],
                        "old_runs": o["n_runs"], "new_runs": n["n_runs"]})
        out.sort(key=lambda x: x["delta"])
        ds = [x["delta"] for x in out]
        print("articulation 语速 Δ 中位 %+.0f%%   ±10%%内 %d | 快>10%% %d | 慢>10%% %d\n"
              % (np.median(ds) * 100,
                 sum(1 for x in ds if abs(x) <= 0.10),
                 sum(1 for x in ds if x > 0.10),
                 sum(1 for x in ds if x < -0.10)))
        print("%-9s %-8s %-6s %8s %8s %7s %8s" %
              ("id", "who", "emo", "旧wpm", "新wpm", "Δ", "停顿(旧→新)"))
        for x in out:
            flag = "" if abs(x["delta"]) <= 0.15 else ("  <<" if abs(x["delta"]) > 0.30 else "  <")
            print("%-9s %-8s %-6s %8.0f %8.0f %+6.0f%% %6.2f→%.2f%s" % (
                x["id"], x["who"], x["emo"], x["old_wpm"] or 0, x["new_wpm"] or 0,
                x["delta"] * 100, x["old_pause"], x["new_pause"], flag))
        json.dump(out, open(os.path.join(root, "_rate_notxt66.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("\n→ _rate_notxt66.json")


if __name__ == "__main__":
    main()
