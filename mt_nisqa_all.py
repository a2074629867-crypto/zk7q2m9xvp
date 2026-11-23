# -*- coding: utf-8 -*-
"""mt_nisqa_all.py —— 对候选批量打 NISQA（MOS 四维），产出 {相对路径: 指标} 的 JSON。

为什么要单独一步：nisqa 只装在 G:/Python310，而 mt_score 跑在另一个 env。
约 0.7 秒/条，1800 条≈20 分钟，可以接受。

用法（必须用 G:/Python310）：
    G:/Python310/python.exe mt_nisqa_all.py --dirs _mt_raw_s42,_mt_raw_s1234 --out _mt_nisqa.json
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "G:/_setup")
import ch123_nisqa as N

ROOT = "G:/_setup"
MODEL = "D:/eval_models/nisqa/nisqa.tar"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", required=True)
    ap.add_argument("--out", default="_mt_nisqa.json")
    a = ap.parse_args()

    files = []
    for d in a.dirs.split(","):
        files += sorted(glob.glob(os.path.join(os.path.abspath(d.strip()), "*.wav")))
    old = {}
    if os.path.exists(a.out):
        old = json.load(open(a.out, encoding="utf-8"))
    todo = [f for f in files if f not in old]
    print("共 %d 个文件，已打 %d，待打 %d" % (len(files), len(files) - len(todo), len(todo)))
    if not todo:
        return

    tmp = tempfile.mkdtemp(prefix="nis_", dir=ROOT + "/_mt_tmp")
    mp = {}
    for i, f in enumerate(todo):
        key = "f%06d.wav" % i
        shutil.copy2(f, os.path.join(tmp, key))
        mp[key] = f
    df = N.run(tmp, MODEL)
    res = dict(old)
    for _, r in df.iterrows():
        src = mp.get(str(r["deg"]))
        if not src:
            continue
        res[src] = {"mos": round(float(r.get("mos_pred", 0)), 3),
                    "noi": round(float(r.get("noi_pred", 0)), 3),
                    "col": round(float(r.get("col_pred", 0)), 3),
                    "dis": round(float(r.get("dis_pred", 0)), 3),
                    "loud": round(float(r.get("loud_pred", 0)), 3)}
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    shutil.rmtree(tmp, ignore_errors=True)
    import numpy as np
    m = np.array([v["mos"] for v in res.values()])
    d = np.array([v["dis"] for v in res.values()])
    print("写完 %s（%d 条）  MOS 中位 %.2f  最低 %.2f  |  DIS 中位 %.2f  低于3.0 %d 条"
          % (a.out, len(res), np.median(m), m.min(), np.median(d), (d < 3.0).sum()))


if __name__ == "__main__":
    main()
