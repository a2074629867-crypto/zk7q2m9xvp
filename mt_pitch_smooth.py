# -*- coding: utf-8 -*-
"""mt_pitch_smooth.py —— 旁白起伏压缩：F0 轮廓平滑（自适应强度）。

    python mt_pitch_smooth.py --dir _mt_raw_s42 --out _mt_smooth --limit 30
    python mt_pitch_smooth.py --wav N0004.wav --out /tmp/x.wav

## 为什么是平滑，不是幂律压缩

幂律压缩 `new = med*(f/med)^alpha` 会把**真实语调起伏一起压掉**，所以
同一 alpha 在不同文件上效果差 1.5 倍（N0005 a=0.5 只到 0.82，N0004 a=0.9 就到 0.69），
级联两次 IQR 口径实测 0.204（16/20 过度）。见 skill 18.35。

平滑只去掉**小尺度抖动**（移动中值+均值，窗 30~310ms），保留大起伏。
实测比值单调：w3 0.84~1.10 / w7 0.66~1.34。

## 音质代价（N0004/N0019/N0010 实测）

    MFCC cos 0.9998~1.0000   F1-3 变化 ≤20Hz   HNR −1.91→−1.29（变好）
    RMS −0.2~−0.3dB          时长完全不变

## 为什么自适应

N0010 在 w=5 时 IQR 反而 4.72→5.60（重合成后 F0 提取的倍频/段边界效应）。
所以不能固定窗口，必须「测→不够继续加窗→取最优」，且每次都从**原文件**重建，
不在上一次结果上叠加（避免 PSOLA 多次级联累积失真）。
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
import numpy as np
import parselmouth
from parselmouth.praat import call

from mt_matt_contour import segs_of, f0_track, shape_feats

# 马修母带标定（matt_contour.json，627 段）
TARGET_HI = 2.77   # 马修 p75：压到这条线才算「同量级」
TARGET_LO = 1.10   # 马修 p10：低于此是「平」，也不对
HARD_HI = 4.18     # 马修 p90：超过这条必须处理
WINDOWS = [3, 5, 7, 11, 15, 21, 31]   # 帧（10ms/帧）→ 30~310ms


def _iqr_of_segs(x, sr, segs):
    v = []
    for a, b in segs:
        tr, st = f0_track(x, sr, a, b)
        if tr is None:
            continue
        v.append(shape_feats(tr, st)["iqr_st"])
    return (float(np.median(v)) if v else None), len(v)


def measure(path):
    segs, x, sr = segs_of(path)
    iqr, n = _iqr_of_segs(x, sr, segs)
    return iqr, n


def _smooth(v, win):
    k = win // 2 * 2 + 1
    pad = k // 2
    x = np.pad(v, (pad, pad), mode="edge")
    med = np.array([np.median(x[i:i + k]) for i in range(len(v))])
    x2 = np.pad(med, (pad, pad), mode="edge")
    return np.array([x2[i:i + k].mean() for i in range(len(v))])


def _apply(src, dst, win):
    snd = parselmouth.Sound(src)
    manip = call(snd, "To Manipulation", 0.01, 60, 250)
    tier = call(manip, "Extract pitch tier")
    n = call(tier, "Get number of points")
    if n < 5:
        return False
    ts = np.array([call(tier, "Get time from index", i + 1) for i in range(n)])
    fv = np.array([call(tier, "Get value at index", i + 1) for i in range(n)])
    ok = fv > 0
    idx = np.where(ok)[0]
    if len(idx) < 5:
        return False
    nv = fv.copy()
    nv[idx] = _smooth(fv[idx], win)
    call(tier, "Remove points between", 0.0, 1e9)
    for t, f in zip(ts, nv):
        if f > 0:
            call(tier, "Add point", float(t), float(f))
    call([manip, tier], "Replace pitch tier")
    call(manip, "Get resynthesis (PSOLA)").save(dst, "WAV")
    return True


def process(src, dst, target_hi=TARGET_HI, verbose=False):
    """自适应平滑。返回 (info_dict, status)。"""
    base, nseg = measure(src)
    if base is None:
        return None, "SHORT"
    if base <= target_hi:
        if os.path.abspath(src) != os.path.abspath(dst):
            import shutil
            shutil.copy2(src, dst)
        return {"base": base, "final": base, "win": 0, "n_seg": nseg}, "NOOP"
    tmp = dst + ".tmp.wav"
    best = (base, None, 0)
    tried = []
    for w in WINDOWS:
        if not _apply(src, tmp, w):
            continue
        v, _ = measure(tmp)
        if v is None:
            continue
        tried.append((w, round(v, 3)))
        if v < best[0]:
            best = (v, w, w)
        if verbose:
            print("    w=%-2d → %.2f" % (w, v), flush=True)
        if v <= target_hi:
            break
    if best[1] is None:
        if os.path.exists(tmp):
            os.unlink(tmp)
        return {"base": base, "final": base, "win": 0, "n_seg": nseg,
                "tried": tried}, "FAIL"
    # 用最优窗口重新生成到正式路径
    _apply(src, dst, best[1])
    if os.path.exists(tmp):
        os.unlink(tmp)
    st = "OK" if best[0] <= target_hi else ("PARTIAL" if best[0] <= HARD_HI else "STILL_HIGH")
    return {"base": round(base, 3), "final": round(best[0], 3),
            "win": best[1], "ratio": round(best[0] / base, 3),
            "n_seg": nseg, "tried": tried}, st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir")
    ap.add_argument("--out")
    ap.add_argument("--wav")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--target", type=float, default=TARGET_HI)
    ap.add_argument("--json")
    ap.add_argument("--units", help="只处理指定章/单元：ch1 或 N0001,N0002")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if a.wav:
        dst = a.out or a.wav.replace(".wav", "_sm.wav")
        info, st = process(a.wav, dst, a.target, verbose=True)
        print(json.dumps({"status": st, **info}, ensure_ascii=False, indent=1))
        return

    if not a.dir or not a.out:
        ap.error("需要 --dir 与 --out")
    os.makedirs(a.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.dir, "*.wav")))
    if a.units:
        want = None
        if a.units.startswith("ch"):
            S = json.load(open("G:/_setup/_mt_loop_state.json", encoding="utf-8"))["units"]
            want = {n for n, u in S.items() if u["ch"] == a.units}
        else:
            want = set(a.units.split(","))
        files = [f for f in files if os.path.splitext(os.path.basename(f))[0] in want]
    if a.limit:
        files = files[:a.limit]

    rows = {}
    from collections import Counter
    for i, f in enumerate(files):
        n = os.path.splitext(os.path.basename(f))[0]
        dst = os.path.join(a.out, n + ".wav")
        info, st = process(f, dst, a.target)
        if info is None:
            rows[n] = {"status": st}
            continue
        rows[n] = {"status": st, **info}
        if st == "NOOP" and os.path.exists(dst) is False:
            pass
        if (i + 1) % 20 == 0:
            print("  %d / %d" % (i + 1, len(files)), flush=True)

    c = Counter(r["status"] for r in rows.values())
    done = [r for r in rows.values() if "base" in r and r["status"] != "NOOP"]
    print("\n=== 处理 %d 条 ===" % len(files))
    print("  " + "  ".join("%s %d" % (k, v) for k, v in sorted(c.items())))
    if done:
        b = np.array([r["base"] for r in done])
        f2 = np.array([r["final"] for r in done])
        print("  需处理的 %d 条：IQR 中位 %.2f → %.2f（比值 %.2f）"
              % (len(done), np.median(b), np.median(f2),
                 np.median(f2 / np.maximum(b, 1e-6))))
        print("  窗口分布 " + "  ".join("w%d:%d" % (k, v) for k, v in
                                       sorted(Counter(r["win"] for r in done).items())))
        print("  仍在 p75 以上 %d 条 / 超 p90 %d 条"
              % (int((f2 > TARGET_HI).sum()), int((f2 > HARD_HI).sum())))
    if a.json:
        json.dump(rows, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("  → %s" % a.json)


if __name__ == "__main__":
    main()
