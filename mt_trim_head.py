# -*- coding: utf-8 -*-
"""裁掉 TTS 单元的前导/尾随空白。

问题：dots.tts 每段生成都在开头留 0.8~1.4s 静音（180 条全部 >0.15s，p50 1.22s），
      合计 216s，占单元总时长 18%。这些空白与 chapter_join 给的句间停顿（clause 1.695s）
      叠加，实际句间停顿变成 ~3.0s，这才是「停顿占比高 / 章太长」的真因。

只在**已插停顿之后**用安全（实测停顿链不在头尾插任何东西，逐条变化 0.00）。
裁剪量由 VAD 语音边界决定，不透支语音；两端各留 head_pad / tail_pad 缓冲并做 5ms 淡入淡出。
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from mt_final_pause import frame_db  # noqa: E402


def spans(x, sr):
    db, _, _ = frame_db(x, sr)
    if len(db) < 5:
        return None
    on = db > (np.percentile(db, 90) - 25.0)
    if not on.any():
        return None
    a = int(np.argmax(on))
    b = len(on) - int(np.argmax(on[::-1]))
    return a * 0.01, (len(on) - b) * 0.01, len(x) / sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", required=True)
    ap.add_argument("--out", dest="outdir", required=True)
    ap.add_argument("--head-pad", type=float, default=0.05)
    ap.add_argument("--tail-pad", type=float, default=0.25)
    ap.add_argument("--fade", type=float, default=0.005)
    ap.add_argument("--json")
    a = ap.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.indir, "*.wav")))
    rows = []
    cut_h = cut_t = 0.0
    d0 = d1 = 0.0

    for p in files:
        x, sr = sf.read(p, dtype="float32", always_2d=True)
        x = x.mean(1)
        r = spans(x, sr)
        if r is None:
            y = x
            hc = tc = 0.0
        else:
            h, t, dur = r
            hs = max(0.0, h - a.head_pad)
            te = min(dur, dur - t + a.tail_pad)
            i0 = int(round(hs * sr))
            i1 = int(round(te * sr))
            y = x[i0:i1].copy()
            hc, tc = hs, dur - te
        n = max(1, int(a.fade * sr))
        if len(y) > 2 * n:
            y[:n] *= np.linspace(0.0, 1.0, n)
            y[-n:] *= np.linspace(1.0, 0.0, n)
        sf.write(os.path.join(a.outdir, os.path.basename(p)), y, sr,
                 subtype="PCM_16")
        hc = hc if r else 0.0
        tc = tc if r else 0.0
        cut_h += hc
        cut_t += tc
        d0 += len(x) / sr
        d1 += len(y) / sr
        rows.append({"uid": os.path.splitext(os.path.basename(p))[0],
                     "cut_head": round(hc, 3), "cut_tail": round(tc, 3)})

    print("裁边 %d 条  head_pad=%.2fs tail_pad=%.2fs" % (len(files), a.head_pad, a.tail_pad))
    print("  裁掉头部 %.1fs / 尾部 %.1fs（合计 %.1fs）" % (cut_h, cut_t, cut_h + cut_t))
    print("  总时长 %.1fs → %.1fs（−%.1f%%）" % (d0, d1, 100 * (d0 - d1) / d0))
    if a.json:
        json.dump(rows, open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
