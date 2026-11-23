# -*- coding: utf-8 -*-
"""mt_focus_eval.py —— 文本层判定的「焦点词」在音频上真的更突出吗？

设计要点（避免第 N 次同型错误）：
  1. **局部突出度**，不是句内最高。焦点是局部现象：一个词只要比前后邻居高就算突出。
     整句最高往往由短语拱形决定，与词义无关。
     rel_local(i) = st(word_i) - median(st(前后各 2 个词))
  2. **配对零分布**：同一句里，把「焦点词」的 rel 减去「该句所有词 rel 的均值」，
     得到句内相对量。若判据无效，这个量的分布应以 0 为中心。
     同时对每个词算 rank 分位（0.5 = 随机）。
  3. **时长轴**另算：重读词通常更长。z 分数相对句内全部词。
  4. 两个标注者分别算，看是否一致。若两方都无效，判据作废。
"""
import argparse
import json
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
from mt_matt_word_f0 import load_wav, f0_series  # noqa: E402

MIN_FRAMES = 3


def word_st(t, f, words, t0, t1):
    """每个词的中位 F0（半音，相对句内中位）。"""
    med = float(np.median(f))
    st = 12.0 * np.log2(f / med)
    out = []
    for a, b, w in words:
        a2, b2 = max(a, t0), min(b, t1)
        if b2 <= a2:
            out.append(None)
            continue
        m = (t >= a2) & (t < b2)
        if m.sum() < MIN_FRAMES:          # 太短就向外扩 40ms 再试
            m = (t >= a2 - 0.04) & (t < b2 + 0.04)
        if m.sum() < MIN_FRAMES:
            out.append(None)
            continue
        out.append(dict(w=w, st=float(np.median(st[m])), dur=float(b2 - a2)))
    return out


def rel_local(ws, k=2):
    out = []
    for i, x in enumerate(ws):
        if x is None:
            out.append(None)
            continue
        nb = [ws[j]["st"] for j in range(max(0, i - k), min(len(ws), i + k + 1))
              if j != i and ws[j] is not None]
        out.append(x["st"] - float(np.median(nb)) if len(nb) >= 2 else None)
    return out


def dur_z(ws):
    d = [x["dur"] for x in ws if x]
    if len(d) < 4:
        return [None] * len(ws)
    mu, sd = float(np.mean(d)), float(np.std(d))
    if sd < 1e-6:
        return [None] * len(ws)
    return [((x["dur"] - mu) / sd if x else None) for x in ws]


def run(samples, labels, audio, tag):
    x, sr = load_wav(audio)
    T, F = f0_series(x, sr)
    rows = []
    for s in samples:
        k = s["key"]
        lab = labels.get(k)
        if not lab or "times" not in s:
            continue
        focus = lab["focus"] if isinstance(lab, dict) else lab
        words = [(a, b, w) for (a, b), w in zip(s["times"], s["words"])]
        t0, t1 = words[0][0], words[-1][1]
        ws = word_st(T, F, words, t0, t1)
        rl = rel_local(ws)
        dz = dur_z(ws)
        idx = [i for i, w in enumerate(s["words"]) if w == focus]
        if not idx:
            continue
        i = idx[0]
        if rl[i] is None:
            continue
        vals = [v for v in rl if v is not None]
        if len(vals) < 3:
            continue
        mean_all = float(np.mean(vals))
        rank = float(np.mean([v < rl[i] for v in vals]))
        rows.append(dict(key=k, focus=focus, rel=rl[i], rel_centered=rl[i] - mean_all,
                         rank=rank, durz=dz[i] if dz[i] is not None else 0.0,
                         n_word=len(vals), text=" ".join(s["words"])))
    if not rows:
        print("[%s] 无有效样本" % tag)
        return rows
    rel = np.array([r["rel"] for r in rows])
    cen = np.array([r["rel_centered"] for r in rows])
    rk = np.array([r["rank"] for r in rows])
    dz = np.array([r["durz"] for r in rows])
    print("\n[%s] n=%d" % (tag, len(rows)))
    print("  焦点词 rel_local   中位 %+.2f 半音   均值 %+.2f   >0 占比 %.0f%%" % (
        np.median(rel), rel.mean(), 100 * (rel > 0).mean()))
    print("  句内去均值后      中位 %+.2f 半音   均值 %+.2f   >0 占比 %.0f%%" % (
        np.median(cen), cen.mean(), 100 * (cen > 0).mean()))
    print("  句内 rank 分位    中位 %.2f  （0.50 = 随机，1.00 = 句内最高）" % np.median(rk))
    print("  时长 z            中位 %+.2f  （0 = 随机）" % np.median(dz))
    # 单样本 t（双尾）
    for name, v in [("rel_centered", cen), ("rank-0.5", rk - 0.5), ("dur_z", dz)]:
        n = len(v)
        se = float(np.std(v, ddof=1) / np.sqrt(n)) if n > 2 else 0.0
        t = float(np.mean(v) / se) if se > 1e-9 else 0.0
        print("  t(%s) = %.2f  (n=%d, 均值 %+.3f, SE %.3f)" % (name, t, n, np.mean(v), se))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default="G:/_setup/_matt_focus_samples.json")
    ap.add_argument("--audio", default="G:/GPT-SoVITS/_dataset/wonder_train.wav")
    ap.add_argument("--labels", nargs="+", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    samples = json.load(open(a.samples, encoding="utf-8"))
    allrows = {}
    for p in a.labels:
        tag = p.split("_")[-1].replace(".json", "")
        lab = json.load(open(p, encoding="utf-8"))
        allrows[tag] = run(samples, lab, a.audio, tag)
    if a.out:
        json.dump(allrows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
