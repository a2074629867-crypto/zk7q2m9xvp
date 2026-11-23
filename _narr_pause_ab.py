# -*- coding: utf-8 -*-
"""_narr_pause_ab.py —— 旁白停顿注入 A/B 验收

只回答三件事：
  1) 注入了没有、改了多少（时长、条数、单条最大变化）
  2) 电平有没有被搞乱（voiced RMS 跨度 ≤1dB 是铁律，峰值不削波）
  3) 自然度有没有掉（`_nat_guard.verdict(domain='narr')`，逐条 A/B，缓存按 md5 自动失效）

不做：不重跑音色/物理闸（那些跟「只插静音」无关；要跑用 narr_gate_phys.py --dir）

用法：
  G:/Python310/python.exe _narr_pause_ab.py
  G:/Python310/python.exe _narr_pause_ab.py --a _audio_ch123/out --b _audio_narr_paused --limit 40
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _nat_guard as NG

TARGET = -24.0   # 只用于报告，不改文件


def vdb(y, sr):
    """voiced RMS（排除首尾 0.05s 与静音帧），与 norm_dlg.vdb 同口径的简化版。"""
    if y.ndim > 1:
        y = y.mean(1)
    fr = max(1, int(sr * 0.02))
    n = len(y) // fr
    if n < 3:
        return -90.0
    r = np.sqrt(np.mean(y[:n * fr].reshape(n, fr) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(r + 1e-12)
    thr = np.percentile(db, 95) - 35
    v = db[db > thr]
    return float(20 * np.log10(np.sqrt(np.mean(10 ** (v / 10.0))) + 1e-12)) if len(v) else -90.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="G:/_setup/_audio_ch123/out")
    ap.add_argument("--b", default="G:/_setup/_audio_narr_paused")
    ap.add_argument("--plan", default="G:/_setup/_castle_en_ch123_plan.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="只测前 N 条（nat 很慢）")
    ap.add_argument("--out", default="G:/_setup/_narr_pause_ab.json")
    a = ap.parse_args()

    ids = []
    for ln in open(a.plan, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        if not r.get("dialog"):
            ids.append(r["id"])
    files = []
    for i in ids:
        pa, pb = os.path.join(a.a, i + ".wav"), os.path.join(a.b, i + ".wav")
        if os.path.exists(pa) and os.path.exists(pb):
            files.append((i, pa, pb))
    if a.limit:
        files = files[:a.limit]
    print("可比对 %d 条（旁白）" % len(files), flush=True)

    rows = []
    for k, (i, pa, pb) in enumerate(files, 1):
        ya, sra = sf.read(pa, dtype="float32")
        yb, srb = sf.read(pb, dtype="float32")
        da, db_ = len(ya) / sra, len(yb) / srb
        ra, rb = vdb(ya, sra), vdb(yb, srb)
        rows.append(dict(id=i, dur_a=round(da, 3), dur_b=round(db_, 3),
                         dd=round(db_ - da, 3),
                         rms_a=round(ra, 2), rms_b=round(rb, 2),
                         peak_a=round(float(np.abs(ya).max()), 3),
                         peak_b=round(float(np.abs(yb).max()), 3)))
        if k % 50 == 0:
            print("  度量 %d/%d" % (k, len(files)), flush=True)

    dds = np.array([r["dd"] for r in rows])
    rms = [r["rms_b"] for r in rows]
    chg = [r for r in rows if abs(r["dd"]) > 0.05]
    print("\n=== 一、改动规模 ===")
    print("  总时长 %.1fs → %.1fs（%+.2f%%）" %
          (sum(r["dur_a"] for r in rows), sum(r["dur_b"] for r in rows),
           100.0 * (sum(r["dur_b"] for r in rows) / max(1e-6, sum(r["dur_a"] for r in rows)) - 1)))
    print("  有变化(>0.05s) %d/%d 条｜单条中位 %+.3fs｜最大 %+.2fs｜压缩最多 %+.2fs" %
          (len(chg), len(rows), float(np.median(dds)), float(dds.max()), float(dds.min())))
    print("=== 二、电平 ===")
    print("  voiced RMS min %.2f / 中位 %.2f / max %.2f ⇒ 跨度 %.2f dB（铁律 ≤1）" %
          (min(rms), float(np.median(rms)), max(rms), max(rms) - min(rms)))
    print("  峰值 max %.3f（<0.999 不削波）" % max(r["peak_b"] for r in rows))

    print("\n=== 三、自然度 A/B（narr 参照）===", flush=True)
    nat = []
    for k, (i, pa, pb) in enumerate(files, 1):
        va = NG.verdict(pa, domain="narr")
        vb = NG.verdict(pb, domain="narr")
        nat.append(dict(id=i, a=va, b=vb))
        if k % 20 == 0:
            print("  nat %d/%d" % (k, len(files)), flush=True)

    def dist(sel):
        d = {}
        for x in nat:
            v = (x[sel] or {})
            key = v.get("verdict") or v.get("code") or "UNK"
            d[key] = d.get(key, 0) + 1
        return d

    print("  原 A 判决:", dist("a"))
    print("  新 B 判决:", dist("b"))
    worse = []
    for x in nat:
        va, vb = x["a"] or {}, x["b"] or {}
        sa, sb = va.get("score"), vb.get("score")
        if sa is not None and sb is not None and sb < sa - 1.0:
            worse.append((x["id"], round(sa, 2), round(sb, 2)))
    print("  退步 >1σ 的条目 %d 条%s" % (len(worse), ("：" + str(worse[:8])) if worse else ""))

    json.dump(dict(rows=rows, nat=nat, worse=worse), open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出 %s" % a.out)


if __name__ == "__main__":
    main()
