# -*- coding: utf-8 -*-
"""trim_cues.py —— 把候选音裁到真实发声区间，重算静音/语速指标。

为什么必须裁
------------
字幕 cue 的窗口普遍比台词宽：实测 Son of Rambow 里 54 条 Lee Carter 候选，
19 条静音占 55–85%，其中 `c210` 2.11s 里有 85% 是空白。带这么多静音当参考音
有两个坏处：① 声纹 embedding 被静音摊薄；② `1−A`（委屈判据）被静音刷分——
emo_cut 抬头写的第一个反例就是这么来的。

裁法（与 film_seg.py 同一套参数，改之前先看那里的实测说明）
----------------------------------------------------------
  帧长 25ms / 帧移 10ms；阈值 = max(底噪 p20 + 6dB, 峰值 p95 − 30dB)
  取「第一个有声帧 → 最后一个有声帧」，前后各留 50ms
  裁完短于 1.2s 的直接丢（不够判声纹）

用法
----
  python trim_cues.py --cand G:/MOVIE_DL/_emo_lee2/candidates.json \
      --outdir G:/MOVIE_DL/_emo_lee2/trim --out G:/MOVIE_DL/_emo_lee2/candidates_trim.json
"""
import argparse
import json
import os

import numpy as np
import soundfile as sf


def frames_db(x, sr, win=0.025, hop=0.010):
    w, h = int(win * sr), int(hop * sr)
    n = max(1, (len(x) - w) // h + 1)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(x) - 1)
    fr = x[idx]
    return 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9), h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pad", type=float, default=0.05)
    ap.add_argument("--min-dur", type=float, default=1.2)
    a = ap.parse_args()

    cand = json.load(open(a.cand, encoding="utf-8"))
    os.makedirs(a.outdir, exist_ok=True)
    keep, drop = [], 0
    for c in cand:
        x, sr = sf.read(c["path"], dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        db, hop = frames_db(x, sr)
        thr = max(np.percentile(db, 20) + 6.0, np.percentile(db, 95) - 30.0)
        v = db > thr
        if not v.any():
            drop += 1
            continue
        i0 = int(np.argmax(v))
        i1 = len(v) - int(np.argmax(v[::-1]))
        t0 = max(0.0, i0 * hop / sr - a.pad)
        t1 = min(len(x) / sr, i1 * hop / sr + a.pad)
        if t1 - t0 < a.min_dur:
            drop += 1
            continue
        y = x[int(t0 * sr):int(t1 * sr)]
        dst = os.path.join(a.outdir, os.path.basename(c["path"]))
        sf.write(dst, y, sr, subtype="PCM_16")

        db2, hop2 = frames_db(y, sr)
        thr2 = max(np.percentile(db2, 20) + 6.0, np.percentile(db2, 95) - 30.0)
        v2 = db2 > thr2
        sil = float(1.0 - v2.mean())
        # 最长连续静音
        best = run = 0
        for b in v2:
            run = 0 if b else run + 1
            best = max(best, run)
        long_sil = best * hop2 / sr
        voiced = max(1e-6, v2.sum() * hop2 / sr)
        nw = len(c["text"].split())

        d = dict(c)
        d["path"] = dst.replace("\\", "/")
        d["dur"] = round(t1 - t0, 2)
        d["orig_dur"] = c["dur"]
        d["trim_off"] = round(t0, 2)
        d["sil"] = round(sil, 2)
        d["long_sil"] = round(long_sil, 2)
        d["wpm"] = round(nw / voiced, 1)
        d["bad"] = []
        if d["sil"] > 0.35:
            d["bad"].append("静音%d%%" % round(sil * 100))
        if long_sil > 1.0:
            d["bad"].append("连续静音%.1fs" % long_sil)
        keep.append(d)

    json.dump(keep, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("裁后保留 %d 条（丢 %d）" % (len(keep), drop))
    import collections
    bad = collections.Counter(b.split("%")[0] for d in keep for b in d["bad"])
    print("仍不达标：", dict(bad) if bad else "无")
    for d in sorted(keep, key=lambda z: z["sil"])[:5]:
        print("  %-6s %.2fs sil=%0.2f %s" % (d["id"], d["dur"], d["sil"], d["text"][:50]))


if __name__ == "__main__":
    main()
