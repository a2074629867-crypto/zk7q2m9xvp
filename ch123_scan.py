# -*- coding: utf-8 -*-
"""全库逐段体检（内容无关指标）：F0 / 电平 / HNR / 结尾硬切。

为什么不用声纹余弦：短段循环补长后，不同词的余弦天然只有 0.1-0.3
（实测同一句话内部 "Look" 段也只有 0.22），阈值无法设。
F0、电平、HNR 与「说了哪个词」无关，只跟发声状态有关，才是可靠判据。

判据（任一条命中即报）：
  F0 跨度 > 40Hz          → 前后像两个人（L068 的「怪物」就是这么来的）
  F0 任一段 > 305Hz       → 进假声区，真在喊（L053 happy 破音）
  相邻段电平差 > 6dB      → 忽大忽小
  HNR 比本文件中位低 6dB  → 某段发毛发炸
  结尾 5ms 内掉 > 40dB    → 硬切（L083 father 没读完）
"""
import os
import sys
import glob
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB
import ch123_stab as ST

SIL_DB = -45.0
MIN_SEG = 0.20
# 社区 GPE 口径：音高偏差 >20%（约 316 cent）算跳。段间互比取 300 cent。
# 注意：段间互比没有 ground truth，句界自然降调也会命中 ⇒ 只作提示，须重生成验证是否固有。
F0_JUMP_CENTS = 300.0
F0_CEIL = 305.0
LVL_DIFF_MAX = 6.0
HNR_DROP = 6.0
HF_RATIO_MAX = 50.0
CUT_JUMP = 40.0


def hnr(x, sr):
    x = x - x.mean()
    if len(x) < 512 or (x ** 2).sum() < 1e-9:
        return 0.0
    ac = np.correlate(x, x, "full")[len(x) - 1:]
    ac = ac / (ac[0] + 1e-12)
    lo, hi = int(sr / 500), int(sr / 60)
    if hi >= len(ac):
        return 0.0
    r = float(ac[lo:hi].max())
    return 10 * np.log10(max(r, 1e-6) / (1 - max(r, 1e-6) + 1e-9))


def hf_ratio(seg, sr):
    """4kHz 以上能量占比。人声一般 <15%；>50% 说明这一段是气流噪声，不是说话。"""
    if len(seg) < 512:
        return 0.0
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    tot = X.sum() + 1e-20
    return float(X[f >= 4000].sum() / tot * 100)


def seg_stats(a, sr, s0, s1):
    seg = a[int(s0 * sr):int(s1 * sr)]
    f0 = ST.f0_track(a, sr)
    fs = f0[int(s0 / 0.01):int(s1 / 0.01)]
    fs = fs[~np.isnan(fs)]
    return {
        "t0": s0, "t1": s1, "dur": s1 - s0,
        "f0": float(np.median(fs)) if len(fs) else 0.0,
        "db": RB.rms_voiced_db(seg, sr),
        "hnr": hnr(seg, sr),
        "hf": hf_ratio(seg, sr),
    }


def tail_jump(a, sr, end):
    """结尾 5ms 粒度的最大跳变（dB）。只统计跳变前 > -50dB 的，
    因为淡出到数字零必然从 -70 跳到 -240，那是听不见的，不算硬切。"""
    w = int(0.005 * sr)
    prof = []
    for i in range(int((end - 0.06) * sr), min(len(a), int((end + 0.015) * sr)), w):
        s = a[i:i + w]
        prof.append(20 * np.log10(np.sqrt((s ** 2).mean()) + 1e-12))
    if len(prof) < 3:
        return 0.0
    d = [prof[i] - prof[i + 1] for i in range(len(prof) - 1) if prof[i] > -50]
    return float(max(d)) if d else 0.0


