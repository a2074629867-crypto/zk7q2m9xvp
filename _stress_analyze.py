# -*- coding: utf-8 -*-
"""_stress_analyze.py —— 词级重音位置分析（G:/Python310 跑，需要 parselmouth）。

回答三个问题：
  1. 重音放错（不落在内容词上）的比例是多少？按句长分档。
  2. 超过 7 词是否就失控？—— 看命中率是否随句长单调下降。
  3. 换 seed 能否命中想要的重音？—— 看跨 seed 位置一致率与有效位置数 N_eff。

口径：
- 词窗口来自 ASR 时间戳（`_stress_words.json`），不用音节核（会漂 0.7s）。
- 突出度 = 0.5·z(F0 中位, 半音) + 0.3·z(能量峰, dB) + 0.2·z(时长比)，z 用句内 robust z。
- F0 跨度 < 2 半音视为「无重音」，单独统计，不参与命中率。
- 内容词 = 不在停用词表里的词（粗略代理，但基线一起算，看的是相对提升）。
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import parselmouth

ROOT = "G:/_setup"
WORDS = os.path.join(ROOT, "_stress_words.json")
MIN_WIN = 0.06          # 词窗口短于此，F0/能量不可信
MIN_SPAN_ST = 2.0       # F0 跨度低于此视为无重音
POS_TOL = 0.10          # 跨 seed 位置一致判据（归一化句长）

STOP = set("""a an the and or but nor of to in on at for with from by as if than that this
these those it its he him his she her they them their we us our you your i me my was were is
are am be been being had has have do does did would could should will shall can may might must
not no so then there here when where why how what which who whom whose very just too also only
up down out off over into about after before again all any some more most such own same other
another both each few many much every either neither yet still ever never now once
sir mrs mr miss madam""".split())


def norm_word(w):
    return "".join(c for c in w.lower() if c.isalnum())


def is_content(w):
    s = norm_word(w)
    return bool(s) and s not in STOP


def rd(path):
    import wave
    with wave.open(path, "rb") as w:
        sr, ch, nf = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def rz(x):
    x = np.asarray(x, dtype=np.float64)
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    if mad < 1e-9:
        sd = float(np.std(x))
        return (x - med) / sd if sd > 1e-9 else np.zeros_like(x)
    return 0.6734 * (x - med) / mad


def feats(path, words):
    y, sr = rd(path)
    n = len(y)
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    pitch = snd.to_pitch(time_step=0.01, pitch_floor=60.0, pitch_ceiling=400.0)
    f = np.asarray(pitch.selected_array["frequency"], dtype=np.float64)
    pt = np.asarray(pitch.xs(), dtype=np.float64)

    rows = []
    for w in words:
        s, e = float(w["start"]), float(w["end"])
        if e - s < MIN_WIN:
            continue
        a, b = int(s * sr), min(n, int(e * sr))
        if b - a < int(MIN_WIN * sr):
            continue
        seg = y[a:b]
        # 能量：20ms 帧的 RMS 峰值
        hop = max(1, int(0.02 * sr))
        k = len(seg) // hop
        if k < 1:
            continue
        rms = np.sqrt(np.mean(seg[:k * hop].reshape(k, hop) ** 2, axis=1) + 1e-12)
        e_db = 20.0 * math.log10(float(rms.max()) + 1e-12)
        # F0：窗口内浊音帧中位
        m = (pt >= s) & (pt <= e) & (f > 0)
        f0 = float(np.median(f[m])) if m.sum() >= 2 else 0.0
        rows.append(dict(w=w["w"], start=s, end=e, dur=e - s, f0=f0, e_db=e_db,
                         content=is_content(w["w"])))

    if len(rows) < 2:
        return None
    durs = np.array([r["dur"] for r in rows])
    dur_ratio = durs / max(1e-6, float(np.median(durs)))
    f0s = np.array([r["f0"] if r["f0"] > 0 else np.nan for r in rows])
    okf = np.isfinite(f0s)
    if okf.sum() >= 2:
        med = float(np.median(f0s[okf]))
        f0_st = np.where(okf, 12.0 * np.log2(np.where(okf, f0s, med) / med), 0.0)
        span = float(np.nanmax(f0_st) - np.nanmin(f0_st))
    else:
        f0_st = np.zeros(len(rows))
        span = 0.0
    e_db = np.array([r["e_db"] for r in rows])

    prom = 0.5 * rz(f0_st) + 0.3 * rz(e_db) + 0.2 * rz(dur_ratio)
    k = int(np.argmax(prom))
    for i, r in enumerate(rows):
        r["f0_st"] = round(float(f0_st[i]), 2)
        r["prom"] = round(float(prom[i]), 3)
    n_ok = len(rows)
    return dict(words=rows, span_st=round(span, 2), top=k,
                top_w=rows[k]["w"], top_content=rows[k]["content"],
                pos_norm=round(k / max(1, n_ok - 1), 3),
                p_content=round(sum(1 for r in rows if r["content"]) / n_ok, 3),
                n_word=n_ok)


def q(a, p):
    a = sorted(a)
    if not a:
        return 0.0
    return a[min(len(a) - 1, max(0, int(round(p * (len(a) - 1)))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--out", default="_stress_ch1.json")
    a = ap.parse_args()

    plan = {p["id"]: p for p in json.load(open(os.path.join(ROOT, "mt_plan3b.json"), encoding="utf-8"))
            if p["ch"] == a.ch}
    raw = json.load(open(WORDS, encoding="utf-8"))

    # 只用 ASR 与原文对得上的（ratio >= 0.85，来自 mt_score）
    sc = json.load(open(os.path.join(ROOT, "_mt_score_%s.json" % a.ch), encoding="utf-8"))
    good = {}
    for r in sc:
        for c in r["cands"]:
            if c.get("ratio", 0) >= 0.85:
                good[(r["id"], str(c["seed"]))] = True

    res = {}
    for path, v in raw.items():
        if "error" in v or "words" not in v:
            continue
        uid, seed = v.get("uid"), str(v.get("seed"))
        if (uid, seed) not in good:
            continue
        try:
            ft = feats(path, v["words"])
        except Exception as e:
            print("skip", os.path.basename(path), e)
            continue
        if ft:
            ft.update(uid=uid, seed=seed, n_plan=len(plan[uid]["text"].split()) if uid in plan else 0)
            res[path] = ft

    json.dump(res, open(os.path.join(ROOT, a.out), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---------- 1) 按句长分档 ----------
    bins = [(0, 7), (8, 10), (11, 13), (14, 17), (18, 99)]
    print("\n=== 按句长分档（%d 条候选）===" % len(res))
    print("%-8s %6s %8s %9s %9s %9s" % ("句长", "候选", "无重音%", "命中内容词%", "随机基线%", "净提升pp"))
    for lo, hi in bins:
        sub = [v for v in res.values() if lo <= v["n_plan"] <= hi]
        if not sub:
            continue
        flat = [v for v in sub if v["span_st"] >= MIN_SPAN_ST]
        noacc = 100.0 * (1 - len(flat) / len(sub))
        if not flat:
            print("%-8s %6d %8.1f %9s %9s %9s" % ("%d-%d" % (lo, hi), len(sub), noacc, "-", "-", "-"))
            continue
        hit = 100.0 * sum(1 for v in flat if v["top_content"]) / len(flat)
        base = 100.0 * float(np.mean([v["p_content"] for v in flat]))
        print("%-8s %6d %8.1f %9.1f %9.1f %+9.1f"
              % ("%d-%d" % (lo, hi), len(sub), noacc, hit, base, hit - base))

    # ---------- 2) 跨 seed 一致性 ----------
    by_uid = {}
    for v in res.values():
        if v["span_st"] >= MIN_SPAN_ST:
            by_uid.setdefault(v["uid"], []).append(v)
    multi = {u: vs for u, vs in by_uid.items() if len(vs) >= 2}

    pairs = same = 0
    all_same = any_same = 0
    neff_terms = []
    for u, vs in multi.items():
        ps = [v["pos_norm"] for v in vs]
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                pairs += 1
                if abs(ps[i] - ps[j]) <= POS_TOL:
                    same += 1
        cnt = sum(1 for i in range(len(ps)) for j in range(i + 1, len(ps))
                  if abs(ps[i] - ps[j]) <= POS_TOL)
        if cnt == len(ps) * (len(ps) - 1) // 2:
            all_same += 1
        if cnt > 0:
            any_same += 1
        # 有效位置数（逆辛普森），基于 0.1 分桶
        h = {}
        for p in ps:
            k = int(round(p * 10))
            h[k] = h.get(k, 0) + 1
        neff_terms.append(1.0 / sum((c / len(ps)) ** 2 for c in h.values()))

    print("\n=== 跨 seed 重音位置一致性（%d 个多候选单元，%d 对）===" % (len(multi), pairs))
    if pairs:
        print("  两两一致率（|Δpos|<=%.2f）：%.1f%%" % (POS_TOL, 100.0 * same / pairs))
        print("  全部候选一致：%d/%d = %.1f%%" % (all_same, len(multi), 100.0 * all_same / len(multi)))
        print("  至少两条一致：%d/%d = %.1f%%" % (any_same, len(multi), 100.0 * any_same / len(multi)))
        print("  有效位置数 N_eff 中位 %.2f（越大越随机）" % float(np.median(neff_terms)))

    # ---------- 3) 随机命中推算 ----------
    print("\n=== 随机命中推算 ===")
    flat_all = [v for v in res.values() if v["span_st"] >= MIN_SPAN_ST]
    if flat_all:
        nw = float(np.median([v["n_word"] for v in flat_all]))
        print("  句中位词数 %.1f" % nw)
        for K in (2, 3, 4, 6):
            print("    %d 个候选，若位置在 %.0f 个词上均匀随机 → 至少命中一次 %.1f%%"
                  % (K, nw, 100.0 * (1 - (1 - 1.0 / nw) ** K)))
        if pairs:
            print("  实测两两一致率 %.1f%% ⇒ 若纯随机，基线应为 1/%.0f = %.1f%%"
                  % (100.0 * same / pairs, nw, 100.0 / nw))

    # ---------- 4) 句末偏置 ----------
    tail = sum(1 for v in flat_all if v["top"] >= v["n_word"] - 1)
    if flat_all:
        print("\n  主重音落在句末两词：%d/%d = %.1f%%（句末边界延长是已知偏置）"
              % (tail, len(flat_all), 100.0 * tail / len(flat_all)))


if __name__ == "__main__":
    main()
