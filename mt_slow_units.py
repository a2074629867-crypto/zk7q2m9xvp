# -*- coding: utf-8 -*-
"""单元级降速（rubberband tempo），用于把语速从 285 拉到 ~256 wpm。

为什么在插停顿之前做：停顿链给的是**绝对值**（inner/bound/clause），
先降速再插停顿，语音变长而停顿不变，语音占比才会上升。
反过来先插停顿再降速，停顿会被一起拉长 11%，占比反而恶化。

仅用 pitchq=quality，不加 transients=crisp（实测 crisps 会削短句起音）。
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"


def stretch(src, dst, tempo):
    subprocess.run(
        [FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
         "-af", "rubberband=tempo=%.4f:pitchq=quality" % tempo,
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", dst],
        check=True)


def one(args):
    src, dst, tempo = args
    try:
        stretch(src, dst, tempo)
        d0 = sf.info(src).duration
        d1 = sf.info(dst).duration
        return {"uid": os.path.splitext(os.path.basename(src))[0],
                "dur0": round(d0, 3), "dur1": round(d1, 3),
                "ratio": round(d1 / d0, 4), "status": "ok"}
    except Exception as e:
        return {"uid": os.path.splitext(os.path.basename(src))[0],
                "status": "fail:%s" % e}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", required=True)
    ap.add_argument("--out", dest="outdir", required=True)
    ap.add_argument("--tempo", type=float, default=0.90)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--units", help="只处理指定单元：N0001,N0002 或 ch1")
    ap.add_argument("--state", default="G:/_setup/_mt_loop_state.json")
    ap.add_argument("--json")
    a = ap.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.indir, "*.wav")))
    if a.units:
        if a.units.startswith("ch"):
            S = json.load(open(a.state, encoding="utf-8"))["units"]
            keep = {n for n, u in S.items() if u["ch"] == a.units}
            files = [f for f in files
                     if os.path.splitext(os.path.basename(f))[0] in keep]
        else:
            keep = set(a.units.split(","))
            files = [f for f in files
                     if os.path.splitext(os.path.basename(f))[0] in keep]

    jobs = [(f, os.path.join(a.outdir, os.path.basename(f)), a.tempo)
            for f in files]
    print("降速 %d 条，tempo=%.3f（时长 ×%.3f）" % (len(jobs), a.tempo, 1 / a.tempo))

    rows = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, r in enumerate(ex.map(one, jobs), 1):
            rows.append(r)
            if i % 20 == 0 or i == len(jobs):
                print("  %d/%d" % (i, len(jobs)), flush=True)

    ok = [r for r in rows if r["status"] == "ok"]
    bad = [r for r in rows if r["status"] != "ok"]
    if ok:
        ra = np.array([r["ratio"] for r in ok])
        print("\n完成 %d / 失败 %d" % (len(ok), len(bad)))
        print("  时长比 p10 %.4f  p50 %.4f  p90 %.4f（目标 %.4f）"
              % (*np.percentile(ra, [10, 50, 90]), 1 / a.tempo))
        print("  总时长 %.1fs → %.1fs（+%.1fs）"
              % (sum(r["dur0"] for r in ok), sum(r["dur1"] for r in ok),
                 sum(r["dur1"] for r in ok) - sum(r["dur0"] for r in ok)))
    for r in bad[:5]:
        print("  FAIL", r["uid"], r["status"])

    if a.json:
        json.dump(rows, open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
