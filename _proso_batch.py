# -*- coding: utf-8 -*-
"""对**一个目录**跑 TTSDS2 PROSODY，返回四个因子分与均值（官方口径，分布级）。

给回环当「打标签前的体检」用：先看这一批无标签 take 的韵律像不像真人，
不合格就别在上面叠 pitch/rate 了 —— 那是把修不好的东西再动一次。

用法：
    import _proso_batch
    _proso_batch.score_dir("G:/_setup/_mt_adv_ctl_2051")   -> dict
"""
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HOME", "E:/ttsds/hf")
os.environ.setdefault("TTSDS_CACHE_DIR", "E:/ttsds/cache")
os.environ.setdefault("TMPDIR", "E:/ttsds/tmp")
os.environ.setdefault("TEMP", "E:/ttsds/tmp")
os.environ.setdefault("TMP", "E:/ttsds/tmp")

REF_DIR = "E:/ttsds/data/ref_human"
FACTORS = ("pitch", "hubert_token_sr", "allosaurus_sr", "mpm")


def score_dir(path, factors=FACTORS, ref_dir=REF_DIR, verbose=False):
    """返回 {'pitch': 91.2, ..., 'prosody': 88.4, 'n': 文件数}。

    每个因子都是**官方 compute_score**（d_noise/(d_ref+d_noise)*100），
    只是把待测集换成了这个目录。分布走 ttsds 缓存，同一目录重跑是秒回。
    """
    import glob
    from ttsds.util.dataset import DirectoryDataset
    from ttsds.ttsds import BENCHMARKS, NOISE_DATASETS

    n = len(glob.glob(os.path.join(path, "*.wav")))
    if n == 0:
        return dict(prosody=None, n=0, why="目录里没有 wav")
    if not os.path.isdir(ref_dir):
        return dict(prosody=None, n=n, why="缺参考集 " + ref_dir)

    ref = DirectoryDataset(ref_dir, name="human")
    ref_sample = ref.sample(min(100, len(ref)))
    ds = DirectoryDataset(path, name=os.path.basename(path.rstrip("/\\")))

    out = dict(n=n)
    for key in factors:
        if key not in BENCHMARKS:
            continue
        try:
            if "hubert" in key:
                bench = BENCHMARKS[key](cluster_datasets=[ref_sample])
            else:
                bench = BENCHMARKS[key]()
            s, (noise_name, ref_name) = bench.compute_score(ds, [ref], NOISE_DATASETS)
            out[key] = round(float(s), 2)
            if verbose:
                print("  %-18s %6.2f  (noise=%s ref=%s)" % (key, s, noise_name, ref_name))
        except Exception as e:
            out[key] = None
            out.setdefault("err", {})[key] = str(e)[:80]
            if verbose:
                print("  %-18s 失败: %s" % (key, str(e)[:80]))
    vals = [v for k, v in out.items() if k in factors and isinstance(v, float)]
    out["prosody"] = round(sum(vals) / len(vals), 2) if vals else None
    return out


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(p)
        r = score_dir(p, verbose=True)
        print("  => PROSODY %.2f（%d 条）" % (r.get("prosody") or 0, r["n"]))
