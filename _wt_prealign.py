# -*- coding: utf-8 -*-
"""_wt_prealign.py —— 预跑强制对齐，填充 `_wt_cache.json`（并行）

为什么要单独一步：
  `mt_final_pause` 为每一句算词时间（`_wtlib.word_times_cached`），
  缓存键是 `basename|size|mtime`。对白早就算过（命中 0.1s），
  **旁白 726 条一条都没算过** ⇒ 每条现场对齐 31s ⇒ 串行注入要 6 小时。

做法：多进程各自写 `_wt_part_<pid>.json`（`_wtlib.CACHE` 是模块常量，
多进程共享同一文件会互相覆盖），跑完合并进 `_wt_cache.json`。

用法：
  G:/Python310/python.exe _wt_prealign.py -j 8
  G:/Python310/python.exe _wt_prealign.py -j 8 --merge-only
"""
import argparse
import glob
import json
import os
import sys
import time
from multiprocessing import Pool

HERE = "G:/_setup"
ROOT = os.path.join(HERE, "_audio_ch123", "out")
CACHE = os.path.join(HERE, "_wt_cache.json")
PART = os.path.join(HERE, "_wt_part_%d.json")


def _init():
    sys.path.insert(0, HERE)
    import _wtlib
    _wtlib.CACHE = PART % os.getpid()


def work(path):
    sys.path.insert(0, HERE)
    import _wtlib
    t = time.time()
    try:
        r = _wtlib.word_times_cached(path)
        return (os.path.basename(path), len(r) if r else 0, round(time.time() - t, 1))
    except Exception as e:                                  # 单条失败不拖垮整批
        return (os.path.basename(path), -1, str(e)[:60])


def merge():
    allc = {}
    for p in sorted(glob.glob(os.path.join(HERE, "_wt_part_*.json"))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        allc.update(d)
        print("  合并 %-40s %d 条" % (os.path.basename(p), len(d)))
    cur = {}
    if os.path.exists(CACHE):
        cur = json.load(open(CACHE, encoding="utf-8"))
    n0 = len(cur)
    cur.update(allc)
    json.dump(cur, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print("缓存 %d → %d 条" % (n0, len(cur)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", "--jobs", type=int, default=8)
    ap.add_argument("--merge-only", action="store_true")
    a = ap.parse_args()
    if a.merge_only:
        merge()
        return

    ids = open(os.path.join(HERE, "_narr_ids.txt"), encoding="utf-8").read().strip().split(",")
    files = [os.path.join(ROOT, i + ".wav") for i in ids if os.path.exists(os.path.join(ROOT, i + ".wav"))]
    print("待对齐 %d 条，%d 进程" % (len(files), a.jobs), flush=True)
    t0 = time.time()
    done = 0
    with Pool(a.jobs, initializer=_init) as pool:
        for name, n, dt in pool.imap_unordered(work, files, chunksize=1):
            done += 1
            if done % 25 == 0 or n <= 0:
                print("  %d/%d  %-12s n=%s %.1fs  已用 %.0f 分"
                      % (done, len(files), name, n, dt if isinstance(dt, float) else 0,
                         (time.time() - t0) / 60), flush=True)
    merge()
    print("完成，用时 %.0f 分" % ((time.time() - t0) / 60))


if __name__ == "__main__":
    main()
