# -*- coding: utf-8 -*-
"""_hole_in_word.py —— 干声自带「洞切在词里」的全库清单（模型坏 take）。

背景：用户 2026-11-25 09:2x 听出 `himse/lf`，指认这是切点问题。修完后期注入后
仍有残留（`c2_0492` 的 Thump 等处），查明是**干声本身就劈**，与注入无关。
这类只能换 seed 重生成，改切点无效。

判据（用字符级强制对齐的词边界，20ms 精度，不再用 whisper）：
  洞的左边界或右边界落在某词的 (start+50ms, end-50ms) 内 ⇒ 该洞切在词里面。

用法：
  G:/Python310/python.exe -u _hole_in_word.py [--dir _regen_1123_norm] [--json _hole_in_word.json]
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def holes(y, sr, minlen=0.15, db_below=20.0):
    hop = int(sr * 0.02)
    n = len(y) // hop
    if n < 10:
        return []
    e = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) + 1e-12 for i in range(n)])
    db = 20 * np.log10(e)
    thr = max(np.percentile(db, 90) - db_below, -60)
    sil = db < thr
    out, i = [], 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            d = (j - i) * 0.02
            if d >= minlen and i > 3 and j < n - 3:
                out.append((i * 0.02, j * 0.02, d))
            i = j
        else:
            i += 1
    return out


def load_fa():
    p = os.path.join(HERE, "_wt_fa_cache.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="_regen_1123_norm")
    ap.add_argument("--json", default="_hole_in_word.json")
    ap.add_argument("--pad", type=float, default=0.05)
    a = ap.parse_args()

    FA = load_fa()
    ids = set(json.load(open(os.path.join(HERE, "_narr_ids716.json"), encoding="utf-8")))
    rows, files = [], 0
    for p in sorted(glob.glob(os.path.join(HERE, a.dir, "*.wav"))):
        sid = os.path.basename(p)[:-4]
        if sid not in ids:
            continue
        files += 1
        st = os.stat(p)
        key = "%s|%d|%d" % (os.path.basename(p), st.st_size, int(st.st_mtime))
        words = FA.get(key)
        if not words:
            continue
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        for t0, t1, d in holes(y, sr):
            # 严判据：洞的【两端】都落在同一个词内部 ⇒ 该词被劈成两半。
            # 只一端落在词内多半是 FA 边界噪声或句尾标点的尾音，不算劈。
            for s0, s1, w in words:
                if s0 + a.pad < t0 and t1 < s1 - a.pad:
                    rows.append(dict(sid=sid, hole=round(d, 2), word=w,
                                     w0=round(s0, 2), w1=round(s1, 2),
                                     h0=round(t0, 2), h1=round(t1, 2),
                                     split=round((s1 - s0) - d, 2)))
                    break
    print("扫 %d 句，干声自带「洞切在词里」%d 处，涉及 %d 句"
          % (files, len(rows), len(set(r["sid"] for r in rows))))
    seen = {}
    for r in rows:
        seen.setdefault(r["sid"], []).append(r)
    for sid, rs in sorted(seen.items(), key=lambda x: -len(x[1]))[:15]:
        print("  %-9s %d 处: %s" % (sid, len(rs),
                                    ", ".join("%s@%.2f(洞%.2f)" % (x["word"], x["edge"], x["hole"]) for x in rs[:4])))
    json.dump(rows, open(os.path.join(HERE, a.json), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", a.json)


if __name__ == "__main__":
    main()
