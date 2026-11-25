# -*- coding: utf-8 -*-
"""
_band.py —— 「区间通过制」的量化底座。

用户的判据形式（2026-11-25 03:2x）：
  「不需要完全一致，只需要一个正确的区间。可以是 A 也可以是 B，只要 AB 听感都不错就通过；
    但如果是 C、听感很差，就不行。」

⇒ 判据不是点匹配（和我比某个目标值差多少），而是**区间归属**：落在人声分布的学习区间内 = PASS。

本脚本只在"峰-峰"这一层做事，因为 F0 的峰是重音的物理载体，且**不需要转写**就能在人声上算：
  1. 基频轨迹 → 中值滤波 → 在连续有声段内找局部峰（地形突出度 prominence）
  2. 相邻峰落差 Δst（半音，说话人无关）
  3. 峰后下降幅度 descent_st
输出每句话的这几项，再聚合出分布区间。

用法:
  python _band.py E:/ttsds/data/ref_human --tag human
  python _band.py _audio_ch123/out --tag old
  python _band.py _regen_final --tag new
  python _band.py --report          # 三组分布对照
"""
import sys, os, glob, json, math, argparse
import numpy as np
import soundfile as sf
import parselmouth
from scipy.signal import medfilt

HOP = 0.01
FLOOR, CEIL = 60.0, 350.0
MIN_PROM = 1.5      # st，低于此不算一个峰（Praat 常用 2st，这里取略松）
MIN_DIST = 0.12     # s，两峰最小间隔
MIN_RUN = 0.15      # s，有声段最短长度


def f0_track(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    p = snd.to_pitch(time_step=HOP, pitch_floor=FLOOR, pitch_ceiling=CEIL)
    f0 = p.selected_array["frequency"].astype(float)
    t = p.xs()
    return t, f0


def peaks_in_run(t, st, min_prom=MIN_PROM, min_dist=MIN_DIST):
    """在一段连续有声的 st 序列里找峰：局部极大 + 地形突出度 + 最小间隔。"""
    n = len(st)
    if n < 5:
        return []
    cand = []
    for i in range(1, n - 1):
        if st[i] >= st[i - 1] and st[i] > st[i + 1]:
            # 向右找谷、向左找谷
            j = i + 1
            while j < n and st[j] <= st[j - 1]:
                j += 1
            rv = st[j - 1] if j - 1 < n else st[i]
            k = i - 1
            while k >= 0 and st[k] <= st[k + 1]:
                k -= 1
            lv = st[k + 1] if k + 1 >= 0 else st[i]
            prom = st[i] - max(lv, rv)
            if prom >= min_prom:
                cand.append((i, st[i], prom))
    # 最小间隔：贪心保留突出度大的
    cand.sort(key=lambda x: -x[2])
    kept = []
    for i, v, prom in cand:
        if all(abs(t[i] - t[j]) >= min_dist for j, _, _ in kept):
            kept.append((i, v, prom))
    kept.sort(key=lambda x: x[0])
    return kept


def sent_stats(path):
    t, f0 = f0_track(path)
    if not np.any(f0 > 0):
        return None
    st = np.where(f0 > 0, 12 * np.log2(np.maximum(f0, 1) / 100.0), np.nan)
    # 有声段切分
    v = f0 > 0
    runs = []
    i = 0
    n = len(v)
    while i < n:
        if v[i]:
            j = i
            while j < n and v[j]:
                j += 1
            if (j - i) * HOP >= MIN_RUN:
                runs.append((i, j))
            i = j
        else:
            i += 1

    all_peaks = []
    for a, b in runs:
        seg = st[a:b]
        seg = np.where(np.isnan(seg), np.nanmedian(seg), seg)
        if len(seg) >= 5:
            seg = medfilt(seg, 5)
        pk = peaks_in_run(t[a:b], seg)
        for i, val, prom in pk:
            all_peaks.append((t[a + i], val, prom))

    if len(all_peaks) < 2:
        return {"file": os.path.basename(path), "dur": round(t[-1] - t[0], 2),
                "n_peaks": len(all_peaks), "deltas": [], "descents": [], "proms": []}

    all_peaks.sort(key=lambda x: x[0])
    deltas = [round(all_peaks[i + 1][1] - all_peaks[i][1], 2) for i in range(len(all_peaks) - 1)]
    # 峰后下降：峰到下一个更低的谷（用相邻峰之间的最低点近似）
    descents = []
    for i in range(len(all_peaks) - 1):
        ta, va, _ = all_peaks[i]
        tb, vb, _ = all_peaks[i + 1]
        m = (t >= ta) & (t <= tb) & (f0 > 0)
        if m.sum() >= 3:
            low = np.nanmin(st[m])
            descents.append(round(va - low, 2))
    return {"file": os.path.basename(path), "dur": round(t[-1] - t[0], 2),
            "n_peaks": len(all_peaks), "deltas": deltas, "descents": descents,
            "proms": [round(p, 2) for _, _, p in all_peaks]}


def run_dir(d, tag, out_dir="_band"):
    os.makedirs(out_dir, exist_ok=True)
    fs = sorted(glob.glob(os.path.join(d, "*.wav")))
    rows = []
    for k, p in enumerate(fs):
        r = sent_stats(p)
        if r:
            r["file"] = r["file"][:-4]
            rows.append(r)
        if k % 100 == 0:
            print(f"  {tag} {k}/{len(fs)}", flush=True)
    json.dump(rows, open(f"{out_dir}/{tag}.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{tag}: {len(rows)} files → {out_dir}/{tag}.json")


def pct(x, q):
    return round(float(np.percentile(x, q)), 2) if len(x) else None


def report():
    sets = {}
    for tag in ("human", "old", "new"):
        p = f"_band/{tag}.json"
        if not os.path.exists(p):
            print("missing", p); continue
        rows = json.load(open(p, encoding="utf-8"))
        d = [abs(x) for r in rows for x in r["deltas"]]
        dd = [x for r in rows for x in r["descents"]]
        pr = [x for r in rows for x in r["proms"]]
        rate = [r["n_peaks"] / r["dur"] for r in rows if r["dur"] > 1]
        sets[tag] = dict(n=len(rows), deltas=d, desc=dd, prom=pr, rate=rate)
        print(f"{tag:6s} files={len(rows):4d}  峰/秒={np.median(rate):.2f}  "
              f"|Δ峰| p10/p50/p90={pct(d,10)}/{pct(d,50)}/{pct(d,90)}  "
              f"下降 p10/p50/p90={pct(dd,10)}/{pct(dd,50)}/{pct(dd,90)}  "
              f"突出度 p50={pct(pr,50)}")
    if "human" in sets:
        lo, hi = np.percentile(sets["human"]["deltas"], [10, 90])
        print(f"\n人声 |Δ峰| 中心区间 = [{lo:.2f}, {hi:.2f}] st")
        for tag in ("old", "new"):
            if tag not in sets: continue
            d = np.array(sets[tag]["deltas"])
            inside = np.mean((d >= lo) & (d <= hi)) * 100
            above = np.mean(d > hi) * 100
            print(f"  {tag}: 落在区间内 {inside:.1f}%   超出上界 {above:.1f}%   "
                  f"（超出上界 = 峰间跳得比真人还猛）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--tag")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.report:
        report()
    elif a.dir and a.tag:
        run_dir(a.dir, a.tag)
    else:
        ap.print_help()
