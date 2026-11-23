"""_pb_stress.py —— 用 ProsodyBench 最小对立对检验「重音位置测量」是否可信。

语言学铁律：
  合写复合词  GREENHOUSE / BLACKBIRD / DARKROOM ...  主重音在**第一**成分
  分写短语    GREEN HOUSE / BLACK BIRD / DARK ROOM ... 主重音在**第二**成分

如果测量系统连这个都判不对，那它给出的逐词 prominence 就不能当门禁依据。
反之，如果 8 对里能判对绝大多数，说明测量在「重音落在哪个成分」这个粒度上是可信的。

方法：parselmouth 找音节核（强度局部峰，峰间需有 ≥2dB 的谷），
      每个核算 [强度峰, F0 中位, 核时长]，z-score 后加权，
      比较前半核 vs 后半核的平均强度，判「重音在前 / 在后」。

跑法：G:/Python310/python.exe _pb_stress.py --dir _pb/el
"""
import argparse
import glob
import json
import os
import statistics
import warnings

import numpy as np

warnings.filterwarnings("ignore")

# trial 号 -> (文本, 期望重音位置 head/tail)
MAP = {
    1: ("GREENHOUSE", "head"), 13: ("GREEN HOUSE", "tail"),
    2: ("WHITEBOARD", "head"), 10: ("WHITE BOARD", "tail"),
    7: ("DARKROOM", "head"), 9: ("DARK ROOM", "tail"),
    12: ("WETSUIT", "head"), 8: ("WET SUIT", "tail"),
    4: ("BLACKBIRD", "head"), 6: ("BLACK BIRD", "tail"),
    15: ("HOTDOG", "head"), 11: ("HOT DOG", "tail"),
    16: ("BLUEBELL", "head"), 14: ("BLUE BELL", "tail"),
    5: ("BULLSEYE", "head"), 3: ("BULL'S EYE", "tail"),
}


