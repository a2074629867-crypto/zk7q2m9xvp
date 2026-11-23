# -*- coding: utf-8 -*-
"""TTSDS2 PROSODY 因子：真人参考 vs 我们各组。

只跑 prosody 的四个 benchmark（mpm / pitch / hubert_token_sr / allosaurus_sr），
其余 category 的权重设 0 且不加载。

用法：
  python _ttsds_run.py --sets syn_delivered,syn_cand,syn_ctl --bench pitch
  python _ttsds_run.py --sets syn_delivered --bench mpm,pitch,hubert_token_sr,allosaurus_sr
"""
import argparse
import os
import sys

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HOME", "E:/ttsds/hf")
os.environ.setdefault("TTSDS_CACHE_DIR", "E:/ttsds/cache")
os.environ.setdefault("TMPDIR", "E:/ttsds/tmp")
os.environ.setdefault("TEMP", "E:/ttsds/tmp")
os.environ.setdefault("TMP", "E:/ttsds/tmp")

import pandas as pd

from ttsds import BenchmarkSuite
from ttsds.util.dataset import DirectoryDataset
from ttsds.benchmarks.benchmark import BenchmarkCategory
from ttsds.ttsds import BENCHMARKS

BASE = "E:/ttsds/data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="syn_delivered",
                    help="逗号分隔，E:/ttsds/data 下的目录名")
    ap.add_argument("--ref", default="ref_human")
    ap.add_argument("--bench", default="pitch")
    ap.add_argument("--out", default="E:/ttsds/results.csv")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    refs = [DirectoryDataset(os.path.join(BASE, a.ref), name=a.ref.replace("ref_", ""))]
    ds = []
    for s in a.sets.split(","):
        p = os.path.join(BASE, s)
        if not os.path.isdir(p):
            raise SystemExit("目录不存在: " + p)
        ds.append(DirectoryDataset(p, name=s.replace("syn_", "")))
    bench = {k: BENCHMARKS[k] for k in a.bench.split(",") if k in BENCHMARKS}
    missing = [k for k in a.bench.split(",") if k not in BENCHMARKS]
    if missing:
        raise SystemExit("未知 benchmark: %s（可用：%s）" % (missing, list(BENCHMARKS)))

    print("参考集 : %s (%d 个文件)" % (a.ref, len(refs[0])))
    print("待测集 : %s" % ", ".join("%s(%d)" % (d.name, len(d)) for d in ds))
    print("因子   : %s" % ", ".join(bench))
    print()

    suite = BenchmarkSuite(
        datasets=ds,
        reference_datasets=refs,
        benchmarks=bench,
        category_weights={
            BenchmarkCategory.PROSODY: 1.0,
            BenchmarkCategory.SPEAKER: 0.0,
            BenchmarkCategory.INTELLIGIBILITY: 0.0,
            BenchmarkCategory.GENERIC: 0.0,
            BenchmarkCategory.ENVIRONMENT: 0.0,
        },
        skip_errors=True,
        write_to_file=a.out,
        cache_dir="E:/ttsds/cache",
        device="cpu",
        include_environment=False,
        n_workers=a.workers,
    )
    suite.run()

    df = suite.database
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print()
    print("=== 逐 benchmark ===")
    print(df[["benchmark_name", "dataset", "score"]].to_string(index=False))
    print()
    print("=== 聚合（PROSODY）===")
    agg = suite.get_aggregated_results()
    print(agg)
    try:
        agg.to_csv("E:/ttsds/results_prosody_agg.csv", index=False)
    except Exception as e:
        print("聚合结果写盘失败:", e)


if __name__ == "__main__":
    main()
