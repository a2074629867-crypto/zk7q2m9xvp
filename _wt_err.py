# -*- coding: utf-8 -*-
"""whisper 词尾 vs 强制对齐词尾：切点误差有多大。

用法：G:/Python310/python.exe -u _wt_err.py c1_0174,c2_0458,... [--json out.json]
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _align_gate as AG

HERE = "G:/_setup"


def fa_words(res):
    """把字符跨度按 '|' 合并成词，词尾 = 最后一个字符的 end。"""
    words, cur = [], []
    for t in res["tokens"]:
        if t["tok"] == "|":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        words.append(cur)
    out = []
    for w in words:
        txt = "".join(x["tok"] for x in w)
        out.append(dict(w=txt, start=w[0]["start"] * AG.FRAME_MS / 1000.0,
                        end=w[-1]["end"] * AG.FRAME_MS / 1000.0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--dir", default="_regen_1123_norm")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    ids = [x.strip() for x in a.ids.split(",") if x.strip()]

    P = {json.loads(l)["id"]: json.loads(l) for l in
         open(os.path.join(HERE, "_narr_plan_for_pause.jsonl"), encoding="utf-8")}
    cache = json.load(open(os.path.join(HERE, "_wt_cache.json"), encoding="utf-8"))
    proc, model = AG.load_model()

    errs, rows = [], []
    for sid in ids:
        wav = os.path.join(HERE, a.dir, sid + ".wav")
        if not os.path.exists(wav):
            continue
        text = P.get(sid, {}).get("text", "")
        st = os.stat(wav)
        key = "%s.wav|%d|%d" % (sid, st.st_size, int(st.st_mtime))
        wh = cache.get(key)
        r = AG.align(proc, model, wav, text)
        if r is None:
            print("%-9s 对齐失败" % sid)
            continue
        fa = fa_words(r)
        if not wh:
            print("%-9s whisper 无缓存" % sid)
            continue
        # 按顺序配对（whisper 词数可能与 gold 不同，取前 min 个）
        n = min(len(fa), len(wh))
        for i in range(n):
            e_fa = fa[i]["end"]
            e_wh = wh[i][1]
            d = e_wh - e_fa        # 负 = whisper 比真实早
            errs.append(d)
            rows.append(dict(sid=sid, w=fa[i]["w"], fa_end=round(e_fa, 2),
                             wh_end=round(e_wh, 2), d=round(d, 3)))
    errs = np.array(errs)
    print("\n词尾误差（whisper − 强制对齐），n=%d" % len(errs))
    for q in (5, 25, 50, 75, 95):
        print("  p%-2d = %+6.1f ms" % (q, np.percentile(errs, q) * 1000))
    print("  |误差| 中位 %.1f ms   最大 %.1f ms" % (
        np.median(np.abs(errs)) * 1000, np.max(np.abs(errs)) * 1000))
    for thr in (0.04, 0.08, 0.12):
        k = int((errs < -thr).sum())
        print("  whisper 早于真实词尾 >%dms（切点会落进词里）: %d / %d = %.0f%%" % (
            thr * 1000, k, len(errs), k / len(errs) * 100))
    print("\n最差的 10 个词：")
    for r in sorted(rows, key=lambda r: r["d"])[:10]:
        print("  %-9s %-12s whisper %.2f  真实 %.2f  Δ%+5.0f ms" % (
            r["sid"], r["w"], r["wh_end"], r["fa_end"], r["d"] * 1000))
    if a.json:
        json.dump(rows, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
