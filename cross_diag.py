#!/usr/bin/env python
"""跨片失败的归因：先确认 embedding 在这批音频上到底有没有区分力。

只看准确率无法判断是「判据阈值不对」还是「声纹本身失效」。这里直接算
ref × test 的余弦矩阵，比较「同人」与「异人」的分布有没有分开：
  · 若同人余弦明显高于异人 → 声纹有效，问题在阈值/ref 数量
  · 若两组重合 → 声纹在这批音频上失效（音质 / 域不匹配），换阈值没用

顺带量音频质量（有效带宽 / 谱平坦度），因为 DVD 转录片的频响比现代
WEB-DL 窄，而声纹模型是在现代录音上训的。
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/voice_lib")

from sv_onnx import SV  # noqa: E402


def band_quality(path):
    """估有效带宽：累积能量到 99% 的频率，以及 4k 以上能量占比。"""
    import soundfile as sf
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    if len(x) < sr // 4:
        return 0.0, 0.0
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    c = np.cumsum(X) / (X.sum() + 1e-12)
    bw99 = float(f[np.searchsorted(c, 0.99)])
    hi = float(X[f > 4000].sum() / (X.sum() + 1e-12))
    return bw99, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default="crosscut/cross_lib.json")
    ap.add_argument("--eval", default="out/cross_eval.json")
    ap.add_argument("--cues", default="crosscut/cues/cues.json")
    a = ap.parse_args()

    lib = json.load(open(a.lib, encoding="utf-8"))
    refs = [(role, it["path"]) for role, v in lib.items() for it in v["neutral"]]
    rows = json.load(open(a.eval, encoding="utf-8"))
    cues = {os.path.basename(c["path"].replace("\\", "/")): c["path"].replace("\\", "/")
            for c in json.load(open(a.cues, encoding="utf-8"))}
    tests = [(r["gt"], cues[r["file"]]) for r in rows if r["file"] in cues]

    m = SV("r34")
    R = np.array([m.embed(p) for _, p in refs])
    T = np.array([m.embed(p) for _, p in tests])

    # 同人（ref 角色 == test 真值）与异人余弦
    same, diff = [], []
    for j, (gt, _) in enumerate(tests):
        for i, (role, _) in enumerate(refs):
            c = float(R[i] @ T[j])
            (same if role == gt else diff).append(c)
    same, diff = np.array(same), np.array(diff)
    print("同人余弦 n=%d  中位 %.3f  p25 %.3f  p75 %.3f" % (
        len(same), np.median(same), np.percentile(same, 25), np.percentile(same, 75)))
    print("异人余弦 n=%d  中位 %.3f  p25 %.3f  p75 %.3f" % (
        len(diff), np.median(diff), np.percentile(diff, 25), np.percentile(diff, 75)))

    # AUC：随机取一对同人 / 一对异人，同人余弦更高的概率
    rs = np.random.default_rng(0)
    a_s = rs.choice(same, 4000); a_d = rs.choice(diff, 4000)
    auc = float((a_s[:, None] > a_d[None, :]).mean())
    print("\n余弦 AUC = %.3f  （0.5 = 完全不可分，1.0 = 完美）" % auc)

    # 模板自检：ref 与同角色其他 ref 的余弦
    print("\n=== 模板自检：ref 之间同角色 / 跨角色 ===")
    sm, df_ = [], []
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            c = float(R[i] @ R[j])
            (sm if refs[i][0] == refs[j][0] else df_).append(c)
    if sm:
        print("  同角色 %.3f (n=%d)   跨角色 %.3f (n=%d)" % (
            np.median(sm), len(sm), np.median(df_) if df_ else 0, len(df_)))

    # 音频质量
    print("\n=== 音频质量（有效带宽 / 4k 以上能量占比）===")
    for tag, items in (("ref", refs), ("test", tests)):
        bw, hi = [], []
        for _, p in items:
            b, h = band_quality(p)
            bw.append(b); hi.append(h)
        print("  %-4s 带宽中位 %5.0f Hz   4k+ 占比中位 %.3f" % (
            tag, np.median(bw), np.median(hi)))

    print("\n=== 对照：城堡片（现代 WEB-DL）同类指标 ===")
    lib2 = json.load(open("G:/_setup/_emo_refs.json", encoding="utf-8"))
    cs = [(r, it["path"]) for r, v in lib2.items() for it in v.get("neutral", [])]
    if cs:
        bw, hi = [], []
        for _, p in cs:
            b, h = band_quality(p)
            bw.append(b); hi.append(h)
        print("  城堡 ref 带宽中位 %5.0f Hz   4k+ 占比中位 %.3f" % (np.median(bw), np.median(hi)))
        R2 = np.array([m.embed(p) for _, p in cs])
        print("  城堡 ref 同角色余弦中位 %.3f" % np.median([float(R2[i] @ R2[j])
              for i in range(len(cs)) for j in range(i + 1, len(cs))]))


if __name__ == "__main__":
    main()