def check(path):
    a, sr = sf.read(path, dtype="float32", always_2d=True)
    a = a.mean(1)
    segs = [(s0, s1) for s0, s1 in RB.split_at_silence(a, sr, min_gap=0.12)
            if s1 - s0 >= MIN_SEG]
    if not segs:
        return None
    info = [seg_stats(a, sr, s0, s1) for s0, s1 in segs]
    f0s = [x["f0"] for x in info if x["f0"] > 0]
    span = (max(f0s) - min(f0s)) if len(f0s) >= 2 else 0.0
    lvl = [x["db"] for x in info]
    lvl_max = max(abs(lvl[i] - lvl[i - 1]) for i in range(1, len(lvl))) if len(lvl) >= 2 else 0.0
    hnrs = [x["hnr"] for x in info]
    hnr_med = float(np.median(hnrs)) if hnrs else 0.0
    hnr_low = min(hnrs) if hnrs else 0.0
    jump = tail_jump(a, sr, segs[-1][1])

    issues = []
    # 相邻段 F0 跳变：只比长度 >=0.35s 的段，短段（单个词）F0 估计不可靠。
    # ★ 判据用 cent（1200*log2 比值），不用线性 Hz —— 社区 GPE 口径。
    #   线性 50Hz 在 200Hz 处是 25%、在 400Hz 处只有 12.5%，高低音区宽严差一倍。
    jump_hi = 0.0      # cents
    jump_hz = 0.0      # 仅用于显示
    for i in range(1, len(info)):
        if info[i]["dur"] >= 0.35 and info[i - 1]["dur"] >= 0.35:
            a0, a1 = info[i - 1]["f0"], info[i]["f0"]
            if a0 > 0 and a1 > 0:
                d = abs(1200.0 * np.log2(a1 / a0))
                if d > jump_hi:
                    jump_hi = d
                    jump_hz = abs(a1 - a0)
    if jump_hi > F0_JUMP_CENTS:
        issues.append("F0邻段跳%.0fcent(%.0fHz)" % (jump_hi, jump_hz))
    hi = [(i, x["f0"]) for i, x in enumerate(info) if x["f0"] > F0_CEIL]
    if hi:
        issues.append("p%s F0>305" % ",".join(str(i) for i, _ in hi))
    if lvl_max > LVL_DIFF_MAX:
        issues.append("电平差%.0f" % lvl_max)
    if hnr_med - hnr_low > HNR_DROP:
        issues.append("HNR低%.0f" % (hnr_med - hnr_low))
    # 只对 >=0.5s 的段判高频噪声：短词可能被 /s/ 这类擦音占满，会误报
    hf_bad = [(i, x["hf"]) for i, x in enumerate(info)
              if x["hf"] > HF_RATIO_MAX and x["dur"] >= 0.5]
    if hf_bad:
        issues.append("p%s 高频噪声%.0f%%" % (",".join(str(i) for i, _ in hf_bad), hf_bad[0][1]))
    if jump > CUT_JUMP:
        issues.append("结尾硬切%.0f" % jump)
    return {"file": os.path.basename(path)[:-4], "n": len(segs), "dur": len(a) / sr,
            "info": info, "span": jump_hi, "span_hz": jump_hz, "lvl_max": lvl_max,
            "hnr": hnr_med, "jump": jump, "issues": issues}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "ch123_clean"
    files = sorted(glob.glob(os.path.join(src, "*.wav")))
    bad = []
    for f in files:
        r = check(f)
        if not r:
            continue
        if r["issues"]:
            bad.append(r)
    print("扫描 %d 条，%d 条有疑点\n" % (len(files), len(bad)))
    for r in bad:
        print("%-6s %d段 %.2fs  %s" % (r["file"], r["n"], r["dur"], " | ".join(r["issues"])))
        print("        " + "  ".join("p%d %.0fHz %.0fdB" % (i, x["f0"], x["db"])
                                     for i, x in enumerate(r["info"])))
    if not bad:
        print("全部通过")


if __name__ == "__main__":
    main()
