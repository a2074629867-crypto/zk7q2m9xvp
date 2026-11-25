# -*- coding: utf-8 -*-
"""c1_0174 的 himself 被切开 —— 三份时间戳对照

whisper 词边界（_wl_final2 / _wl_regen1123）vs 强制对齐（_wt_cache）
vs 真实能量谷（包络最小值）
"""
import json
import os

import numpy as np
import soundfile as sf

HERE = "G:/_setup"


def load_wl(fn):
    d = json.load(open(os.path.join(HERE, fn), encoding="utf-8"))
    out = {}
    for k, v in d.items():
        out[k.replace("\\", "/").rsplit("/", 1)[-1].replace(".wav", "")] = v
    return out


def env(path, hop=0.01):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    n = len(y) // int(sr * hop)
    e = np.array([
        np.sqrt(np.mean(y[i * int(sr * hop):(i + 1) * int(sr * hop)] ** 2)) + 1e-12
        for i in range(n)
    ])
    return y, sr, 20 * np.log10(e), hop


def cache_lookup(name):
    c = json.load(open(os.path.join(HERE, "_wt_cache.json"), encoding="utf-8"))
    hits = [k for k in c if k.startswith(name)]
    return [(k, c[k]) for k in hits]


def show_words(tag, words, t0=1.4, t1=3.2):
    print("  [%s]" % tag)
    for w in words:
        s = w.get("start", w.get("t0"))
        e = w.get("end", w.get("t1"))
        if e < t0 or s > t1:
            continue
        print("    %-10s %6.2f - %6.2f" % (w.get("w", w.get("word", "?")), s, e))


def main():
    sid = "c1_0174"
    wl_f = load_wl("_wl_final2.json")
    wl_d = load_wl("_wl_regen1123.json")

    print("=" * 70)
    print("whisper 词边界（交付版 _regen_final）")
    v = wl_f[sid]
    show_words("final", v["words"])
    print("  dur = %.2f  text = %s" % (v["dur"], v["text"]))

    print("\nwhisper 词边界（干声 _regen_1123_norm）")
    k = [x for x in wl_d if x.endswith(sid)]
    if k:
        v2 = wl_d[k[0]]
        show_words("dry", v2["words"])
        print("  dur = %.2f" % v2["dur"])

    # 强制对齐缓存：按文件 size|mtime
    for tag, path in (("final", os.path.join(HERE, "_regen_final", sid + ".wav")),
                      ("dry", os.path.join(HERE, "_regen_1123_norm", sid + ".wav"))):
        if not os.path.exists(path):
            print("\n%s 不存在" % path)
            continue
        st = os.stat(path)
        key = "%s.wav|%d|%d" % (sid, st.st_size, int(st.st_mtime))
        c = json.load(open(os.path.join(HERE, "_wt_cache.json"), encoding="utf-8"))
        print("\n强制对齐 %s  key=%s  hit=%s" % (tag, key, key in c))
        if key in c:
            print("  " + "  ".join("%s %.2f-%.2f" % (w, a, b) for a, b, w in c[key]))

    # 能量谷
    print("\n" + "=" * 70)
    print("包络（10ms 帧，看 himself 附近的真实能量谷）")
    for tag, path in (("dry", os.path.join(HERE, "_regen_1123_norm", sid + ".wav")),
                      ("final", os.path.join(HERE, "_regen_final", sid + ".wav"))):
        if not os.path.exists(path):
            continue
        y, sr, db, hop = env(path)
        i0, i1 = int(1.5 / hop), int(3.2 / hop)
        seg = db[i0:i1]
        # 找局部最小值（每 20ms 一个点）
        mins = []
        for i in range(3, len(seg) - 3):
            if seg[i] == seg[i - 3:i + 4].min():
                mins.append(((i0 + i) * hop, seg[i]))
        # 5ms 内合并
        merged = []
        for t, v2 in mins:
            if merged and t - merged[-1][0] < 0.08:
                if v2 < merged[-1][1]:
                    merged[-1] = (t, v2)
                continue
            merged.append((t, v2))
        print("  [%s] 能量谷(<-35dB): %s" % (
            tag, [(round(t, 2), round(v2)) for t, v2 in merged if v2 < -35]))
        # himself 区间内的能量轮廓（每 40ms）
        print("    1.60-2.70s 每 40ms:")
        for i in range(int(1.60 / 0.04), int(2.70 / 0.04), 1):
            t = i * 0.04
            j = int(t / hop)
            if j >= len(db):
                break
            bar = "#" * max(0, int((db[j] + 60) / 1.5))
            print("      %5.2f %6.1f %s" % (t, db[j], bar))


if __name__ == "__main__":
    main()
