# -*- coding: utf-8 -*-
"""_adv_present.py —— 只回答一个问题：该副词在音频里**物理上是否存在**。

教训（2026-10-26）：用户听了 4 条被判"不合格"的单元，全部说没问题。
说明"够不够突出"的阈值不是他实际的标准，声学上不突出的副词他也接受。
真正不能接受的是「被跳过 / 吞掉」，这可以硬判：

  voiced_ms   词区间内浊音帧总长（10ms 一帧）
  rms_ratio   词区间 RMS / 全句 voiced RMS
  sps         词时长/音节数

硬缺陷只有两种：
  ABSENT    voiced_ms < 60           → 根本没出声
  SWALLOW   rms_ratio < 0.35 且 sps < 0.14  → 出声但被压没
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import parselmouth

sys.path.insert(0, "G:/_setup")
import _adv_check as AC
import _adv_align
import _f0_accent as F

ROOT = "G:/_setup"
PLAN = "B:/mt-tts/data/plan/mt_plan3b.json"
PROM_DIR = os.path.join(ROOT, "_wpt_out")
STATE = os.path.join(ROOT, "_mt_adv_state.json")


def measure(wav, text, word):
    ts, fs, dur = F.track(wav)
    if len(fs) < 20:
        return None
    snd = parselmouth.Sound(wav)
    rows = []
    sp = _adv_align.span_of(text, rows, word)   # 需要 prom 行，见下
    return None


def analyse(wav, text, prom_path, word):
    ts, fs, dur = F.track(wav)
    if len(fs) < 20:
        return None
    snd = parselmouth.Sound(wav)
    inten = snd.to_intensity(minimum_pitch=60, time_step=0.01)
    it, iv = inten.xs(), inten.values[0]
    iv = np.where(np.isfinite(iv), iv, 0.0)

    rows = F.read_prom(prom_path)
    spans = _adv_align.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    tw = _adv_align.text_words(text)
    hit = None
    for i, x in enumerate(tw):
        if x["is_word"] and x["key"] == AC.norm(word):
            hit = i
    if hit is None or spans[hit]["t0"] is None:
        return dict(word=word, verdict="UNMEASURED")
    t0, t1 = spans[hit]["t0"], spans[hit]["t1"]

    voiced = float(((ts >= t0) & (ts < t1)).sum()) * 0.01
    seg = iv[(it >= t0) & (it < t1)]
    whole = iv[(it >= 0) & (it < dur)]
    rms = 10 ** (np.median(seg) / 20.0) if len(seg) else 0.0
    ref = 10 ** (np.median(whole) / 20.0) if len(whole) else 1e-9
    ratio = rms / max(ref, 1e-9)
    nsyl = max(1, AC.syllables(word))
    sps = (t1 - t0) / nsyl
    v = "OK"
    if voiced < 0.06:
        v = "ABSENT"
    elif ratio < 0.35 and sps < 0.14:
        v = "SWALLOW"
    return dict(word=word, t0=round(t0, 2), t1=round(t1, 2), voiced=round(voiced, 2),
                rms_ratio=round(float(ratio), 2), sps=round(sps, 3),
                synthetic=bool(spans[hit]["synthetic"]), verdict=v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_adv_present.json")
    a = ap.parse_args()
    plan = {str(it["id"]): it["text"] for it in
            (lambda d: d if isinstance(d, list) else d.get("items", []))(
                json.load(open(PLAN, encoding="utf-8")))}
    st = json.load(open(STATE, encoding="utf-8"))
    prom = {}
    for f in os.listdir(PROM_DIR):
        if f.endswith(".prom") and "__" in f:
            prom.setdefault(f[:-5].split("__", 1)[1], []).append(os.path.join(PROM_DIR, f))

    rows = []
    for uid, x in sorted(st["units"].items()):
        cands = prom.get(uid) or []
        if not cands:
            rows.append(dict(uid=uid, adv=x["adv"], verdict="NO_AUDIO"))
            continue
        best = None
        for p in sorted(cands):
            d, u = os.path.splitext(os.path.basename(p))[0].split("__", 1)
            wav = os.path.join(ROOT, d, u + ".wav")
            if not os.path.exists(wav):
                continue
            r = analyse(wav, x["text"], p, x["adv"])
            if not r:
                continue
            r["uid"], r["adv"], r["seed"] = uid, x["adv"], d.replace("_mt_raw_s", "")
            order = {"ABSENT": 0, "SWALLOW": 1, "UNMEASURED": 2, "OK": 3}
            if best is None or order[r["verdict"]] > order[best["verdict"]]:
                best = r
        rows.append(best or dict(uid=uid, adv=x["adv"], verdict="NO_AUDIO"))

    print("%-8s %-13s %-6s %-5s %-7s %-8s %-6s %s"
          % ("uid", "adv", "seed", "voiced", "rms比", "sps", "syn", "判定"))
    for r in rows:
        print("%-8s %-13s %-6s %-7s %-8s %-6s %-6s %s"
              % (r.get("uid"), r.get("adv"), r.get("seed"), r.get("voiced"),
                 r.get("rms_ratio"), r.get("sps"),
                 "Y" if r.get("synthetic") else "", r["verdict"]))
    from collections import Counter
    c = Counter(r["verdict"] for r in rows)
    print("\n", dict(c))
    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
