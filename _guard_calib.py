# -*- coding: utf-8 -*-
"""闸门阈值标定：用「同文本不同 take」的真实差异当噪声底。

思路
----
闸门是拿**候选 vs 同 seed 无标签对照**做差。要判「多大差别算异常」，必须知道
「同样的文本、同样的模型，只是换了 take」会产生多大的自然波动。

数据来源：`_mt_pick`（交付）、`_mt_adv_s*`（历史重生）、`_mt_adv_ctl_*`（对照）、
`_adv_tts`（标注实验）里同一个 uid 的多条 take。
对每个 uid 取所有 take，两两配对，算 HNR / 高频比 / DNSMOS-SIG 的差，
得到噪声底分布，再取 p95 作为阈值（即「正常波动里最大也就这么大」）。
"""
import os
import sys
import json
import glob
import argparse
import itertools
import warnings

import numpy as np

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _guard as G


def collect():
    """uid -> [wav...]，只收 55 个在做单元，避免把目录里所有文件都算进来。"""
    st = json.load(open(os.path.join(HERE, "_mt_adv_state.json"), encoding="utf-8"))
    keep = set(st["units"])
    idx = {}
    pats = ["_mt_pick", "_mt_adv_s*", "_mt_adv_ctl_*", "_adv_tts", "_mt_raw_s*"]
    for pat in pats:
        for d in glob.glob(os.path.join(HERE, pat)):
            if not os.path.isdir(d):
                continue
            for w in glob.glob(os.path.join(d, "*.wav")):
                uid = os.path.basename(w)[:-4].split("_")[0]
                if uid in keep:
                    idx.setdefault(uid, []).append(w)
    return {k: sorted(set(v)) for k, v in idx.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "_guard_calib.json"))
    ap.add_argument("--max-per-uid", type=int, default=4, help="每 uid 最多取几条，控制耗时")
    a = ap.parse_args()

    idx = collect()
    print("有 ≥2 条 take 的单元：%d" % sum(1 for v in idx.values() if len(v) >= 2), flush=True)

    rows = []
    n = 0
    for uid in sorted(idx):
        ws = idx[uid][: a.max_per_uid]
        if len(ws) < 2:
            continue
        feats = {}
        for w in ws:
            try:
                feats[w] = G.audio_guard(w, None)
            except Exception as e:
                print("  !! %s %s" % (os.path.basename(w), str(e)[:60]))
        keys = [w for w in ws if w in feats]
        for x, y in itertools.combinations(keys, 2):
            fx, fy = feats[x], feats[y]
            if None in (fx.get("hnr"), fy.get("hnr")):
                continue
            rows.append(dict(
                uid=uid, a=os.path.basename(x), b=os.path.basename(y),
                d_hnr=round(fy["hnr"] - fx["hnr"], 3),
                r_hf=round(fy["hf"] / max(fx["hf"], 1e-9), 3),
                d_sig=round((fy.get("dnsig") or 0) - (fx.get("dnsig") or 0), 3),
            ))
        n += 1
        if n % 5 == 0:
            print("  %d 个单元，%d 对" % (n, len(rows)), flush=True)

    if not rows:
        print("没有配对数据")
        return

    def rep(name, arr, absmode=True):
        v = np.abs(arr) if absmode else np.array(arr)
        v = np.sort(v)
        print("  %-8s n=%d  中位 %.3f  p90 %.3f  p95 %.3f  max %.3f"
              % (name, len(v), float(np.median(v)),
                 float(np.percentile(v, 90)), float(np.percentile(v, 95)), float(v[-1])))
        return float(np.percentile(v, 95))

    print("\n同文本不同 take 的自然波动（绝对值）：")
    d_hnr = [r["d_hnr"] for r in rows]
    r_hf = [r["r_hf"] for r in rows]
    d_sig = [r["d_sig"] for r in rows if r["d_sig"]]
    t_hnr = rep("ΔHNR dB", d_hnr)
    t_hf = rep("高频比倍", r_hf)
    t_sig = rep("ΔDNSIG", d_sig) if d_sig else None

    cur = dict(HNR_DROP_DB=getattr(G, "HNR_DROP_DB", None),
               HF_RATIO_MAX=getattr(G, "HF_RATIO_MAX", None),
               DNSIG_DROP=getattr(G, "DNSIG_DROP", None))
    print("\n当前阈值：%s" % cur)
    print("建议阈值（p95，且不低于当前值）：")
    print("  HNR_DROP_DB  = %.2f" % max(t_hnr, 2.0))
    print("  HF_RATIO_MAX = %.2f" % max(t_hf, 1.40))
    if t_sig:
        print("  DNSIG_DROP   = %.2f" % max(t_sig, 0.5))

    json.dump(dict(
        n_pairs=len(rows), n_units=n,
        thr=dict(hnr_drop_db=max(t_hnr, 2.0), hf_ratio_max=max(t_hf, 1.40),
                 dnsig_drop=(max(t_sig, 0.5) if t_sig else 0.5)),
        current=cur, rows=rows,
    ), open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写出 %s" % a.out)


if __name__ == "__main__":
    main()
