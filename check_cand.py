#!/usr/bin/env python
"""候选 ref 的可用性硬检查：指标高不等于能用。

ref 层指标（1−A、z1）只能说明「这段音频听起来像委屈的 Charles」，不能说明
「这段音频是干净完整的一句话」。实测踩过两次：
  · c394 "Il va t'arriver quelque chose, Charles." —— 是在**叫他的名字**，
    说话人不是 Charles；
  · c304 "Thomas, passez-moi mon miroir." —— 用的是 vous 敬称，是长辈在说话。
两条的 1−A 都排在最前面。

这里用三个客观量代替「看起来对」：
  ① 语速（词/有声秒）：法语正常 2–4。低于 1.5 说明有长静音或混了别人的话
  ② 静音占比：>35% 不适合当 ref
  ③ 能量轨迹：首尾各 300ms 是否几乎没有声音（切偏了）
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")

SIL_DB = -40.0


def analyze(p):
    x, sr = sf.read(p, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    w = int(0.02 * sr)                     # 20ms 窗
    n = len(x) // w
    if n < 5:
        return None
    fr = x[:n * w].reshape(n, w)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    voiced = db > SIL_DB
    dur = len(x) / sr
    v_dur = float(voiced.sum() * 0.02)
    # 首尾各 300ms
    k = max(1, int(0.3 / 0.02))
    head_db = float(db[:k].max()) if n >= k else -99
    tail_db = float(db[-k:].max()) if n >= k else -99
    # 最长连续静音
    longest, cur = 0, 0
    for v in voiced:
        cur = 0 if v else cur + 1
        longest = max(longest, cur)
    return dict(dur=round(dur, 2), voiced=round(v_dur, 2),
                sil_ratio=round(1 - v_dur / dur, 2) if dur else 1.0,
                longest_sil=round(longest * 0.02, 2),
                head_db=round(head_db, 1), tail_db=round(tail_db, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="out/soft_cand.json")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--out", default="out/soft_check.json")
    a = ap.parse_args()

    rows = json.load(open(a.cand, encoding="utf-8"))[:a.top]
    print("%-26s %5s %5s %5s %5s %6s %6s %6s" % (
        "file", "dur", "有声", "静音%", "最长静", "首dB", "尾dB", "语速"))
    keep = []
    for r in rows:
        st = analyze(r["p"])
        if not st:
            continue
        # 词数用字幕文本粗估（法语按空格 + 连字符拆开算）
        words = len([w for w in re.split(r"[\s\-']+", r["text"]) if w.strip()])
        sps = round(words / st["voiced"], 2) if st["voiced"] > 0 else 0
        flags = []
        if sps < 1.5:
            flags.append("语速过低→有静音或混人")
        if st["sil_ratio"] > 0.35:
            flags.append("静音过多")
        if st["head_db"] < -35:
            flags.append("开头空")
        if st["tail_db"] < -35:
            flags.append("结尾空")
        print("%-26s %5.2f %5.2f %5.0f%% %5.2f %6.1f %6.1f %6.2f %s" % (
            os.path.basename(r["p"]), st["dur"], st["voiced"], st["sil_ratio"] * 100,
            st["longest_sil"], st["head_db"], st["tail_db"], sps, " ".join(flags)))
        r.update(st, sps=sps, words=words, flags=flags)
        if not flags:
            keep.append(r)

    print("\n=== 无硬伤的候选 %d 条 ===" % len(keep))
    for r in keep:
        print("  %-26s 1-A=%.3f z1=%.2f %s" % (
            os.path.basename(r["p"]), r["soft"], r["z1"], r["text"][:50]))
    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写 ->", a.out)


if __name__ == "__main__":
    main()
