# -*- coding: utf-8 -*-
"""_import_cloud.py —— 把云端回传的 wav 归位成流水线能吃的目录。

云端结构：<ch>_s<seed>/<uid>.wav
本地目标：_mt_raw_<ch>_s<seed>/<uid>.wav

用法：
  python _import_cloud.py --src D:/dl/cloud_out --ch ch1
  python _import_cloud.py --src D:/dl/cloud_out --ch ch1 --seeds 42 --dry-run
"""
import argparse
import glob
import os
import shutil
import sys

sys.path.insert(0, "G:/_setup")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--ch", required=True)
    ap.add_argument("--seeds", default="")
    ap.add_argument("--root", default="G:/_setup")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    only = {s.strip() for s in a.seeds.split(",") if s.strip()}
    dirs = sorted(d for d in os.listdir(a.src)
                  if os.path.isdir(os.path.join(a.src, d)) and d.startswith(a.ch + "_s"))
    if not dirs:
        print("源目录里没有 %s_s* 子目录：%s" % (a.ch, a.src))
        return 1

    total = 0
    for d in dirs:
        seed = d.split("_s", 1)[1]
        if only and seed not in only:
            continue
        src = os.path.join(a.src, d)
        dst = os.path.join(a.root, "_mt_raw_%s_s%s" % (a.ch, seed))
        wavs = sorted(glob.glob(os.path.join(src, "*.wav")))
        if not a.dry_run:
            os.makedirs(dst, exist_ok=True)
        n = 0
        for p in wavs:
            if os.path.getsize(p) < 1024:
                continue
            if not a.dry_run:
                shutil.copy2(p, os.path.join(dst, os.path.basename(p)))
            n += 1
        total += n
        print("%-14s → %-26s %3d 条" % (d, os.path.basename(dst), n))

    print("合计 %d 条" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
