# -*- coding: utf-8 -*-
"""位置基线：CWT 的 prominence 有多少是「词在句中的位置」造成的？

    python _pos_baseline.py

动机：句首虚词被测成最重，到底是它真被强调，还是 F0 重置的测量偏差？
光看 pos<=1 无法区分 —— 因为英语句首本来也常带重音。

做法：把全库所有词按「相对位置」分箱，算每个箱的 prominence 中位，
得到位置基线曲线；然后算每个词的残差 = prom − baseline[bin]。
残差高 = 比同位置的其他词更突出 = 真重音；残差 ≈ 0 = 只是位置效应。

不用绝对位置（pos），因为长句短句混在一起会把曲线拉平。
"""
import glob
import os
import statistics
from collections import defaultdict

PROM_DIR = "G:/_setup/_wpt_out"
PUNCT = set(".,;:!?-\"'()[]—–")
NBIN = 10


def load(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        if len(f) < 6:
            continue
        try:
            rows.append((f[3], float(f[4])))
        except ValueError:
            continue
    return [(w, p) for w, p in rows if w and w not in PUNCT]


def main():
    files = sorted(glob.glob(os.path.join(PROM_DIR, "*.prom")))
    sents = []
    for f in files:
        s = load(f)
        if len(s) >= 4:
            sents.append(s)

    print("句子 %d 条，词 %d 个" % (len(sents), sum(len(s) for s in sents)))

    bins = defaultdict(list)
    for s in sents:
        n = len(s)
        for i, (_w, p) in enumerate(s):
            b = min(NBIN - 1, int(round(i / max(1, n - 1) * (NBIN - 1))))
            bins[b].append(p)

    base = {}
    print("\n=== 位置基线（相对位置 → prominence 中位）===")
    for b in range(NBIN):
        v = sorted(bins[b])
        med = statistics.median(v)
        base[b] = med
        bar = "█" * int(round(med * 8))
        print("  位置 %.2f  n=%5d  中位 %.3f  p90 %.3f  %s"
              % (b / (NBIN - 1), len(v), med, v[int(0.9 * (len(v) - 1))], bar))

    # 每个词的残差
    resid_all = []
    resid_by_pos = defaultdict(list)
    top1_resid = []
    top1_by_kind_pos = defaultdict(list)
    for s in sents:
        n = len(s)
        if n < 4:
            continue
        rs = []
        for i, (_w, p) in enumerate(s):
            b = min(NBIN - 1, int(round(i / max(1, n - 1) * (NBIN - 1))))
            r = p - base[b]
            rs.append(r)
            resid_by_pos[b].append(r)
            resid_all.append(r)
        ti = max(range(n), key=lambda i: s[i][1])
        top1_resid.append(rs[ti])
        b = min(NBIN - 1, int(round(ti / max(1, n - 1) * (NBIN - 1))))
        top1_by_kind_pos[("head" if ti <= 1 else "mid")].append(rs[ti])

    print("\n=== 残差（句内去位置效应后）===")
    rr = sorted(resid_all)
    print("  全部词   中位 %+.3f  p90 %+.3f  p99 %+.3f  最大 %+.3f"
          % (statistics.median(rr), rr[int(.9 * (len(rr) - 1))],
             rr[int(.99 * (len(rr) - 1))], rr[-1]))
    tt = sorted(top1_resid)
    print("  top1 词  中位 %+.3f  p10 %+.3f  p90 %+.3f"
          % (statistics.median(tt), tt[int(.1 * (len(tt) - 1))], tt[int(.9 * (len(tt) - 1))]))
    for k, v in sorted(top1_by_kind_pos.items()):
        v = sorted(v)
        print("  top1 %-5s n=%4d  残差中位 %+.3f  p10 %+.3f"
              % (k, len(v), statistics.median(v), v[int(.1 * (len(v) - 1))]))

    print("\n=== top1 残差分档（残差低 ⇒ 只是位置效应）===")
    for lo, hi, lab in [(-99, 0.05, "≤0.05 位置效应"), (0.05, 0.2, "0.05-0.2 弱"),
                        (0.2, 0.5, "0.2-0.5 中"), (0.5, 99, ">0.5 强")]:
        k = sum(1 for r in top1_resid if lo < r <= hi)
        print("  %-18s %4d  %5.1f%%" % (lab, k, 100.0 * k / len(top1_resid)))

    print("\n=== 句首 3 词的残差（验证 F0 重置假设）===")
    for pos in range(min(NBIN, 4)):
        v = sorted(resid_by_pos[pos])
        if not v:
            continue
        print("  pos=%d  n=%4d  残差中位 %+.3f  p75 %+.3f"
              % (pos, len(v), statistics.median(v), v[int(.75 * (len(v) - 1))]))


if __name__ == "__main__":
    main()
