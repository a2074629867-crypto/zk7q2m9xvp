# -*- coding: utf-8 -*-
"""pause_by_punct.py —— 按「标点类型」给停顿，目标值取自马修真人全段统计。

与 pause_donor_by_position.py 的区别（那个是照搬一段 9 个间隙的序列）：
  · 目标时长按标点类型定，而不是按位置逐个搬
  · 只在标点处插停顿，模型自带的词内微停顿（<0.3s）**原样保留**
    ⇒ 避免「短-长-短-长」的抖动节奏

真人统计（母带 26.92min，能量 VAD，切片级可归类 378 个）：
  period  n=151  中位 1.03  p10 0.47  p90 1.60
  comma   n= 66  中位 0.58  p10 0.20  p90 0.90

用法:
  python pause_by_punct.py --gen c01.wav --text c01.txt --donor real.wav \
      --out c01_fix.wav --report c01.json [--scale 1.0] [--max-gap 2.0]
"""
import argparse
import json
import re

import numpy as np
import soundfile as sf

SR = 48000

# 真人实测目标值（秒）—— 来自 mc_pause_rules.py 对母带 26.63min / 641 间隙的统计：
#   逗号 n=136 中位 1.17 (p25 1.00 / p75 1.45)
#   句号 n=234 中位 1.76 (p25 1.38 / p75 1.98)
#   句中换气 <0.6s n=198 中位 0.11 —— 与模型自带的 0.09 几乎一致，**不动**
#   段落边界 >=2.3s n=26 中位 2.50
# 旧版把所有标点统一成 1.48（长停混合中位），会把逗号拖长、句号压短。
MC_RULES = "G:/_setup/mc_pause_rules.json"

_FALLBACK = {".": 1.76, "?": 1.76, "!": 1.76, ",": 1.17,
             ";": 1.28, ":": 1.28, "—": 1.17, "…": 1.17}


def punct_target():
    out = dict(_FALLBACK)
    try:
        d = json.load(open(MC_RULES, encoding="utf-8"))
        p = d.get("punct", {})
        for sym, key in ((".", "period"), ("?", "question"), ("!", "exclam"),
                         (",", "comma"), (";", "semicolon"), (":", "colon")):
            st = p.get(key, {}).get("stats")
            if st:
                out[sym] = float(st["median"])
    except Exception:
        pass
    return out


PUNCT_TARGET = punct_target()


