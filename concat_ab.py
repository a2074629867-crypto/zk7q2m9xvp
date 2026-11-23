# -*- coding: utf-8 -*-
"""A/B 实验：chunk 一次生成 vs 现有逐句音频按块拼接。

背景
----
现有 955 条旁白是逐句生成的（每句一个 wav）。实测 81 个 chunk 块的 ids 拼接文本
与块文本 81/81 完全一致，说明可以按块拼接复现文本顺序。

如果「拼接 + 停顿移植」的听感/指标接近「chunk 一次生成」，就能省掉 79 块 × 8.3 分钟
≈ 11 小时的 TTS 时间。

只做对比，不覆盖任何现有产物。
"""
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

OUT = "G:/_setup/_concat_ab"
SRC = "G:/_setup/_audio_ch123/out"


def trim_sil(y, sr, thresh_db=-45.0, keep=0.05):
    """裁掉首尾静音，各留 keep 秒。

    为什么必须裁：现有 955 条是逐句生成的，每句首尾都带 qc 检查过的 lead/tail 静音。
    直接首尾相接，这些静音会累加 —— 实测 B000 不裁时 81.9s，而 chunk 生成只要 66.1s
    （+24%），朗读节奏明显拖慢。
    """
    w = max(1, int(0.01 * sr))
    n = len(y) // w
    if not n:
        return y
    fr = np.array([np.sqrt((y[i * w:(i + 1) * w].astype(np.float64) ** 2).mean())
                   for i in range(n)])
    thr = 10 ** (thresh_db / 20.0)
    voiced = np.where(fr >= thr)[0]
    if not len(voiced):
        return y
    a = max(0, (voiced[0] * w) - int(keep * sr))
    b = min(len(y), ((voiced[-1] + 1) * w) + int(keep * sr))
    return y[a:b]


def concat(bid, ids, gap=0.10, do_trim=True):
    """按顺序拼 wav。句间留 gap 秒静音（留出可被停顿移植识别的间隙）。"""
    ys, sr = [], None
    for i in ids:
        p = os.path.join(SRC, i + ".wav")
        y, s = sf.read(p)
        if y.ndim > 1:
            y = y.mean(1)
        if sr is None:
            sr = s
        y = y.astype(np.float32)
        if do_trim:
            y = trim_sil(y, sr)
        ys.append(y)
        ys.append(np.zeros(int(gap * sr), dtype=np.float32))
    return np.concatenate(ys), sr


def main():
    os.makedirs(OUT, exist_ok=True)
    blocks = {b["bid"]: b for b in json.load(open("G:/_setup/_narr_blocks.json", encoding="utf-8"))}
    todo = sys.argv[1:] or ["B000", "B001", "B002"]
    for bid in todo:
        b = blocks[bid]
        y, sr = concat(bid, b["ids"])
        raw = os.path.join(OUT, bid + "_concat.wav")
        sf.write(raw, y, sr)
        fin = os.path.join(OUT, bid + "_concat_t.wav")
        rep = os.path.join(OUT, bid + "_concat_t.json")
        cmd = [r"G:/Python310/python.exe", r"G:/_setup/pause_donor_by_position.py",
               "--gen", raw, "--donor", r"E:/tts-models/acpp/out/calmdeep_final/real_trim.wav",
               "--out", fin, "--report", rep,
               "--min-gap", "0.30", "--gap-min", "0.85", "--gap-max", "1.70"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("[%s] 拼接 %.1fs → 移植 rc=%s %s" % (
            bid, len(y) / sr, r.returncode, (r.stdout or r.stderr or "").strip()[:100]), flush=True)
    print("done →", OUT)


if __name__ == "__main__":
    main()