def find_nuclei(path, min_gap_db=2.0, rel_floor=25.0):
    """返回 [(t_peak, int_peak_db, f0_med, dur)] —— De Jong & Wempe 的简化版。"""
    import parselmouth
    snd = parselmouth.Sound(path)
    inten = snd.to_intensity(minimum_pitch=50, time_step=0.01)
    v = inten.values[0]
    t0, dt = inten.x1, inten.dx
    v = np.where(np.isfinite(v), v, -np.inf)

    pitch = snd.to_pitch(time_step=0.01, pitch_floor=50, pitch_ceiling=400)
    f0 = pitch.selected_array["frequency"]
    ft0, fdt = pitch.x1, pitch.dx
    f0 = np.where(f0 > 0, f0, np.nan)

    thr = v.max() - rel_floor
    peaks = []            # (index, value)
    for i in range(1, len(v) - 1):
        if v[i] < thr:
            continue
        if not (v[i] >= v[i - 1] and v[i] >= v[i + 1]):
            continue
        if peaks:
            j = peaks[-1][0]
            if v[i] > v[j]:
                peaks[-1] = (i, v[i])
        else:
            peaks.append((i, v[i]))
            continue
        if i != peaks[-1][0]:
            peaks.append((i, v[i]))

    # 相邻峰之间必须存在 ≥ min_gap_db 的谷
    keep = [peaks[0]] if peaks else []
    for k in range(1, len(peaks)):
        a = keep[-1][0]
        b = peaks[k][0]
        if v[a:b + 1].min() < min(peaks[k][1], v[a]) - min_gap_db:
            keep.append(peaks[k])

    # 音节核的"有声"边界：强度跌破 thr 的位置（首尾不能用文件端点，否则把静音算进时长）
    voiced_lo, voiced_hi = 0, len(v) - 1
    while voiced_lo < len(v) and v[voiced_lo] < thr:
        voiced_lo += 1
    while voiced_hi > 0 and v[voiced_hi] < thr:
        voiced_hi -= 1

    out = []
    for k, (i, val) in enumerate(keep):
        tp = t0 + i * dt
        lo = voiced_lo if k == 0 else (keep[k - 1][0] + i) // 2
        hi = voiced_hi if k == len(keep) - 1 else (i + keep[k + 1][0]) // 2
        dur = max(0.0, (hi - lo) * dt)
        fi = int(round((tp - ft0) / fdt))
        w = f0[max(0, fi - 5):fi + 6]
        f0m = float(np.nanmedian(w)) if np.any(~np.isnan(w)) else 0.0
        out.append((round(tp, 3), round(float(val), 2), round(f0m, 1), round(dur, 3)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="G:/_setup/_pb/el")
    ap.add_argument("--out", default="G:/_setup/_pb/result.json")
    a = ap.parse_args()

    files = {}
    for f in glob.glob(os.path.join(a.dir, "*_trial_*.wav")):
        i = int(os.path.basename(f).split("_trial_")[1].split(".")[0])
        files[i] = f

    print("=== %s：%d 个文件 ===" % (a.dir, len(files)))
    print("%-14s %-6s %-3s %-30s %-6s %-6s %s" % ("text", "expect", "n", "nuclei(t,dB,F0,dur)", "前半", "后半", "判定"))
    ok_by, total_by = {}, {}
    rows = []
    for i in sorted(files):
        if i not in MAP:
            continue
        txt, expect = MAP[i]
        try:
            ns = find_nuclei(files[i])
        except Exception as e:
            print("  !! %s %s" % (txt, e))
            continue
        if len(ns) < 2:
            print("%-14s %-6s %-3d %-30s 音节核不足，跳过" % (txt, expect, len(ns)))
            continue

        # 单维度判据（不用 z-score：n=2 时 z 退化成固定 ±0.707，判定会被量纲最大的维度独占）
        ints = [x[1] for x in ns]
        durs = [x[3] for x in ns]
        f0s = [x[2] for x in ns]
        h = len(ns) // 2

        def side(vals):
            a = sum(vals[:h]) / h
            b = sum(vals[h:]) / max(1, len(vals) - h)
            if abs(a - b) < 1e-9:
                return "tie"
            return "head" if a > b else "tail"

        got = {
            "F0": side(f0s),
            "dur": side(durs),
            "int": side(ints),
        }
        # 半音化后的 F0 差 + 对数时长比，量纲可比
        import math
        d_f0 = 12 * math.log2(max(f0s[0], 1) / max(f0s[-1], 1))
        d_du = math.log2(max(durs[0], 1e-3) / max(durs[-1], 1e-3))
        d_in = ints[0] - ints[-1]
        got["F0+dur"] = "head" if (0.5 * d_f0 + 0.5 * d_du * 2) > 0 else "tail"
        got["prod"] = "head" if (d_f0 * d_du) > 0 else ("head" if d_f0 > 0 else "tail")

        marks = {k: ("OK" if v == expect else ("~~" if v == "tie" else "XX")) for k, v in got.items()}
        for k in got:
            if marks[k] == "OK":
                ok_by[k] = ok_by.get(k, 0) + 1
            elif marks[k] == "XX":
                ok_by[k] = ok_by.get(k, 0) + 0
            total_by[k] = total_by.get(k, 0) + (1 if marks[k] != "~~" else 0)

        print("%s%-12s %-5s %d  %s | F0=%s dur=%s int=%s"
              % ("    ", txt, expect, len(ns),
                 " ".join("%.0f/%.2f" % (x[2], x[3]) for x in ns[:3]),
                 marks["F0"], marks["dur"], marks["int"]))
        rows.append(dict(trial=i, text=txt, expect=expect, got=got, n=len(ns),
                         head=None, tail=None, nuclei=ns,
                         d_f0=round(d_f0, 2), d_dur=round(d_du, 2), d_int=round(d_in, 2)))

    n = len(rows)
    print("\n=== 逐维度命中率（n=%d）===" % n)
    for k in ("F0", "dur", "int", "F0+dur", "prod"):
        t = total_by.get(k, 0)
        o = ok_by.get(k, 0)
        if not t:
            continue
        print("  %-8s %2d/%2d = %.3f   二项p=%.3f" % (k, o, t, o / t, _binom(o, t)))
    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s" % a.out)


def _binom(k, n):
    import math
    if n == 0:
        return 1.0
    z = (abs(k - n / 2) - 0.5) / (0.5 * n ** 0.5)
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


if __name__ == "__main__":
    main()
