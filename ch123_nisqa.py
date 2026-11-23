# -*- coding: utf-8 -*-
"""NISQA 批量打分（MOS + Noisiness / Coloration / Discontinuity / Loudness）。

用法:
    G:/Python310/python.exe ch123_nisqa.py <data_dir> [model]
默认模型 D:/eval_models/nisqa/nisqa_tts.tar（专为 TTS 合成音训练）。

为什么要它: DNSMOS 只有 SIG/BAK/OVRL 三个维度，没有「断流/咔哒」维度。
NISQA 的 **Discontinuity** 正是测这种（拼接缝、硬切、抽吸），
我们的 L078 拼接、L083 尾音截断都属这一类。
"""
import os
import sys

import torch

# NISQA 库内部用 torch.load 且没传 weights_only；torch>=2.6 默认 True 会炸
_orig_load = torch.load


def _patched(*a, **k):
    k.setdefault("weights_only", False)
    return _orig_load(*a, **k)


torch.load = _patched

from nisqa.NISQA_model import nisqaModel  # noqa: E402

MODEL = "D:/eval_models/nisqa/nisqa_tts.tar"


def run(data_dir, model=MODEL, out_dir=None):
    out_dir = out_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "_nisqa_out")
    os.makedirs(out_dir, exist_ok=True)
    args = {
        "mode": "predict_dir",
        "pretrained_model": model,
        "data_dir": data_dir,
        "output_dir": out_dir,
        "tr_bs_val": 8,
        "tr_num_workers": 0,
        "tr_parallel": False,
        "ms_channel": None,
        "dim": True,
        "tr_verbose": "noleave",
    }
    m = nisqaModel(args)
    df = m.predict()
    return df


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "ch123_clean"
    model = sys.argv[2] if len(sys.argv) > 2 else MODEL
    df = run(data_dir, model)

    cols = [c for c in ("deg", "mos_pred", "noi_pred", "col_pred", "dis_pred", "loud_pred") if c in df.columns]
    d = df[cols].copy()
    d = d.sort_values("mos_pred")
    print("\n%-12s %6s %6s %6s %6s %6s" % ("file", "MOS", "NOI", "COL", "DIS", "LOUD"))
    for _, r in d.iterrows():
        print("%-12s %6.2f %6.2f %6.2f %6.2f %6.2f" % (
            str(r["deg"])[:12],
            r.get("mos_pred", 0), r.get("noi_pred", 0), r.get("col_pred", 0),
            r.get("dis_pred", 0), r.get("loud_pred", 0)))
    print("\nMOS 均值 %.3f  中位 %.3f  min %.2f (%s)" % (
        d["mos_pred"].mean(), d["mos_pred"].median(),
        d["mos_pred"].min(), d.iloc[0]["deg"]))


if __name__ == "__main__":
    main()
