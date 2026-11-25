# -*- coding: utf-8 -*-
"""对指定目录重出词级时间戳（真·ASR，不信旧词表）。

为什么必须重出：
  · `_wl_words.json` 的末词时间普遍超出音频（c2_0191 标到 14.82s，实际 13.69s）
  · `_wl_regen1123.json` 是在**变速前**的 `_regen_1123` 上生成的，
    而分析对象 `_regen_final` 已经过 rubberband 变速 + 插停顿 ⇒ 词位置整体错位

用法（必须用 asr_venv 的解释器）：
  G:/_setup/asr_venv/Scripts/python.exe -u _wl_dir.py --dir _audio_ch123/out --out _wl_out2.json
  G:/_setup/asr_venv/Scripts/python.exe -u _wl_dir.py --dir _regen_final     --out _wl_final2.json
"""
import argparse
import json
import os
import sys
import time

ROOT = r"G:/_setup"
sys.path.insert(0, ROOT)
import _asr_lib  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", default="_narr_blocks.json")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    b = json.load(open(os.path.join(ROOT, a.ids), encoding="utf-8"))
    ids = []
    for blk in b:
        ids.extend(blk["ids"])
    ids = [x for x in ids if os.path.exists(os.path.join(ROOT, a.dir, x + ".wav"))]
    if a.limit:
        ids = ids[: a.limit]

    outp = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    old = {}
    if os.path.exists(outp):
        old = json.load(open(outp, encoding="utf-8"))
    todo = [x for x in ids if ("%s/%s.wav" % (a.dir, x)) not in old
            and (os.path.join(ROOT, a.dir, x + ".wav") not in old)]
    print("目标 %d / 已完成 %d / 待跑 %d" % (len(ids), len(ids) - len(todo), len(todo)), flush=True)

    t0 = time.time()
    B = 20
    for i in range(0, len(todo), B):
        chunk = todo[i:i + B]
        paths = [os.path.join(ROOT, a.dir, x + ".wav") for x in chunk]
        try:
            res = _asr_lib.transcribe(paths)
        except Exception as e:  # noqa: BLE001
            print("ERR chunk %d: %r" % (i, e), flush=True)
            continue
        for p, v in res.items():
            key = "%s/%s" % (a.dir, os.path.basename(p)[:-4])
            old[key] = v
        json.dump(old, open(outp, "w", encoding="utf-8"), ensure_ascii=False)
        el = time.time() - t0
        done = i + len(chunk)
        print("... %d/%d  已用 %.0fs  预计剩余 %.0fs" %
              (done, len(todo), el, el / max(1, done) * (len(todo) - done)), flush=True)
    print("完成，共 %d 条写入 %s" % (len(old), outp), flush=True)


if __name__ == "__main__":
    main()
