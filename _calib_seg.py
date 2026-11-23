# -*- coding: utf-8 -*-
"""_calib_seg.py —— 句内漂移判据的零分布标定。

为什么要这一步（第 9 次同型教训）：
  按某个测量值分层比较前，必须先跑「同一程序、只换掉被检验变量」的零分布。
  这里要定的是「正常句内会有多大的段间跳变」，必须在**已知干净**的批次上测：
  已交付的 ch1 旁白 180 条（单音色、无 emo 标签、人耳通过）。
  对白批次（edit + emo）是可疑集，只能用来验检出，不能用来定阈值。

用法：
  G:/Python310/python.exe _calib_seg.py --dir _mt_trim_ch1_s42 --out _calib_seg_ch1.json
  G:/Python310/python.exe _calib_seg.py --dir ch123_final --out _calib_seg_dialog.json
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
import mt_seg_drift as D


def pct(v, q):
    v = [x for x in v if x is not None and np.isfinite(x)]
    return float(np.percentile(v, q)) if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--glob", default="*.wav")
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, a.glob)))
    if a.limit:
        files = files[:a.limit]
    print("标定 %d 条 <- %s" % (len(files), a.dir), flush=True)

    abs_dst, abs_dcen, abs_dslp, abs_dhnr, abs_drms = [], [], [], [], []
    dur_list, vcnt, rng = [], {}, {}
    per_file = []
    for k, p in enumerate(files):
        try:
            r = D.one(p)
        except Exception as e:  # noqa: BLE001
            print("  ERR", os.path.basename(p), e, file=sys.stderr)
            continue
        vcnt[r["verdict"]] = vcnt.get(r["verdict"], 0) + 1
        key = tuple(r.get("f0_range") or [])
        rng[key] = rng.get(key, 0) + 1
        dur_list.append(r["dur"])
        for q in r["pairs"]:
            if q["dst"] is not None:
                abs_dst.append(abs(q["dst"]))
            if q["dcen"] is not None:
                abs_dcen.append(abs(np.log(q["dcen"])))       # 取 |ln 比|
            if q["dslp"] is not None:
                abs_dslp.append(abs(q["dslp"]))
            if q["dhnr"] is not None:
                abs_dhnr.append(-q["dhnr"])                    # 只看下降
            if q["drms"] is not None:
                abs_drms.append(abs(q["drms"]))
        per_file.append(dict(file=os.path.basename(p), verdict=r["verdict"],
                             dur=r["dur"], n_win=r["n_win"],
                             events=len(r["events"])))
        if (k + 1) % 40 == 0:
            print("  %d/%d" % (k + 1, len(files)), flush=True)

    print("\n=== 判定分布 ===")
    print(vcnt)
    print("F0 范围使用：", {str(k): v for k, v in rng.items()})
    print("时长 中位 %.2fs  总窗数 %d  每句窗数 中位 %.0f"
          % (np.median(dur_list), len(abs_dst),
             np.median([x["n_win"] for x in per_file])))

    print("\n=== 段间跳变零分布（正常批次）===")
    print("%-22s %7s %7s %7s %7s %7s %7s"
          % ("量", "n", "p50", "p90", "p95", "p99", "max"))
    rows = [("|ΔF0| 半音", abs_dst), ("|ln 谱质心比|", abs_dcen),
            ("|Δ谱倾斜|", abs_dslp), ("HNR 下降 dB", abs_dhnr),
            ("|ΔRMS| dB", abs_drms)]
    out = {}
    for name, v in rows:
        vv = [x for x in v if x is not None and np.isfinite(x)]
        if not vv:
            continue
        out[name] = dict(n=len(vv), p50=pct(vv, 50), p90=pct(vv, 90),
                         p95=pct(vv, 95), p99=pct(vv, 99), max=float(np.max(vv)))
        print("%-22s %7d %7.2f %7.2f %7.2f %7.2f %7.2f"
              % (name, len(vv), out[name]["p50"], out[name]["p90"],
                 out[name]["p95"], out[name]["p99"], out[name]["max"]))

    if a.out:
        json.dump(dict(dir=a.dir, n_files=len(files), verdicts=vcnt,
                       f0_ranges={str(k): v for k, v in rng.items()},
                       quantiles=out, per_file=per_file),
                  open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n->", a.out)


if __name__ == "__main__":
    main()
