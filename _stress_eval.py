# -*- coding: utf-8 -*-
"""重音注入效果评估：逐词时长 / F0 / 能量，对比 base 与 <rate> 标注版。

用法：先跑 _asr_words.py 生成 _words.json，再跑本脚本。
"""
import json
import os
import sys
import wave

import numpy as np
import parselmouth

D = "G:/_setup/_stress_test"
PAIRS = [
    ("n0194_base", "n0194_r06", "slowly"),
    ("n0194_base", "n0194_r04", "slowly"),
    ("n0112_base", "n0112_r06", "deliberately"),
    ("n0112_base", "n0112_r04", "deliberately"),
    ("n0167_base", "n0167_r06", "coldly"),
]


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def word_feats(a, sr, s, e):
    i0, i1 = max(0, int(s * sr)), min(len(a), int(e * sr))
    seg = a[i0:i1]
    if len(seg) < int(0.04 * sr):
        return None
    dur = len(seg) / sr
    hop = max(1, int(0.01 * sr))
    k = len(seg) // hop
    if k < 2:
        return None
    env = np.sqrt(np.mean(seg[:k * hop].reshape(k, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(env + 1e-12)
    e_peak = float(np.percentile(db, 90))
    snd = parselmouth.Sound(seg, sampling_frequency=sr)
    pit = snd.to_pitch(time_step=0.01, pitch_floor=60.0, pitch_ceiling=400.0)
    v = pit.selected_array["frequency"]
    v = v[v > 0]
    f0 = float(np.median(v)) if len(v) else 0.0
    return dict(dur=dur, f0=f0, e=e_peak)


def zscores(vals):
    v = np.array([x for x in vals if x], dtype=float)
    if len(v) < 2:
        return np.zeros(len(vals))
    med = np.median(v)
    mad = np.median(np.abs(v - med)) + 1e-9
    return np.array([(x - med) / (1.4826 * mad) if x else 0.0 for x in vals])


def analyze(tag, words_map):
    p = os.path.join(D, tag + ".wav")
    if not os.path.exists(p):
        return None
    w = words_map.get(tag + ".wav")
    if not w:
        return None
    a, sr = rd(p)
    rows = []
    for item in w["words"]:
        f = word_feats(a, sr, item["start"], item["end"])
        if not f:
            continue
        rows.append(dict(w=item["w"], **f))
    if len(rows) < 3:
        return None
    dz = zscores([r["dur"] for r in rows])
    fz = zscores([12 * np.log2(r["f0"] / 100.0) if r["f0"] else 0 for r in rows])
    ez = zscores([r["e"] for r in rows])
    for i, r in enumerate(rows):
        r["prom"] = 0.5 * dz[i] + 0.3 * fz[i] + 0.2 * ez[i]
    order = sorted(range(len(rows)), key=lambda i: -rows[i]["prom"])
    for rank, i in enumerate(order, 1):
        rows[i]["rank"] = rank
    return rows


def main():
    wm = json.load(open("G:/_setup/_words.json", encoding="utf-8"))
    for base_tag, tag_tag, target in PAIRS:
        b = analyze(base_tag, wm)
        t = analyze(tag_tag, wm)
        if not b or not t:
            print("%s / %s  —— 缺数据" % (base_tag, tag_tag))
            continue
        bm = {r["w"].lower().strip(".,;:"): r for r in b}
        tm = {r["w"].lower().strip(".,;:"): r for r in t}
        print("=" * 76)
        print("%s  →  %s   目标词: %s" % (base_tag, tag_tag, target))
        print("%-16s %7s %7s %7s %8s %8s %6s %6s" %
              ("词", "base时长", "标注时长", "变化", "base F0", "标注 F0", "名次", "→"))
        bt = bm.get(target)
        tt = tm.get(target)
        others = []
        for k, rb in bm.items():
            rt = tm.get(k)
            if not rt:
                continue
            if not any(c.isalpha() for c in k):
                continue                      # 跳过纯标点，避免逗号时长污染统计
            chg = rt["dur"] / rb["dur"] - 1 if rb["dur"] else 0
            if k != target:
                others.append(chg)
            mark = " ◀目标" if k == target else ""
            print("%-16s %6.3fs %6.3fs %+6.1f%% %7.1fHz %7.1fHz %4d→%-2d%s" %
                  (k, rb["dur"], rt["dur"], 100 * chg, rb["f0"], rt["f0"],
                   rb["rank"], rt["rank"], mark))
        if bt and tt:
            print()
            print("目标词 %-13s 时长 %+.1f%%  突出度名次 %d/%d → %d/%d  突出度 %.2f → %.2f"
                  % (target, 100 * (tt["dur"] / bt["dur"] - 1),
                     bt["rank"], len(b), tt["rank"], len(t), bt["prom"], tt["prom"]))
            if others:
                print("非目标词时长平均变化 %+.1f%%（绝对值最大 %.1f%%）"
                      % (100 * np.mean(others), 100 * max(abs(x) for x in others)))
        print()


if __name__ == "__main__":
    main()
