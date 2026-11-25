"""语调轮廓分析：把「语调好不好」量化

用户口径：
  「c2_0368 的 seed44（think 400ms）的 free 念得更好，就是语调更好」
  「c2_0279 的 42 somebody's house 的语调发音不如 seed43，因为在这里
    somebody's 不用突然发亮，所以 seed43 的语调好一点」
  「我说的语调，就是你的这些曲线是更符合的」

「突然发亮」= 该词 F0 相对句基线的**正向偏移过大**。所以量化成：

    词级 F0(半音) = 12 * log2(词内 F0 中位 / 全句发声 F0 中位)

半音的好处是可跨句比较、不受说话人基频高低影响。
然后看两件事：
1. **局部突起**：某个非句末词的半音值比前后邻居高 >4 st（误重音）
2. **轮廓平滑度**：相邻词半音差的标准差（越大越跳）

输出每条的词级轮廓，方便人工核对用户听感。
"""
import argparse
import json
import os
import sys

import numpy as np
import parselmouth

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _pause_gap as PG       # noqa: E402


def st(x, base):
    return 12.0 * np.log2(max(x, 1e-9) / max(base, 1e-9))


def word_f0(path, spans):
    """每个词的发声段 F0 中位（Hz）。"""
    f = parselmouth.Sound(path).to_pitch(0.01, 75, 600).selected_array["frequency"]
    out = []
    for w, a, b in spans:
        i0, i1 = int(a / 0.01), max(int(b / 0.01), int(a / 0.01) + 1)
        seg = f[i0:i1]
        seg = seg[seg > 0]
        out.append(float(np.median(seg)) if len(seg) >= 2 else None)
    return out


def analyse(path, text, proc, model):
    spans = PG.align_spans(path, text, proc, model)
    if not spans:
        return None
    marks = PG.word_mark_map(text)
    f0s = word_f0(path, spans)
    valid = [x for x in f0s if x]
    if len(valid) < 3:
        return None
    base = float(np.median(valid))
    rel = [round(st(x, base), 1) if x else None for x in f0s]

    # 局部突起：非句末且比左右都高 4st 以上
    spike = []
    for i in range(1, len(rel) - 1):
        a, b, c = rel[i - 1], rel[i], rel[i + 1]
        if None in (a, b, c):
            continue
        kind = marks[i][1] if i < len(marks) else "none"
        if kind in ("period", "ellipsis") and i >= len(rel) - 2:
            continue                      # 句末降/升调不算
        if b - a >= 4.0 and b - c >= 4.0:
            spike.append((spans[i][0], b, round(b - (a + c) / 2, 1)))

    dif = [abs(rel[i + 1] - rel[i]) for i in range(len(rel) - 1)
           if rel[i] is not None and rel[i + 1] is not None]
    # 句内音域（半音跨度）：最大 − 最小，衡量「有没有大起大落」
    vals = [x for x in rel if x is not None]
    return dict(spans=[(w, round(a, 2), round(b, 2)) for w, a, b in spans],
                f0=[None if x is None else round(x, 0) for x in f0s],
                rel=rel, base=round(base, 0),
                spike=spike, rough=round(float(np.std(dif)), 2) if dif else 0.0,
                range_st=round(float(max(vals) - min(vals)), 1) if vals else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--seeds", default="42,43,44,45,46")
    ap.add_argument("--src", default="G:/_setup/_seedpick")
    ap.add_argument("--json", default="G:/_setup/_intonation.json")
    a = ap.parse_args()

    import _align_gate as AG
    proc, model = AG.load_model()
    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]

    out = {}
    for rid in [x.strip() for x in a.ids.split(",") if x.strip()]:
        text = PG.clean(rows[rid]["text"])
        out[rid] = {}
        print("== %s  %s" % (rid, text[:70]))
        base_p = "G:/_setup/_audio_ch123/out/%s.wav" % rid
        if os.path.exists(base_p):
            r = analyse(base_p, text, proc, model)
            if r:
                out[rid]["now"] = r
                print("   现役        rough=%.2f 突起%s" % (
                    r["rough"], ["%s%+.1f" % (s[0], s[1]) for s in r["spike"]] or "无"))
        for sd in seeds:
            p = os.path.join(a.src, rid, "s%d.wav" % sd)
            if not os.path.exists(p):
                continue
            r = analyse(p, text, proc, model)
            if not r:
                continue
            out[rid]["s%d" % sd] = r
            print("   seed%-3d     rough=%.2f 突起%s" % (
                sd, r["rough"], ["%s%+.1f" % (s[0], s[1]) for s in r["spike"]] or "无"))
            if sd == seeds[0]:
                print("      词级半音: " + " ".join(
                    "%s%+.1f" % (w[:6], v) for (w, _, _), v in zip(r["spans"], r["rel"]) if v is not None))
    json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("->", a.json)


if __name__ == "__main__":
    sys.exit(main())
