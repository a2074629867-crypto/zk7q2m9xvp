# -*- coding: utf-8 -*-
"""_adv_vdur.py —— 用「有声帧时长」替代 ASR 边界差，重新审 55 条。

为什么换：
    `sps = (t1 - t0) / nsyl` 用的是 ASR 词边界差。ASR 边界在词尾会把**静音/呼吸**
    一起圈进去，于是词时长被静音固定住 —— 改前改后都是 0.64 / 0.96，看不出变化。
    实测 N0219 r7：ASR 边界 1.04 不变，但**有声帧时长 0.310 → 0.445（+37%）**。

新量：
    vdur   词区间内**连续有声帧**的总长（间隔 <40ms 才算连续，剔掉孤立噪声）
    vx     该词 vdur ÷ 同句其它实词 vdur 的中位   （配对对照，自带句子归一）
    vdur_z log(vdur) 相对「同音节数应有值」的 σ 偏离

判据不是绝对阈值 —— 分位数那条路已经证明会造出 56% 不合格。
这里只看 **vx 是否 > 1**（这个词是否比同句其它词占更多发声时间），
以及 vdur 相对原版是变长还是变短（改动前后的直接对照）。
"""
import json
import math
import os
import statistics as S
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
import _adv_align as A
import _f0_accent as F
import _adv_prom as P

ROOT = "G:/_setup"
STATE = os.path.join(ROOT, "_mt_adv_state.json")


def vdur(ts, t0, t1):
    """词内有声时长：只累计连续段（相邻帧间隔 <40ms）。"""
    sel = (ts >= t0) & (ts < t1)
    tt = ts[sel]
    if len(tt) == 0:
        return 0.0, 0.0
    gap = np.diff(tt)
    total = float(len(tt)) * 0.005
    # 最长连续段
    best = cur = 1
    for g in gap:
        if g < 0.04:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return total, float(best) * 0.005


def measure(wav, prom, text):
    ts, fs, ss, dur = F.track_ex(wav)
    rows = F.read_prom(prom)
    spans = A.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    tw = A.text_words(text)
    out = []
    for i, x in enumerate(tw):
        if not x["is_word"] or x["key"] in F.FUNC:
            continue
        sp = spans[i]
        if sp["t0"] is None:
            continue
        tot, longest = vdur(ts, sp["t0"], sp["t1"])
        if tot <= 0:
            continue
        out.append(dict(key=x["key"], w=x["w"],
                        nsyl=max(1, P.AC.syllables(x["w"])),
                        t0=sp["t0"], t1=sp["t1"],
                        vdur=round(tot, 3), longest=round(longest, 3),
                        span=round(sp["t1"] - sp["t0"], 2)))
    return out


def fit_base(allc):
    pts = [(w["nsyl"], w["vdur"]) for w in allc if w["vdur"] > 0]
    if len(pts) < 50:
        return None
    x = np.log([p[0] for p in pts])
    y = np.log([p[1] for p in pts])
    b, a = np.polyfit(x, y, 1)
    r = y - (a + b * x)
    mad = float(np.median(np.abs(r - np.median(r))))
    return dict(a=float(a), b=float(b), sd=max(1.4826 * mad, 0.08), n=len(pts),
                r=float(np.corrcoef(x, y)[0, 1]))


def main():
    st = json.load(open(STATE, encoding="utf-8"))["units"]
    raws = []
    for u, x in sorted(st.items()):
        prom = os.path.join(ROOT, "_wpt_out", "_mt_pick__%s.prom" % u)
        wav = os.path.join(ROOT, "_mt_pick", u + ".wav")
        if not (os.path.exists(prom) and os.path.exists(wav)):
            continue
        cws = measure(wav, prom, x["text"])
        if cws:
            raws.append((u, x, cws))
    allc = [w for _u, _x, cws in raws for w in cws]
    base = fit_base(allc)
    print("基线 log(vdur) = %.3f + %.3f*log(nsyl)   r=%.3f  sd=%.3f  n=%d"
          % (base["a"], base["b"], base["r"], base["sd"], base["n"]))

    rows = []
    for u, x, cws in raws:
        adv = x["adv"].lower()
        hit = [c for c in cws if c["key"] == adv]
        if not hit:
            rows.append(dict(uid=u, adv=x["adv"], note="未测到"))
            continue
        c = hit[-1]
        others = [cc for cc in cws if cc is not c]
        med = S.median([cc["vdur"] for cc in others]) if others else None
        pred = base["a"] + base["b"] * math.log(max(1, c["nsyl"]))
        rows.append(dict(
            uid=u, adv=x["adv"], nsyl=c["nsyl"],
            vdur=c["vdur"], longest=c["longest"], span=c["span"],
            vx=round(c["vdur"] / med, 2) if med else None,
            vdur_z=round((math.log(c["vdur"]) - pred) / base["sd"], 2),
            human=x.get("judge_by") or ""))

    # 母检验：副词 vs 同句其它词
    vx = [r["vx"] for r in rows if r.get("vx")]
    print("\n=== 配对对照（副词 ÷ 同句其它实词中位）===")
    print("  n=%d  中位 %.2f  均值 %.2f  >1 的 %d/%d"
          % (len(vx), S.median(vx), sum(vx) / len(vx),
             sum(1 for v in vx if v > 1), len(vx)))
    # 符号检验
    k, n = sum(1 for v in vx if v > 1), len(vx)
    p = sum(math.comb(n, i) for i in range(k, n + 1)) / 2.0 ** n
    print("  单侧二项 p=%.4f" % p)

    print("\n%-8s %-14s %-6s %-7s %-7s %-7s %s"
          % ("uid", "adv", "音节", "vdur", "vx", "vdur_z", "人耳"))
    for r in sorted(rows, key=lambda z: z.get("vx") or -9):
        if "vdur" not in r:
            continue
        print("%-8s %-14s %-6d %-7.3f %-7.2f %+7.2f %s"
              % (r["uid"], r["adv"][:14], r["nsyl"], r["vdur"], r["vx"],
                 r["vdur_z"], r["human"]))

    json.dump(dict(baseline=base, rows=rows),
              open(os.path.join(ROOT, "_adv_vdur.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出 _adv_vdur.json")


if __name__ == "__main__":
    main()
