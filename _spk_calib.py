# -*- coding: utf-8 -*-
"""_spk_calib.py —— 标定声纹闸门：CAM++ 在「2~4 秒短句」上的真实噪声底。

三个分布互相参照：
  A. 同一条音频自己 vs 自己（应 ≈1.000，检验实现）
  B. 同一条音频的**前半 / 后半**（同一人、同一句、不同片段）⇒ 片段级噪声底
  C. **不同 unit 之间**（同一人、不同句子）⇒ 「重生 take」真正的零假设分布
  D. 本轮被闸门拦下的 4 个 take 落在哪

结论只有一种判法：
  如果 C 的下沿（p5）比 0.339 还低，说明 0.339 完全在「同一个人」范围内 ⇒ 闸门定错了。
"""
import os
import random
import statistics as S
import sys
import wave

sys.path.insert(0, "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab")
import numpy as np
import soundfile as sf
import spk_embed as SP

ROOT = "G:/_setup"
TMP = os.path.join(ROOT, "_spk_calib_tmp")
os.makedirs(TMP, exist_ok=True)


def half(path, which):
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    y = y.mean(1)
    mid = len(y) // 2
    seg = y[:mid] if which == 0 else y[mid:]
    p = os.path.join(TMP, "%s_h%d.wav" % (os.path.basename(path)[:-4], which))
    sf.write(p, seg, sr)
    return p


def dur(path):
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


def main():
    st = __import__("json").load(open(os.path.join(ROOT, "_mt_adv_state.json"), encoding="utf-8"))["units"]
    uids = sorted(st)
    files = {u: os.path.join(ROOT, "_mt_pick", u + ".wav") for u in uids}
    files = {u: p for u, p in files.items() if os.path.exists(p)}
    print("可用交付版 %d 条，时长中位 %.2fs"
          % (len(files), S.median([dur(p) for p in files.values()])))

    # --- A / B：片段级噪声底 ---
    emb = {}
    selfsim, halfsim = [], []
    for u in uids[:20]:
        p = files.get(u)
        if not p:
            continue
        try:
            e = SP.embed(p)
            e0 = SP.embed(half(p, 0))
            e1 = SP.embed(half(p, 1))
        except Exception as ex:
            print("  skip", u, ex)
            continue
        emb[u] = e
        selfsim.append(SP.cos(e, e))
        halfsim.append(SP.cos(e0, e1))

    print("\nA 自己 vs 自己     n=%d  中位 %.3f  最低 %.3f"
          % (len(selfsim), S.median(selfsim), min(selfsim)))
    print("B 同句前半 vs 后半 n=%d  中位 %.3f  最低 %.3f  p5 %.3f"
          % (len(halfsim), S.median(halfsim), min(halfsim),
             sorted(halfsim)[max(0, int(len(halfsim) * .05))]))

    # --- C：不同 unit 之间（同一人、不同句子）---
    for u in uids:
        if u in emb or u not in files:
            continue
        try:
            emb[u] = SP.embed(files[u])
        except Exception:
            pass
    keys = sorted(emb)
    random.seed(7)
    cross = []
    for _ in range(600):
        a, b = random.sample(keys, 2)
        cross.append(SP.cos(emb[a], emb[b]))
    cross.sort()
    print("\nC 不同句之间      n=%d  中位 %.3f  p5 %.3f  p1 %.3f  最低 %.3f"
          % (len(cross), S.median(cross), cross[int(len(cross) * .05)],
             cross[int(len(cross) * .01)], cross[0]))

    # --- D：被拦下的 take ---
    bad = [("N0634", "2033"), ("N0219", "2033"), ("N0219", "2035"), ("N0627", "2033")]
    print("\nD 被闸门拦下的 take（与它自己那一句的原版比）：")
    print("  %-7s %-6s %-14s %-8s %s" % ("uid", "seed", "原版spk", "落在C的第几百分位", ""))
    for u, sd in bad:
        w = os.path.join(ROOT, "_mt_adv_s%s" % sd, u + ".wav")
        if not (os.path.exists(w) and files.get(u)):
            print("  %-7s %-6s 缺文件" % (u, sd))
            continue
        v = SP.cos(emb.get(u) or SP.embed(files[u]), SP.embed(w))
        pct = 100.0 * sum(1 for c in cross if c < v) / len(cross)
        print("  %-7s %-6s %-14.3f 第 %5.1f 百分位" % (u, sd, v, pct))

    # --- 对照：被采纳的 take 落点 ---
    good = [("N0301", "2031"), ("N0480", "2031"), ("N0602", "2031"),
            ("N0634", "2035"), ("N0666", "2031")]
    print("\n对照：本轮被采纳的 take")
    for u, sd in good:
        w = os.path.join(ROOT, "_mt_adv_s%s" % sd, u + ".wav")
        if not os.path.exists(w):
            continue
        v = SP.cos(emb.get(u) or SP.embed(files[u]), SP.embed(w))
        pct = 100.0 * sum(1 for c in cross if c < v) / len(cross)
        print("  %-7s %-6s %.3f   第 %5.1f 百分位" % (u, sd, v, pct))


if __name__ == "__main__":
    main()
