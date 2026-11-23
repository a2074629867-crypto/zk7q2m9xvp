# -*- coding: utf-8 -*-
"""单词级 emo 效果测量：整段中位 F0 + 目标词局部 F0 + 时长。

两步走：
  1) asr_venv/Scripts/python.exe _ew_ts.py <变体列表>   → _ew_ts.json
  2) G:/Python310/python.exe _ew_f0.py hair            → 本脚本

判据：
  - 整段 Δ ≈ 0 而目标词 Δ 大  → 局部生效（理想）
  - 整段 Δ 也很大            → 整段被污染，等价于整段 emo
"""
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

BASE_DIR = "G:/_setup/dots_edit2"
TS_JSON = "G:/_setup/_ew_ts.json"
BASE = "ES_base"


def read_wav(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return a.mean(axis=1), sr


def f0_track(a, sr, fmin=50, fmax=500):
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=fmin, pitch_ceiling=fmax)
    return pitch.xs(), pitch.selected_array["frequency"]


def med_in(t, f, t0, t1):
    m = (t >= t0) & (t <= t1) & (f > 0)
    return float(np.median(f[m])) if m.any() else None


def st(a, b):
    if a is None or b is None or a <= 0 or b <= 0:
        return None
    return 12.0 * np.log2(a / b)


def find_word(entry, word):
    for w, t0, t1 in entry.get("words", []):
        if w.strip(".,;:!?").lower() == word.lower():
            return float(t0), float(t1)
    return None


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else "hair"
    ts = json.load(open(TS_JSON, encoding="utf-8"))
    if BASE not in ts:
        print("缺少基线", BASE)
        return

    names = [BASE] + [k for k in ts if k != BASE]
    rows = []
    for v in names:
        p = "%s/MES_%s.wav" % (BASE_DIR, v)
        if not os.path.exists(p):
            continue
        a, sr = read_wav(p)
        dur = len(a) / sr
        t, f = f0_track(a, sr)
        whole = med_in(t, f, 0, dur)
        win = find_word(ts[v], word) or find_word(ts[BASE], word)
        local = None
        if win:
            pad = max(0.10, (win[1] - win[0]) * 0.6)
            local = med_in(t, f, max(0, win[0] - pad), min(dur, win[1] + pad))
        rows.append(dict(v=v, dur=dur, whole=whole, local=local, win=win,
                         nw=len(ts[v].get("words", [])),
                         sim_text=ts[v].get("text", "")))

    b = next((r for r in rows if r["v"] == BASE), None)
    if not b:
        print("缺少基线音频")
        return

    print("目标词：%s（基线 %d 词 / %.2fs / 整段 %.1f Hz）\n"
          % (word, b["nw"], b["dur"], b["whole"]))
    print("%-16s %7s %5s %9s %8s %10s %8s %s"
          % ("变体", "时长", "词数", "整段F0", "Δ整段", "目标词F0", "Δ词", "词窗"))
    for r in rows:
        dw, dl = st(r["whole"], b["whole"]), st(r["local"], b["local"])
        win = "%.2f-%.2f" % r["win"] if r["win"] else "-"
        print("%-16s %6.2fs %5d %9.1f %+8s %10s %+8s %s" % (
            r["v"], r["dur"], r["nw"], r["whole"] or 0,
            ("%.2f" % dw) if dw is not None else "-",
            ("%.1f" % r["local"]) if r["local"] else "-",
            ("%.2f" % dl) if dl is not None else "-",
            win))


if __name__ == "__main__":
    main()
