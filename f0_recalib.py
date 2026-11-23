# -*- coding: utf-8 -*-
"""重新标定「句内 F0 突跳」判据。

原判据 = f0_max > 2.2 × 本轮全局中位。实测：真人旁白 F0 中位 73~76Hz，
真人自己的 f0_max 就在 200~248Hz（+16st 的正常语调上扬），于是真人 100% 中招。
⇒ 该判据对低音男声是结构性误报，必须换。

新判据：真正的「音高猛地翻上去」必须**跳过去并站住**。
  事件 = 相邻帧 |Δ| ≥ JST 半音，且跳前 5 帧与跳后 5 帧各自平稳（±1.5st）
  八度跟踪错误只闪 1~3 帧，站不住，自然被排除。
"""
import sys, os, json, io, argparse
sys.path.insert(0, "G:/_setup")
import numpy as np, soundfile as sf
import parselmouth

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
PITCH_FLOOR, PITCH_CEIL = 60, 250
JST = 10.0      # 判跳的半音门
HOLD = 5        # 跳后需连续站住的帧数（10ms/帧 → 50ms）
STAB = 1.5      # 「平稳」定义：±1.5 半音


def f0_track(y, sr):
    snd = parselmouth.Sound(np.ascontiguousarray(y, dtype=np.float64), sampling_frequency=sr)
    p = snd.to_pitch_ac(time_step=0.01, pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEIL,
                        voicing_threshold=0.20, silence_threshold=0.03)
    f = np.asarray(p.selected_array["frequency"], dtype=float)
    t = np.asarray(p.xs(), dtype=float)
    return f, t, snd


def events(y, sr):
    f, t, snd = f0_track(y, sr)
    v = f > 0
    if v.sum() < 12:
        return dict(n=0, n_raw=0, f0_med=None, f0_max=None, list=[])
    st = 12 * np.log2(np.maximum(f, 1e-6) / 100.0)
    n_raw = 0
    keep = []
    prev = None
    for i in range(1, len(f)):
        if not (v[i] and v[i - 1]) or abs(t[i] - t[i - 1]) > 0.03:
            continue
        dd = abs(st[i] - st[i - 1])
        if dd < JST:
            continue
        n_raw += 1
        # 跳前平稳：i-5..i-1 都在同一音区
        a = st[max(0, i - HOLD):i]
        a = a[a != 0]
        ok_pre = len(a) >= 3 and (a.max() - a.min()) <= 2 * STAB
        # 跳后站住：i..i+HOLD 基本不变
        b = st[i:i + HOLD]
        ok_post = len(b) >= HOLD and (b.max() - b.min()) <= 2 * STAB
        if ok_pre and ok_post:
            if prev is None or t[i] - prev > 0.08:
                keep.append((round(float(t[i]), 2), round(float(dd), 1), round(float(f[i]), 1)))
            prev = t[i]
    return dict(n=len(keep), n_raw=n_raw,
                f0_med=round(float(np.median(f[v])), 1),
                f0_max=round(float(f[v].max()), 1), list=keep)


def units_of(path, sec=0, whole=False):
    y, sr = sf.read(path, dtype="float64", always_2d=True)
    y = y.mean(1)
    if sec:
        y = y[: int(sec * sr)]
    if whole:
        return [(0.0, len(y) / sr, y, sr)]
    import narr_check as NC
    xs = NC.cut_units(y, sr)
    return [(t0, t1, y[int(t0 * sr): int(t1 * sr)], sr) for t0, t1 in xs]


def report(tag, items):
    rows = []
    for t0, t1, y, sr in items:
        if len(y) < int(0.3 * sr):
            continue
        d = events(y, sr)
        d["t0"], d["dur"] = round(t0, 2), round(t1 - t0, 2)
        rows.append(d)
    n = len(rows)
    nj = sum(1 for r in rows if r["n"] >= 2)
    med = [r["f0_med"] for r in rows if r["f0_med"]]
    mx = [r["f0_max"] for r in rows if r["f0_max"]]
    rawj = sum(1 for r in rows if r["n_raw"] >= 2)
    print("%-14s n=%-4d 反复跳(新,≥2次)=%5.1f%%  裸跳(旧口径,≥2次)=%5.1f%%  "
          "F0中位=%.0f  f0_max_p90=%.0f" % (
              tag, n, 100.0 * nj / max(n, 1), 100.0 * rawj / max(n, 1),
              np.median(med) if med else 0, np.percentile(mx, 90) if mx else 0))
    for r in rows:
        if r["n"]:
            print("    dur=%.1f n=%d n_raw=%d f0med=%.0f %s" % (
                r["dur"], r["n"], r["n_raw"], r["f0_med"], r["list"][:3]))
    return rows


if __name__ == "__main__":
    print("判据：|Δ|≥%.0fst 且跳前%.0fms/跳后%.0fms 各自 ±%.1fst 平稳\n" % (
        JST, HOLD * 10, HOLD * 10, STAB))
    report("真人 real_trim", units_of(r"E:/tts-models/acpp/out/calmdeep_final/real_trim.wav", 120))
    report("真人 wonder切片", units_of(
        r"G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav", 90))

    newdir = r"G:/_setup/_narr_new/out"
    if os.path.isdir(newdir):
        fs = sorted(f for f in os.listdir(newdir) if f.endswith(".wav"))
        items = []
        for f in fs:
            items += [(t0, t1, y, sr) for t0, t1, y, sr in units_of(os.path.join(newdir, f))]
        report("新链路(%d块)" % len(fs), items)

    olddir = r"G:/_setup/_audio_ch123/out"
    cast = [json.loads(l) for l in open(r"G:/_setup/_castle_en_ch123_cast.jsonl", encoding="utf-8")]
    ids = [c["id"] for c in cast if c.get("speaker") == "narrator"][:120]
    items = []
    for i in ids:
        p = os.path.join(olddir, i + ".wav")
        if os.path.exists(p):
            items += [(t0, t1, y, sr) for t0, t1, y, sr in units_of(p)]
    report("旧库旁白(120条)", items)