def load(p):
    x, sr = sf.read(p, dtype="float64", always_2d=True)
    x = x.mean(1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = np.gcd(int(sr), SR)
        x = resample_poly(x, SR // g, sr // g)
    return x


def mc_quantiles(donor, nq=201, thr_db=-35.0):
    """从真人母带直接算间隙分位表（不经过切片，避免 max_sil_kept 削顶）。

    返回 np.array，长度 nq，第 i 项 = 真人间隙分布的第 i/(nq-1) 分位。
    """
    d = load(donor)
    hop = int(SR * 0.010)
    n = len(d) // hop
    db = 20 * np.log10(np.sqrt((d[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() + thr_db)
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
    segs, i = [], 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]:
                j += 1
            segs.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    gs = [segs[k][0] - segs[k - 1][1] for k in range(1, len(segs))]
    gs = np.array([g for g in gs if g > 0.02])
    qs = np.percentile(gs, np.linspace(0, 100, nq))
    print("真人间隙 %d 个：平均 %.2f 中位 %.2f p90 %.2f p98 %.2f max %.2f" % (
        len(gs), gs.mean(), np.median(gs), np.percentile(gs, 90),
        np.percentile(gs, 98), gs.max()))
    return qs


def speech_mask(x):
    hop = int(SR * 0.010)
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() - 35.0)
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


def gaps(x):
    m = speech_mask(x)
    n, out = len(m), []
    i, first = 0, True
    while i < n:
        if not m[i]:
            j = i
            while j < n and not m[j]:
                j += 1
            if not first and j < n:
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


def punct_marks(text):
    """返回 [(词序号, 标点)]，词序号 = 该标点之前已出现的词数。"""
    out = []
    wc = 0
    buf = ""
    for ch in text:
        if ch.isspace():
            if buf:
                wc += 1
                buf = ""
        elif ch in PUNCT_TARGET:
            # ★ 标点前的词必须先计入，否则带标点的词全丢（130 → 117 的 bug）
            if buf:
                wc += 1
                buf = ""
            # 连续标点（如 ."）只记一次
            if not out or out[-1][0] != wc:
                out.append((wc, ch))
        else:
            buf += ch
    if buf:
        wc += 1
    return out, max(1, wc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True)
    ap.add_argument("--text", required=True, help="该块对应的文本（用来定位标点）")
    ap.add_argument("--donor", required=True, help="真人音频（取静音素材）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default="")
    ap.add_argument("--scale", type=float, default=1.0, help="目标停顿整体倍率")
    ap.add_argument("--max-gap", type=float, default=2.0, help="目标上限（秒）")
    ap.add_argument("--min-touch", type=float, default=None,
                    help="生成侧间隙 < 该值时不参与（默认 0 = 全部参与）")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--mode", choices=["punct", "quantile"], default="punct",
                    help="punct=按标点类型给固定目标；quantile=按真人分位表匹配（形状更像）")
    ap.add_argument("--gamma", type=float, default=1.0,
                    help="quantile 模式的 rank 曲率：>1 让短停顿保持更短、长停顿更长")
    a = ap.parse_args()

    text = open(a.text, encoding="utf-8").read().strip()
    marks, nwords = punct_marks(text)
    if a.min_touch is None:
        a.min_touch = 0.0
    g = load(a.gen)
    d = load(a.donor)
    gg = gaps(g)
    dg = gaps(d)
    dur = len(g) / SR

    print("文本 %d 词，标点 %d 个（句 %d / 逗 %d / 其他 %d）" % (
        nwords, len(marks),
        sum(1 for _, p in marks if p in ".?!"),
        sum(1 for _, p in marks if p == ","),
        sum(1 for _, p in marks if p not in ".?!,")))
    print("目标停顿 = %.2fs（真人标点类中位）" % list(PUNCT_TARGET.values())[0])
    print("生成音频 %.2fs，间隙 %d 个" % (dur, len(gg)))

    # 只保留够长的间隙作为「候选锚点」
    cand = [(k, s, e) for k, (s, e) in enumerate(gg) if (e - s) >= a.min_touch]
    if not cand:
        raise SystemExit("没有可用间隙")
    print("候选间隙（>=%.2fs）%d 个" % (a.min_touch, len(cand)))

    # 标点 → 词进度 → 音频时间（线性近似，块内语速相对均匀）
    plan = []
    used = set()
    if a.mode == "quantile":
        # ★ 分位映射：我们第 rank 长的间隙 → 真人第 rank 分位的时长
        #   好处：直接复现真人「双峰」形状（27% 微停顿 + 57% 长停顿）
        qs = mc_quantiles(a.donor)
        order = sorted(range(len(cand)), key=lambda i: cand[i][2] - cand[i][1])
        N = len(cand)
        for rank, oi in enumerate(order):
            k, s, e = cand[oi]
            r = (rank / max(1, N - 1)) ** a.gamma
            idx = int(round((0.02 + 0.96 * r) * (len(qs) - 1)))
            want = min(qs[idx] * a.scale, a.max_gap)
            plan.append(dict(k=k + 1, at=round(s, 2), punct="q%.2f" % r, rank=round(r, 3),
                             cur=round(e - s, 2), target=round(want, 2),
                             t_est=round(0.5 * (s + e), 2), err=0.0))
    else:
        for wi, p in marks:
            t_est = (wi / nwords) * dur
            # 找时间上最近的未用候选间隙
            best, bestd = None, 1e9
            for k, s, e in cand:
                if k in used:
                    continue
                c = 0.5 * (s + e)
                dd = abs(c - t_est)
                if dd < bestd:
                    best, bestd = (k, s, e), dd
            if best is None:
                break
            used.add(best[0])
            want = min(PUNCT_TARGET[p] * a.scale, a.max_gap)
            plan.append(dict(k=best[0] + 1, at=round(best[1], 2), punct=p,
                             cur=round(best[2] - best[1], 2), target=round(want, 2),
                             t_est=round(t_est, 2), err=round(bestd, 2)))

    # 按目标调整：长于目标就裁，短于目标就补（模型自己的停顿和标点不对应，必须双向）
    edits, rows = [], []
    for it in sorted(plan, key=lambda x: x["at"]):
        delta = it["target"] - it["cur"]
        if abs(delta) <= 0.03:
            it["added"] = 0.0
            rows.append(it)
            continue

        s0 = int(it["at"] * SR)
        s1 = int((it["at"] + it["cur"]) * SR)

        if delta < 0:
            # 缩短：在静音段内居中裁，两端各留 0.06s 防切到语音
            cutn = int((-delta) * SR)
            guard = int(0.06 * SR)
            inner = (s1 - s0) - 2 * guard
            cutn = min(cutn, max(0, inner))
            if cutn <= 0:
                it["added"] = 0.0
                rows.append(it)
                continue
            c0 = s0 + guard + (inner - cutn) // 2
            edits.append((c0, c0 + cutn, np.zeros(0)))
            it["added"] = -round(cutn / SR, 2)
            rows.append(it)
            continue

        # 加长：从真人静音里按需取，优先挑时长接近的间隙，居中截取
        need = delta
        pool = sorted(dg, key=lambda se: abs((se[1] - se[0]) - need))
        seg = np.zeros(0)
        for ds, de in pool:
            avail = de - ds
            take = min(need - len(seg) / SR, avail)
            if take <= 0.01:
                continue
            cs = ds + max(0.0, (avail - take) / 2.0)
            seg = np.concatenate([seg, d[int(cs * SR): int((cs + take) * SR)]])
            if len(seg) >= need * SR - 1:
                break
        if len(seg) < need * SR:
            seg = np.concatenate([seg, np.zeros(int(need * SR) - len(seg))])
        seg = fade(seg[: int(need * SR)], int(0.008 * SR))
        edits.append((s1, s1, seg))
        it["added"] = round(delta, 2)
        rows.append(it)

    out = g.copy()
    for s0, s1, seg in sorted(edits, key=lambda x: -x[0]):
        s0 = int(np.clip(s0, 0, len(out)))
        s1 = int(np.clip(s1, s0, len(out)))
        out = np.concatenate([out[:s0], seg, out[s1:]])

    sf.write(a.out, out.astype(np.float32), SR, subtype="PCM_16")
    tot = sum(r["added"] for r in rows)
    n_add = sum(1 for r in rows if r["added"] > 0)
    n_cut = sum(1 for r in rows if r["added"] < 0)
    print("\n调整 %d 处（加长 %d / 缩短 %d），净 %+.2fs → 输出 %.2fs（%+.1f%%）" % (
        n_add + n_cut, n_add, n_cut, tot, len(out) / SR, (len(out) / SR / dur - 1) * 100))
    if a.verbose:
        for r in rows:
            print("  #%-3d @%6.2fs %-5s 现 %.2f → 目标 %.2f  %s" % (
                r["k"], r["at"], r["punct"], r["cur"], r["target"],
                ("%+.2f" % r["added"]) if r["added"] else "不动"))
    if a.verbose:
        fin = np.array([r["target"] for r in rows])
        print("  最终间隙分布: n=%d 平均 %.2f 中位 %.2f p10 %.2f p90 %.2f max %.2f" % (
            len(fin), fin.mean(), np.median(fin), np.percentile(fin, 10),
            np.percentile(fin, 90), fin.max()))
    if a.report:
        json.dump(dict(gen=a.gen, text=a.text, out=a.out, dur_in=round(dur, 2),
                       dur_out=round(len(out) / SR, 2), added_total=round(tot, 2),
                       n_marks=len(marks), n_gaps=len(gg), rows=rows),
                  open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
