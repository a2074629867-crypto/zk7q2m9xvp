# -*- coding: utf-8 -*-
"""_prealign_fa.py —— 全库预跑「字符级强制对齐」，填充 `_wt_fa_cache.json`。

为什么单独一步：单条对齐 ~1.5s，716 条串行近 20 分钟；且模型加载只该付一次。
做法同 `_wt_prealign.py`：多进程各自算，父进程合并（避免并发写同一文件）。

用法：
  G:/Python310/python.exe -u _prealign_fa.py -j 4
"""
import argparse
import glob
import json
import os
import sys
import time
from multiprocessing import Pool

HERE = "G:/_setup"
CACHE = os.path.join(HERE, "_wt_fa_cache.json")


def work(args):
    wav, = args
    sys.path.insert(0, HERE)
    t = time.time()
    try:
        import _wtlib2
        rw = _wtlib2.word_times_fa(wav)
        st = os.stat(wav)
        key = "%s|%d|%d" % (os.path.basename(wav), st.st_size, int(st.st_mtime))
        return (key, [list(x) for x in rw], round(time.time() - t, 1))
    except Exception as e:                                  # 单条失败不拖垮整批
        return (os.path.basename(wav), None, "%s: %s" % (type(e).__name__, str(e)[:60]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", type=int, default=4)
    ap.add_argument("--dir", default="_regen_1123_norm")
    a = ap.parse_args()

    d = os.path.join(HERE, a.dir)
    ids = sorted(os.path.basename(p)[:-4] for p in glob.glob(d + "/*.wav"))
    print("待对齐 %d 条（%s）" % (len(ids), a.dir), flush=True)

    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    todo = []
    for sid in ids:
        p = os.path.join(d, sid + ".wav")
        st = os.stat(p)
        key = "%s|%d|%d" % (os.path.basename(p), st.st_size, int(st.st_mtime))
        if key not in cache:
            todo.append((p,))
    print("已缓存 %d，待跑 %d" % (len(ids) - len(todo), len(todo)), flush=True)

    ok = bad = 0
    t0 = time.time()
    with Pool(a.j) as pool:
        for i, (key, rw, info) in enumerate(pool.imap_unordered(work, todo), 1):
            if rw is None:
                bad += 1
                print("  [%d/%d] %s 失败 %s" % (i, len(todo), key, info), flush=True)
            else:
                cache[key] = rw
                ok += 1
            if i % 25 == 0:
                el = time.time() - t0
                print("  %d/%d  用时 %.0fs  预计剩余 %.0fs" % (
                    i, len(todo), el, el / i * (len(todo) - i)), flush=True)
            if i % 100 == 0:
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print("完成 ok=%d bad=%d  总耗时 %.0fs  缓存 %d 条" % (
        ok, bad, time.time() - t0, len(cache)), flush=True)


if __name__ == "__main__":
    main()
