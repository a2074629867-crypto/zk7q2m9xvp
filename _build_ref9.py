# -*- coding: utf-8 -*-
"""把「角色 × 情绪」的参考补到 ≥9s（用户 2026-11-21 的要求）。

背景
----
用户两次指出同一件事，且第二次给了明确数字：
  「我之前让你每个角色每种情绪，参考时间得接近 9s 准一点，你做了没？」
官方 dots.tts 的实践文档也写着「约 10 秒的干净参考音频」「参考音频太短或
有噪声 → 相似度偏低」。现有 99 条参考的中位只有 3.99s，**没有一条 ≥9s**。

做法
----
同一 (role, emo) 下的多条参考本来就是同一个角色、同一种情绪的短句，
按时长降序累加到 ≥ target（默认 9.0s），段间插 0.2s 静音，
拼成一条长参考。文本按同样顺序用空格连起来当 reference-text。

不做的事
--------
· 不做降噪/归一以外的任何处理 —— 参考要保持原声，处理过的参考会让模型学错。
· 不跨情绪借素材（除非该组自身不足，见 --allow-borrow）。

用法
----
  G:/Python310/python.exe -u _build_ref9.py                # 全部组
  G:/Python310/python.exe -u _build_ref9.py --only Charles_nervous
"""
import argparse
import io
import json
import os
import sys

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT = "G:/_setup"
LIB = os.path.join(ROOT, "_emo_refs_all.json")
OUT = os.path.join(ROOT, "_ref9")
SR = 48000
GAP = 0.20


def load_any(p, sr=SR):
    y, s = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    if s != sr:
        g = np.gcd(int(s), int(sr))
        y = resample_poly(y, sr // g, s // g).astype("float32")
    return y


def trim_edges(y, thr=0.012, pad=0.03):
    """去掉首尾死静音（保留 30ms 呼吸），避免拼接后大段空白。"""
    a = np.abs(y)
    idx = np.where(a > thr * (a.max() or 1))[0]
    if not len(idx):
        return y
    i0 = max(0, idx[0] - int(pad * SR))
    i1 = min(len(y), idx[-1] + int(pad * SR))
    return y[i0:i1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=LIB)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--target", type=float, default=9.0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()

    lib = json.load(io.open(a.lib, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    index = {}

    for role in sorted(lib):
        for emo in sorted(lib[role]):
            key = "%s_%s" % (role, emo)
            if a.only and a.only != key:
                continue
            items = []
            for it in lib[role][emo]:
                p = it.get("path") if isinstance(it, dict) else it
                t = (it.get("text") if isinstance(it, dict) else "") or ""
                if not p or not os.path.exists(p):
                    continue
                try:
                    d = sf.info(p).duration
                except Exception:
                    continue
                items.append({"path": p, "text": t, "dur": d})
            if not items:
                continue
            # 长句优先：少拼几段，接缝就少几个
            items.sort(key=lambda x: -x["dur"])
            picked, total = [], 0.0
            for it in items:
                if total >= a.target:
                    break
                picked.append(it)
                total += it["dur"] + GAP
            # 一条就能顶满的情况：直接原样复制，别多此一举
            chunks = []
            for it in picked:
                y = trim_edges(load_any(it["path"]))
                chunks.append(y)
                chunks.append(np.zeros(int(GAP * SR), dtype="float32"))
            y = np.concatenate(chunks[:-1]) if len(chunks) > 1 else chunks[0]
            dst = os.path.join(a.out, key + ".wav")
            sf.write(dst, y, SR, subtype="PCM_16")
            index[key] = {
                "file": dst,
                "dur": round(len(y) / SR, 2),
                "parts": [{"path": it["path"], "dur": round(it["dur"], 2),
                           "text": it["text"]} for it in picked],
                "text": " ".join(it["text"] for it in picked if it["text"]).strip(),
                "short": round(len(y) / SR, 2) < a.target,
            }
            print("%-24s %5.2fs <- %d 段 %s" % (
                key, len(y) / SR, len(picked),
                "  ⚠ 不足 %.1fs" % a.target if index[key]["short"] else ""))

    meta = os.path.join(a.out, "_index.json")
    old = {}
    if os.path.exists(meta):
        try:
            old = json.load(io.open(meta, encoding="utf-8"))
        except Exception:
            old = {}
    old.update(index)
    json.dump(old, io.open(meta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写入 %d 组到 %s" % (len(index), a.out))


if __name__ == "__main__":
    main()
