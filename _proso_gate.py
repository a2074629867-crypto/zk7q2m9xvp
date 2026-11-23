# -*- coding: utf-8 -*-
"""把 TTSDS2 PROSODY 从「整批分布分」拆成「逐条分」，用来当打标签前的闸门。

官方公式（benchmarks/benchmark.py:436）:
    score = d_noise / (d_ref + d_noise) * 100
其中 d_ref / d_noise 是 **分布与分布** 的 Wasserstein 距离。

逐条化：把单条音频看成「一个点的分布」，点质量到经验分布的 W1 = 平均绝对偏差
（多维用 RMS 欧氏距离）。于是
    d_ref_i  = mean_j |x_i - ref_j|
    d_noise_i= min_n mean_j |x_i - noise_n_j|
    score_i  = 100 * d_noise_i / (d_ref_i + d_noise_i)

这是**改动过的口径**，不是官方分。所以脚本自带校验：
逐条分的组均值必须复现官方批次分的排序（delivered / cand / ctl）。
"""
import argparse
import json
import os
import re
import sys

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HOME", "E:/ttsds/hf")
os.environ.setdefault("TTSDS_CACHE_DIR", "E:/ttsds/cache")
os.environ.setdefault("TMPDIR", "E:/ttsds/tmp")
os.environ.setdefault("TEMP", "E:/ttsds/tmp")
os.environ.setdefault("TMP", "E:/ttsds/tmp")

import numpy as np

from ttsds.util.dataset import DirectoryDataset
from ttsds.ttsds import BENCHMARKS, NOISE_DATASETS

BASE = "E:/ttsds/data"
HERE = os.path.dirname(os.path.abspath(__file__))
BENCHES = ("mpm", "pitch", "hubert_token_sr", "allosaurus_sr")


def safe(tid):
    return tid.replace(":", "_").replace("|", "_")


def load_meta():
    d = json.load(open(os.path.join(HERE, "_align_dataset.json"), encoding="utf-8"))
    by_name = {}
    for r in d["records"]:
        if r["side"] != "narr":
            continue
        by_name[safe(r["tid"]) + ".wav"] = dict(
            tid=r["tid"], gid=r["gid"], kind=(r["take"] or {}).get("kind"),
            seed=(r["take"] or {}).get("seed"), adv=r["adv"], cond=(r["take"] or {}).get("cond"),
        )
    return by_name


def dist_of(bench, ds):
    """取分布（命中缓存就秒回）。"""
    return bench.get_distribution(ds)


def point_dist(x, ref):
    """点质量到经验分布的 W1：1D 用平均绝对偏差，多维用 RMS 欧氏。"""
    x = np.asarray(x, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    if ref.ndim == 1:
        return float(np.mean(np.abs(x - ref)))
    d = np.linalg.norm(ref - x[None, :], axis=1)
    return float(np.sqrt(np.mean(d ** 2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="syn_delivered,syn_cand,syn_ctl")
    ap.add_argument("--out", default="E:/ttsds/per_take_prosody.json")
    a = ap.parse_args()

    meta = load_meta()
    ref_ds = DirectoryDataset(os.path.join(BASE, "ref_human"), name="human")
    print("参考集: %d 文件" % len(ref_ds))

    groups = []
    for s in a.sets.split(","):
        p = os.path.join(BASE, s)
        if not os.path.isdir(p):
            raise SystemExit("缺目录 " + p)
        groups.append((s.replace("syn_", ""), DirectoryDataset(p, name=s.replace("syn_", ""))))
        print("待测  : %-10s %d 文件" % (groups[-1][0], len(groups[-1][1])))

    out = {}
    ref_sample = ref_ds.sample(min(100, len(ref_ds)))
    for key in BENCHES:
        if "hubert" in key:
            bench = BENCHMARKS[key](cluster_datasets=[ref_sample])
        else:
            bench = BENCHMARKS[key]()
        print("\n=== %s ===" % key, flush=True)
        ref = np.asarray(dist_of(bench, ref_ds))
        print("  ref  shape=%s" % (ref.shape,), flush=True)
        if ref.ndim > 1:
            print("  → 逐帧因子，跳过逐条化（仍由批次分覆盖）", flush=True)
            continue

        noise = []
        for nd in NOISE_DATASETS:
            try:
                noise.append(np.asarray(dist_of(bench, nd)))
            except Exception as e:
                print("  noise %s 跳过: %s" % (nd.name, e), flush=True)
        if not noise:
            raise SystemExit("没有噪声分布，无法归一")

        for gname, ds in groups:
            d = np.asarray(dist_of(bench, ds))
            if d.ndim > 1:
                print("  %-10s 逐帧分布 %s —— 不能按文件切，本因子留给批次分" % (gname, d.shape), flush=True)
                continue
            files = [os.path.basename(f) for f in ds.wavs]
            if d.shape[0] != len(files):
                raise SystemExit("%s: 分布 %d 条 vs 文件 %d 个" % (gname, d.shape[0], len(files)))
            dn = np.empty(d.shape[0])
            dr = np.empty(d.shape[0])
            for i in range(d.shape[0]):
                x = d[i]
                dr[i] = point_dist(x, ref)
                dn[i] = min(point_dist(x, n) for n in noise)
            sc = 100.0 * dn / (dr + dn)
            for f, s, r_, n_ in zip(files, sc, dr, dn):
                m = meta.get(f)
                if not m:
                    continue
                out.setdefault(m["tid"], dict(
                    tid=m["tid"], gid=m["gid"], kind=m["kind"], seed=m["seed"],
                    adv=m["adv"], cond=m["cond"], score={}, d_ref={}, d_noise={}))
                out[m["tid"]]["score"][key] = round(float(s), 3)
                out[m["tid"]]["d_ref"][key] = round(float(r_), 5)
                out[m["tid"]]["d_noise"][key] = round(float(n_), 5)
            print("  %-10s n=%3d  score p50=%6.2f  mean=%6.2f" % (gname, len(sc), np.median(sc), sc.mean()),
                  flush=True)

    for v in out.values():
        v["prosody"] = round(float(np.mean(list(v["score"].values()))), 3)
        v["n_factors"] = len(v["score"])
    json.dump(dict(n=len(out), takes=list(out.values())), open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出 %s（%d 条）" % (a.out, len(out)))


if __name__ == "__main__":
    main()
