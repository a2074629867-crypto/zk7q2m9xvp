# -*- coding: utf-8 -*-
"""_gapfix_pool.py —— 对「同一条的多个候选 take」批量压停顿 + 统一底噪。

`_gapfix.py` 只处理 `<src>/<id>/s<seed>.wav` 且一条一个 take，
挑候选池时不够用。这里复用它的核心函数（silent_core / cut_core /
trim_edges / fill_floor），按 (id, take 路径) 列表逐个处理。

不做任何语义判断：只删真静音（silent_core 保证），所以不会吃字。
"""
import argparse
import json
import os
import sys

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np        # noqa: E402
import soundfile as sf    # noqa: E402

sys.path.insert(0, "G:/_setup")
import _align_gate as AG  # noqa: E402
import _gapfix as GF      # noqa: E402
import _pause_gap as PG   # noqa: E402


def process(src, text, proc, model, scale=1.0):
    spans = PG.align_spans(src, text, proc, model)
    if not spans:
        return None, "对齐失败"
    marks = PG.word_mark_map(text)
    n = min(len(spans) - 1, len(marks))

    y, sr = sf.read(src, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    fl = GF.floor_db(y, sr)
    dur_in = len(y) / sr

    todo = []
    for i in range(n):
        _, _, e0 = spans[i]
        _, s1, _ = spans[i + 1]
        ms = (s1 - e0) * 1000
        kind = PG.gap_kind(spans, marks, i)   # 口吃重复单独一档（≤200ms）
        lim = PG.LIMITS[kind] * scale
        if ms <= lim:
            continue
        core = GF.silent_core(y, sr, e0, s1, fl)
        if not core:
            todo.append((i, e0, s1, ms, kind, lim, "no_core"))
            continue
        c0, c1, _ = core
        core_ms = (c1 - c0) * 1000
        need = min(ms - lim, core_ms - 120)
        if need < 80:
            todo.append((i, e0, s1, ms, kind, lim, "core_short"))
            continue
        todo.append((i, c0, c1, core_ms, kind, need, "cut"))

    cut = [t for t in todo if t[6] == "cut"]
    skip = [t for t in todo if t[6] != "cut"]
    kept = []
    for i, c0, c1, core_ms, kind, need, _ in sorted(cut, key=lambda t: -t[1]):
        y, d = GF.cut_core(y, sr, c0, c1, need / 1000.0)
        if d:
            kept.append(dict(at=round(c0, 3), cut_ms=round(d / sr * 1000), kind=kind))

    end_kind = marks[n][1] if n < len(marks) else "period"
    keep = 0.55 if end_kind == "ellipsis" else 0.30
    y, _ = GF.trim_edges(y, sr, fl, tail_keep=keep)
    y = GF.fill_floor(y, sr)
    pk = float(np.abs(y).max())
    if pk > 0.97:
        y = y * (0.97 / pk)
    info = dict(dur_in=round(dur_in, 2), dur_out=round(len(y) / sr, 2),
                cuts=len(kept), skipped=len(skip),
                skip_items=[(t[4], round(t[3]), t[6]) for t in skip],
                cut_at=sorted(kept, key=lambda x: x["at"]))
    return y, sr, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--takes", required=True, help="take 路径，逗号分隔")
    ap.add_argument("--out", default="G:/_setup/_gapfix2")
    a = ap.parse_args()

    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
    text = PG.clean(rows[a.id]["text"])
    proc, model = AG.load_model()
    os.makedirs(a.out, exist_ok=True)
    rep = {}
    for src in [x.strip() for x in a.takes.split(",") if x.strip()]:
        tag = os.path.basename(src)[:-4]
        r = process(src, text, proc, model)
        if r[0] is None:
            print("%-6s %s" % (tag, r[1]))
            continue
        y, sr, info = r
        dst = os.path.join(a.out, "%s_%s.wav" % (a.id, tag))
        sf.write(dst, y, sr, subtype="PCM_24")
        rep[tag] = info
        print("%-6s %.2f→%.2fs 裁%d处 跳过%d %s" % (
            tag, info["dur_in"], info["dur_out"], info["cuts"], info["skipped"],
            ("跳:" + ",".join("%s%.0f(%s)" % (k, m, w[:8]) for k, m, w in info["skip_items"])) if info["skip_items"] else ""))
    json.dump(rep, open(os.path.join(a.out, "_report_%s.json" % a.id), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("->", a.out)


if __name__ == "__main__":
    sys.exit(main())
