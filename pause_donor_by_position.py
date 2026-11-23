# -*- coding: utf-8 -*-
"""pause_donor_by_position.py —— 按「位置」把真人停顿序列移植到生成音频上。

不依赖词级时间戳，直接对能量 VAD 检出的间隙做替换：
  · 生成音频的第 k 个间隙  ←  真人音频的第 k 个间隙（时长 + 素材）
  · 只增不减（裁短有切词风险），差值部分用真人对应间隙的片段补齐
  · 插入的是真人真实静音（带底噪），不是数字零 ⇒ 不需要再铺 room tone

用法:
  python pause_donor_by_position.py --gen A.wav --donor real.wav --out D.wav \
      --report D.json [--scale 1.0]
"""
import argparse
import json

import numpy as np
import soundfile as sf

SR = 48000


def load(p):
    x, sr = sf.read(p, dtype="float64", always_2d=True)
    x = x.mean(1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = np.gcd(int(sr), SR)
        x = resample_poly(x, SR // g, sr // g)
    return x


def speech_mask(x):
    hop = int(SR * 0.010)
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() - 35.0)

    # 填 <80ms 的洞、去 <120ms 的孤岛
    i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]:
                j += 1
            if i > 0 and j < len(m) and (j - i) < 8:
                m[i:j] = True
            i = j
        else:
            i += 1
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) < 12:
                m[i:j] = False
            i = j
        else:
            i += 1
    return m


def gaps(x, min_gap=0.0):
    """返回 [(start_s, end_s)] 的内部间隙（不含首尾静音）。

    min_gap: 小于该值的间隙视为词内微停顿，不参与位置映射（但仍会保留在音频里）。
    """
    m = speech_mask(x)
    n = len(m)
    out = []
    i = 0
    first = True
    while i < n:
        if not m[i]:
            j = i
            while j < n and not m[j]:
                j += 1
            if not first and j < n and (j - i) * 0.01 >= min_gap:
                out.append((i * 0.01, j * 0.01))
            i = j
        else:
            first = False
            i += 1
    return out


def fade(x, nf):
    y = x.copy()
    if len(y) > nf:
        y[:nf] *= np.linspace(0.0, 1.0, nf)
        y[-nf:] *= np.linspace(1.0, 0.0, nf)
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True)
    ap.add_argument("--donor", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default="")
    ap.add_argument("--scale", type=float, default=1.0, help="目标停顿整体倍率")
    ap.add_argument("--min-gap", type=float, default=0.0,
                    help="生成侧小于该值的间隙不参与映射（默认 0）")
    ap.add_argument("--donor-min-gap", type=float, default=0.0,
                    help="真人侧小于该值的间隙不参与映射（默认 0）")
    ap.add_argument("--gap-min", type=float, default=None,
                    help="目标间隙下限（秒），默认不夹")
    ap.add_argument("--gap-max", type=float, default=None,
                    help="目标间隙上限（秒），默认不夹；常用 2.0")
    a = ap.parse_args()

    g = load(a.gen)
    d = load(a.donor)
    gg = gaps(g, a.min_gap)
    dg = gaps(d, a.donor_min_gap)
    print("生成音频 %.2fs，间隙 %d 个" % (len(g) / SR, len(gg)))
    print("真人音频 %.2fs，间隙 %d 个" % (len(d) / SR, len(dg)))
    print("真人间隙序列: %s" % " ".join("%.2f" % (b - a_) for a_, b in dg))

    if not gg or not dg:
        raise SystemExit("间隙检测失败")

    # 位置映射：k -> k（数量不等时按比例取，保证单调）
    def donor_idx(k):
        if len(dg) == len(gg):
            return k
        return int(round(k * (len(dg) - 1) / max(1, len(gg) - 1)))

    edits = []   # (cut_sample, insert_samples, donor_seg)
    rows = []
    for k, (s, e) in enumerate(gg):
        cur = e - s
        di = donor_idx(k)
        ds, de = dg[di]
        want = (de - ds) * a.scale
        # 夹紧到 [gap_min, gap_max]：真人某些间隙会偏长/偏短，不夹会听出突兀
        if a.gap_min is not None:
            want = max(want, a.gap_min)
        if a.gap_max is not None:
            want = min(want, a.gap_max)
        delta = want - cur
        if delta <= 0.02:
            rows.append(dict(k=k + 1, at=round(s, 2), cur=round(cur, 2),
                             target=round(want, 2), added=0.0, donor_idx=di + 1))
            continue
        # 从真人该间隙里取 delta 秒（居中，避开首尾可能的残留语音）
        avail = de - ds
        take = min(delta, avail)
        cs = ds + max(0.0, (avail - take) / 2.0)
        seg = d[int(cs * SR): int((cs + take) * SR)].copy()
        # 若真人间隙比需要的短，循环补齐
        if len(seg) < int(delta * SR):
            reps = int(np.ceil(delta * SR / max(1, len(seg))))
            seg = np.tile(seg, reps)
        seg = seg[: int(delta * SR)]
        seg = fade(seg, int(0.008 * SR))
        edits.append((int(s * SR), seg))
        rows.append(dict(k=k + 1, at=round(s, 2), cur=round(cur, 2),
                         target=round(want, 2), added=round(delta, 2), donor_idx=di + 1))

    out = g.copy()
    for cut, seg in sorted(edits, key=lambda p: -p[0]):
        cut = int(np.clip(cut, 1, len(out) - 1))
        out = np.concatenate([out[:cut], seg, out[cut:]])

    sf.write(a.out, out.astype(np.float32), SR, subtype="PCM_16")
    tot_add = sum(r["added"] for r in rows)
    print("\n插入 %d 处，共 +%.2fs → 输出 %.2fs" % (
        len(edits), tot_add, len(out) / SR))
    for r in rows:
        print("  #%d @%5.2fs  现 %.2fs → 目标 %.2fs  %s" % (
            r["k"], r["at"], r["cur"], r["target"],
            ("+%.2fs（用真人第 %d 个间隙）" % (r["added"], r["donor_idx"])) if r["added"] else "不动"))
    if a.report:
        json.dump(dict(gen=a.gen, donor=a.donor, out=a.out, rows=rows,
                       added_total=round(tot_add, 2),
                       dur_in=round(len(g) / SR, 2), dur_out=round(len(out) / SR, 2)),
                  open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
