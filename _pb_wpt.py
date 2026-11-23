"""_pb_wpt.py —— 用同一套音节切分，测 wpt 的 prominence 在最小对立对上得几分。

做法：
  1. 用 _pb_stress.find_nuclei 找音节核，取两核之间能量最低点作为切分点
  2. 写成 2 区间 TextGrid（tier 名 words），跑 wavelet_prosody_toolkit
  3. 比较两个区间的 prominence，看是否与「重音在前/在后」一致

这样 wpt 与我们自建的 F0+时长 判据用的是**完全相同的时间切分**，
分数可以直接对比，不受对齐差异干扰。
"""
import argparse
import glob
import json
import math
import os
import shutil
import subprocess
import sys

sys.path.insert(0, "G:/_setup")
from _pb_stress import MAP, find_nuclei  # noqa: E402

WPTPY = "G:/_setup/wpt_venv/Scripts/python.exe"
CFG = "G:/_setup/_wpt/mt.yaml"


def split_point(path):
    """返回 (切分点, 有声结束点, 音节核数)。有声结束点用于 TextGrid 的 xmax，
    否则尾部静音会被算进最后一个区间，把它的时长拉长 —— 而 wpt 的 prominence
    主要由时长驱动（ρ=0.712），这一步会系统性偏向「后半更重」。"""
    import numpy as np
    import parselmouth
    snd = parselmouth.Sound(path)
    inten = snd.to_intensity(minimum_pitch=50, time_step=0.005)
    v = inten.values[0]
    t0, dt = inten.x1, inten.dx
    v = np.where(np.isfinite(v), v, -np.inf)

    thr = v.max() - 25.0
    hi = len(v) - 1
    while hi > 0 and v[hi] < thr:
        hi -= 1
    voiced_end = t0 + hi * dt

    ns = find_nuclei(path)
    if len(ns) < 2:
        return None, voiced_end, len(ns)
    if len(ns) == 2:
        a = int(round((ns[0][0] - t0) / dt))
        b = int(round((ns[1][0] - t0) / dt))
    else:
        h = len(ns) // 2
        a = int(round((ns[h - 1][0] - t0) / dt))
        b = int(round((ns[h][0] - t0) / dt))
    a = max(0, min(a, len(v) - 1))
    b = max(a + 1, min(b, len(v) - 1))
    seg = v[a:b + 1]
    cut = t0 + (a + int(np.argmin(seg))) * dt
    return cut, voiced_end, len(ns)


def write_tg(path, dur, cut):
    txt = '''File type = "ooTextFile"
Object class = "TextGrid"

xmin = 0
xmax = %.6f
tiers? <exists>
size = 1
item []:
    item [1]:
        class = "IntervalTier"
        name = "words"
        xmin = 0
        xmax = %.6f
        intervals: size = 2
        intervals [1]:
            xmin = 0
            xmax = %.6f
            text = "part1"
        intervals [2]:
            xmin = %.6f
            xmax = %.6f
            text = "part2"
''' % (dur, dur, cut, cut, dur)
    open(path, "w", encoding="utf-8", newline="\n").write(txt)


def read_prom(p):
    rows = []
    for line in open(p, encoding="utf-8"):
        x = line.rstrip("\n").split("\t")
        if len(x) < 6:
            continue
        try:
            rows.append((x[3], float(x[4])))
        except ValueError:
            continue
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--tag", default="wpt")
    a = ap.parse_args()

    import wave

    stage = "G:/_setup/_pb/_stage_%s" % a.tag
    promdir = "G:/_setup/_pb/_prom_%s" % a.tag
    for d in (stage, promdir):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)

    meta = {}
    for f in glob.glob(os.path.join(a.dir, "*_trial_*.wav")):
        i = int(os.path.basename(f).split("_trial_")[1].split(".")[0])
        if i not in MAP:
            continue
        cut, voiced_end, n = split_point(f)
        if cut is None:
            print("  skip trial %d（音节核 %d）" % (i, n))
            continue
        with wave.open(f, "rb") as w:
            dur = w.getnframes() / w.getframerate()
        base = os.path.splitext(os.path.basename(f))[0]
        shutil.copy2(f, os.path.join(stage, base + ".wav"))
        write_tg(os.path.join(stage, base + ".TextGrid"), voiced_end, cut)
        meta[base] = dict(trial=i, cut=round(cut, 3), dur=round(dur, 3),
                          voiced_end=round(voiced_end, 3), nuclei=n)

    print("staged %d" % len(meta))
    r = subprocess.run([WPTPY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                        "-j", "6", "-c", CFG, "-o", promdir, stage],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("wpt rc=%d" % r.returncode)
    if r.returncode != 0:
        print((r.stderr or "")[-500:])

    ok = tot = 0
    print("\n%-14s %-5s %-8s %-8s %s" % ("text", "expect", "part1", "part2", "判定"))
    for base, m in sorted(meta.items(), key=lambda kv: kv[1]["trial"]):
        pf = os.path.join(promdir, base + ".prom")
        if not os.path.exists(pf):
            print("  !! %s 无 prom" % base)
            continue
        rows = read_prom(pf)
        if len(rows) < 2:
            print("  !! %s prom 行数 %d" % (base, len(rows)))
            continue
        p1, p2 = rows[0][1], rows[1][1]
        txt, expect = MAP[m["trial"]]
        got = "head" if p1 > p2 else "tail"
        mark = "OK" if got == expect else "XX"
        if got == expect:
            ok += 1
        tot += 1
        print("%-14s %-5s %+7.3f %+7.3f  %s  %s" % (txt, expect, p1, p2, mark, got))

    print("\n=== wpt prominence：%d/%d = %.3f ===" % (ok, tot, ok / tot if tot else 0))
    if tot:
        z = (abs(ok - tot / 2) - 0.5) / (0.5 * tot ** 0.5)
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
        print("二项 p = %.3f" % p)


if __name__ == "__main__":
    main()
