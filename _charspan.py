# -*- coding: utf-8 -*-
"""字符级时间跨度：看停顿到底切在哪个音上。

用法：
  G:/Python310/python.exe -u _charspan.py <wav> "<text>" [t0 t1]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _align_gate as AG


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    wav, text = sys.argv[1], sys.argv[2]
    t0 = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    t1 = float(sys.argv[4]) if len(sys.argv) > 4 else 1e9
    proc, model = AG.load_model()
    r = AG.align(proc, model, wav, text)
    if r is None:
        print("对齐失败")
        return
    print("wav=%s  dur=%.2f  覆盖=%.2f" % (wav, r["dur"], r["covered_ratio"]))
    print("贪心解码: %s" % r["greedy"][:140])
    print("%-6s %7s %7s %7s %6s" % ("char", "start", "end", "ms", "score"))
    for t in r["tokens"]:
        s = t["start"] * AG.FRAME_MS / 1000.0
        e = t["end"] * AG.FRAME_MS / 1000.0
        if e < t0 or s > t1:
            continue
        print("%-6s %7.2f %7.2f %7.1f %6.2f" % (
            t["tok"] if t["tok"] != "|" else "_", s, e, t["ms"], t["score"]))
    print("\n贪心路径逐字符（含多念的碎片）:")
    for g in r["greedy_spans"]:
        s = g["start"] * AG.FRAME_MS / 1000.0
        e = g["end"] * AG.FRAME_MS / 1000.0
        if e < t0 or s > t1:
            continue
        print("  %-4s %6.2f-%6.2f  (%.0fms)" % (g["tok"], s, e, (e - s) * 1000))


if __name__ == "__main__":
    main()
