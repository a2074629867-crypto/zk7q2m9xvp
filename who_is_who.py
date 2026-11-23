# -*- coding: utf-8 -*-
"""聚类之后「点名」：每个簇抽几条转写，靠文本判断这一簇是谁。

为什么不能靠声纹直接给名字：没有模板就没有标签。聚类只能告诉你「有几个声音」，
不能告诉你「哪个是爸爸」。所以最后一步必须读台词 —— 城堡之王里就是靠
"Papa, où on va?" 认出孩子的。

用法:
  python who_is_who.py --seg out/hope_full/segments.json --n 8
"""
import argparse
import json
import random

import soundfile as sf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seg", required=True)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--min-dur", type=float, default=2.0)
    ap.add_argument("--max-dur", type=float, default=9.0)
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    d = json.load(open(a.seg, encoding="utf-8"))
    rows = d["rows"]
    print("簇数 k=%d，段数 %d" % (d["k"], len(rows)), flush=True)

    from faster_whisper import WhisperModel
    m = WhisperModel(a.model, device="cpu", compute_type="int8")

    random.seed(a.seed)
    by = {}
    for r in rows:
        by.setdefault(r["cl"], []).append(r)

    for c in sorted(by, key=lambda z: -len(by[z])):
        pool = [r for r in by[c] if a.min_dur <= r["dur"] <= a.max_dur]
        pick = random.sample(pool, min(a.n, len(pool))) if pool else []
        pick.sort(key=lambda r: r["t0"])
        f0 = sorted(r["f0"] for r in by[c] if r["f0"] > 0)
        med = f0[len(f0) // 2] if f0 else 0
        print("\n===== 簇 %d：%d 条，F0 中位 %.0f Hz =====" % (c, len(by[c]), med), flush=True)
        for r in pick:
            x, sr = sf.read(r["path"], dtype="float32", always_2d=True)
            x = x.mean(axis=1)
            peak = float(abs(x).max()) or 1.0
            x = x / peak * 0.9
            segs, _ = m.transcribe(x, language="en", beam_size=1,
                                   vad_filter=False, condition_on_previous_text=False)
            txt = " ".join(s.text.strip() for s in segs).strip()
            print("  @%7.1fs %4.1fs  %s" % (r["t0"], r["dur"], txt[:150]), flush=True)


if __name__ == "__main__":
    main()
