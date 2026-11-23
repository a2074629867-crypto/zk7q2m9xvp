"""_prom_what.py —— 反推：wpt 的 prominence 到底在测什么？

在答案确定的最小对立对上已经发现：强度对重音位置零区分（8/16=50%），
真正有信号的是 F0（10/16）与时长（9/16），二者互补后 13/16（p=0.024）。

若我们的门禁依赖的 prominence 主要吃强度，那它在「短语第二重音」这类
F0 不抬、只拉长的地方就会系统性失效。

方法：取 .prom 的逐词区间，用 parselmouth 在**同一区间**算
      F0 中位（半音）、RMS 能量、区间时长，
      再与 prominence / boundary 求句内 Spearman 相关（句内去均值，避免跨句量纲混）。

跑法：G:/Python310/python.exe _prom_what.py --n 40
"""
import argparse
import glob
import json
import math
import os
import random
import statistics

import numpy as np

PROM = "G:/_setup/_wpt_out"
RAW_DIRS = ["G:/_setup/_mt_raw_s42", "G:/_setup/_mt_raw_s1234", "G:/_setup/_mt_raw_rate"]


def spearman(x, y):
    n = len(x)
    if n < 4:
        return None
    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(x), rank(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx > 1e-9 and dy > 1e-9 else None


def read_prom(p):
    """prom 6 列：文件名 | 起始 | 结束 | 词 | prominence | boundary。"""
    rows = []
    for line in open(p, encoding="utf-8"):
        x = line.rstrip("\n").split("\t")
        if len(x) < 6:
            continue
        try:
            rows.append((float(x[1]), float(x[2]), x[3], float(x[4]), float(x[5])))
        except ValueError:
            continue
    return rows


def find_wav(base):
    # base = _mt_raw_s42__N0001 → G:/_setup/_mt_raw_s42/N0001.wav
    if "__" not in base:
        return None
    d, uid = base.split("__", 1)
    p = os.path.join("G:/_setup", d, uid + ".wav")
    return p if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--out", default="G:/_setup/_prom_what.json")
    a = ap.parse_args()

    import parselmouth
    from parselmouth.praat import call

    files = sorted(glob.glob(os.path.join(PROM, "*.prom")))
    random.seed(11)
    random.shuffle(files)

    acc = []
    for f in files:
        if len(acc) >= a.n:
            break
        base = os.path.splitext(os.path.basename(f))[0]
        wav = find_wav(base)
        if not wav:
            continue
        rows = read_prom(f)
        words = [(t0, t1, w, pr) for t0, t1, w, pr, _b in rows
                 if w and not all(c in ".,;:!?-\"'()[]—–" for c in w)]
        if len(words) < 5:
            continue
        try:
            snd = parselmouth.Sound(wav)
        except Exception:
            continue

        rec = []
        for t0, t1, w, pr in words:
            dur = t1 - t0
            if dur < 0.03:
                continue
            # 区间内的 F0 与强度
            try:
                part = snd.extract_part(from_time=max(0, t0 - 0.005),
                                        to_time=min(snd.duration, t1 + 0.005),
                                        preserve_times=False)
                pit = part.to_pitch(time_step=0.005, pitch_floor=60, pitch_ceiling=400)
                f0 = pit.selected_array["frequency"]
                f0 = f0[f0 > 0]
                f0m = float(np.median(f0)) if len(f0) else 0.0
                inten = part.to_intensity(time_step=0.005, minimum_pitch=60)
                iv = inten.values[0]
                iv = iv[np.isfinite(iv)]
                rms = float(np.max(iv)) if len(iv) else 0.0
            except Exception:
                continue
            rec.append(dict(w=w, dur=dur, f0=f0m, int_db=rms, prom=pr))

        if len(rec) < 5:
            continue
        # 句内只保留 F0 有的
        rec = [r for r in rec if r["f0"] > 0]
        if len(rec) < 5:
            continue
        acc.append(dict(file=base, words=rec))

    print("可用句 %d，词 %d" % (len(acc), sum(len(x["words"]) for x in acc)))

    # 全局相关
    def corr(key):
        X, Y = [], []
        for s in acc:
            X += [w["prom"] for w in s["words"]]
            Y += [w[key] for w in s["words"]]
        r = spearman(X, Y)
        return r

    print("\n=== prominence 与各声学量的全局 Spearman 相关 ===")
    for k, label in [("f0", "F0 中位 (Hz)"), ("dur", "词时长 (s)"), ("int_db", "强度峰值 (dB)")]:
        print("  %-14s %s" % (label, "%.3f" % corr(k) if corr(k) is not None else "n/a"))

    # 句内相关（去掉跨句量纲差异）
    print("\n=== 句内相关（每句内先算，再取中位）===")
    for k, label in [("f0", "F0 中位"), ("dur", "词时长"), ("int_db", "强度峰值")]:
        rs = []
        for s in acc:
            r = spearman([w["prom"] for w in s["words"]], [w[k] for w in s["words"]])
            if r is not None:
                rs.append(r)
        if rs:
            rs.sort()
            print("  %-10s 中位 %.3f  p25 %.3f  p75 %.3f  n=%d"
                  % (label, statistics.median(rs), rs[len(rs) // 4], rs[3 * len(rs) // 4], len(rs)))

    # 半音化后的 F0 与 prominence
    print("\n=== 用半音（句内相对）重算 ===")
    rs = []
    for s in acc:
        f0s = [w["f0"] for w in s["words"]]
        med = statistics.median(f0s)
        if med <= 0:
            continue
        st = [12 * math.log2(max(f, 1) / med) for f in f0s]
        r = spearman([w["prom"] for w in s["words"]], st)
        if r is not None:
            rs.append(r)
    if rs:
        rs.sort()
        print("  F0(半音) 中位 %.3f  p25 %.3f  p75 %.3f  n=%d"
              % (statistics.median(rs), rs[len(rs) // 4], rs[3 * len(rs) // 4], len(rs)))

    json.dump(acc, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写出 %s" % a.out)


if __name__ == "__main__":
    main()
