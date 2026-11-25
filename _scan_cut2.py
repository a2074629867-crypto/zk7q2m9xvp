"""句中断裂扫描（v2）

用户的投诉口径：「所有语句都没有分割好，都是从中间断开的」。

判据不能只看「有没有静音」——正常对白句内本来就有 100~300ms 的停顿，
那是标点、是呼吸。真正的「断」有两个特征：

1. **数字零**：abs(y)==0 的采样段。人声、底噪、任何真实录音都不可能出
   绝对零，出现就是数字填充（我们自己在插停顿时灌过，模型生成时也会灌）。
   听感 = 突然死寂 → 再突然有声 = 一刀切断。
2. **崩塌式深谷**：句内某处能量掉到「该句峰值 −50dB 以下」，且前后
   各 30ms 内能量都高于 −35dB。真实语流不会有这种悬崖。

输出每条：零段数/总毫秒、最深谷位置与深度、判定。
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
STEP = 0.005          # 5ms 帧
FLOOR_REL = 50.0      # 掉到峰值以下 50dB 算深谷
EDGE_SKIP = 0.10      # 首尾各 100ms 不算句中


def frames(y, sr):
    n = int(STEP * sr)
    c = len(y) // n
    if c < 4:
        return np.array([]), n
    seg = y[:c * n].reshape(c, n)
    return 20 * np.log10(np.sqrt((seg ** 2).mean(1)) + 1e-12), n


def zero_runs(y, sr):
    """数字零段：abs==0 的连续采样。"""
    z = (y == 0)
    if not z.any():
        return []
    idx = np.flatnonzero(z)
    brk = np.flatnonzero(np.diff(idx) > 1)
    starts = np.r_[idx[0], idx[brk + 1]]
    ends = np.r_[idx[brk], idx[-1]]
    out = []
    for a, b in zip(starts, ends):
        ms = (b - a + 1) / sr * 1000
        if ms >= 3.0:                      # 3ms 以下算抖动，不算
            out.append((a / sr, b / sr, ms))
    return out


def scan(path):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    dur = len(y) / sr
    db, n = frames(y, sr)
    if len(db) < 8:
        return dict(dur=round(dur, 2), err="too_short")

    top = float(np.percentile(db, 95))
    thr = top - FLOOR_REL

    # 句内深谷：连续低于 thr 的帧段，两侧各 6 帧（30ms）都存在且高于 top-35
    quiet = db < thr
    inner = []
    i = 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j + 1 < len(quiet) and quiet[j + 1]:
                j += 1
            t0, t1 = i * STEP, (j + 1) * STEP
            if t0 > EDGE_SKIP and t1 < dur - EDGE_SKIP:
                pre = db[max(0, i - 6):i]
                post = db[j + 1:j + 7]
                if len(pre) and len(post) and pre.max() > top - 35 and post.max() > top - 35:
                    inner.append((round(t0, 2), round(t1, 2), int((t1 - t0) * 1000),
                                  round(float(db[i:j + 1].min()) - top, 1)))
            i = j + 1
        else:
            i += 1

    zr = zero_runs(y, sr)
    z_inner = [r for r in zr if r[0] > EDGE_SKIP and r[1] < dur - EDGE_SKIP]
    z_ms = sum(r[2] for r in zr)
    z_in_ms = sum(r[2] for r in z_inner)

    # 判定：句中数字零 >= 3ms，或有 >= 60ms 且深于 -45dB 的句内深谷
    hard = []
    if z_in_ms >= 3.0:
        hard.append("zero_in_sentence(%.0fms/%d段)" % (z_in_ms, len(z_inner)))
    deep = [g for g in inner if g[2] >= 60 and g[3] < -45]
    if deep:
        hard.append("deep_gap(%.0fms@%.2fs/%.0fdB)" % (deep[0][2], deep[0][0], deep[0][3]))

    return dict(dur=round(dur, 2), top=round(top, 1),
                zero_ms=round(z_ms, 1), zero_runs=len(zr),
                zero_inner_ms=round(z_in_ms, 1), zero_inner_runs=len(z_inner),
                gaps=len(inner), deepest=inner[:3],
                verdict="CUT" if hard else "OK", why=hard)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="wav 文件或目录")
    ap.add_argument("--json", default="")
    ap.add_argument("--ids", default="", help="逗号分隔，用于目录模式")
    a = ap.parse_args()

    files = []
    for p in a.paths:
        if os.path.isdir(p):
            if a.ids:
                files += [os.path.join(p, "%s.wav" % i.strip()) for i in a.ids.split(",") if i.strip()]
            else:
                files += sorted(glob.glob(os.path.join(p, "*.wav")))
        else:
            files.append(p)
    files = [f for f in files if os.path.exists(f)]

    res = {}
    for f in files:
        r = scan(f)
        res[os.path.basename(f)[:-4]] = r
        if r.get("verdict") == "CUT":
            print("%-14s %5.1fs %5.1fms零(句内%5.1f/%d段) 谷%2d 深%s  %s" % (
                os.path.basename(f)[:-4], r["dur"], r["zero_ms"], r["zero_inner_ms"],
                r["zero_inner_runs"], r["gaps"],
                r["deepest"][0][3] if r["deepest"] else "-", "; ".join(r["why"])))

    cut = [k for k, v in res.items() if v.get("verdict") == "CUT"]
    print()
    print("共 %d 条，判定 CUT %d 条（%.0f%%）" % (len(res), len(cut), 100 * len(cut) / max(1, len(res))))
    if a.json:
        json.dump(res, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("->", a.json)


if __name__ == "__main__":
    sys.exit(main())
