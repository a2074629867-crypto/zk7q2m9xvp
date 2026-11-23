#!/usr/bin/env python
"""通用性验证：同一部片、两个不同编码源，切出来的 cue 应判成同一个人。

为什么用这个口径：旧片（老 mkv）与新的 WEB-DL 1080p 是同一版本，403 条字幕
时间轴逐条一致。于是可以按文件名把两边配对，逐对比较
  ① 声纹 embedding 余弦 —— 片源/编码差异会不会把音色带偏
  ② 1-NN + Z-norm 判定角色 —— 判决是否稳定

这一层测的是「换片源不换人」；跨片冷启动是另一回事（要建新 ref 库），
不在这里混为一谈。

用法：
  G:/Python310/python.exe verify_portable.py --old castle_cues --new newcut/cues --n 100
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/voice_lib")

from chain_check import EmoVoice  # noqa: E402


def _times(fname):
    """从 c171_1941.6_1945.3.wav / c000_00021.2_00025.3.wav 取 (t0, t1)。

    两代命名不完全一样：`%07.1f` 对 21.2 会补成 00021.2，对 1941.6 保持 1941.6。
    所以不能按文件名字符串配对，只能解析出时间再配。
    """
    stem = fname[:-4]
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    try:
        return float(parts[-2]), float(parts[-1])
    except ValueError:
        return None


def pair_files(old_dir, new_dir, tol=0.11):
    """按时间轴配对（同一 cue 的 t0 应完全相同，留 0.11s 容差防浮点）。"""
    olds = [f for f in os.listdir(old_dir) if f.endswith(".wav")]
    news = [f for f in os.listdir(new_dir) if f.endswith(".wav")]
    newmap = {}
    for f in news:
        t = _times(f)
        if t:
            newmap.setdefault(round(t[0], 1), f)
    pairs = []
    for f in olds:
        t = _times(f)
        if not t:
            continue
        n = newmap.get(round(t[0], 1))
        if n:
            pairs.append((f, n))
    return pairs, len(olds), len(news)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="castle_cues")
    ap.add_argument("--new", default="newcut/cues")
    ap.add_argument("--n", type=int, default=80, help="抽多少对（0=全部）")
    ap.add_argument("--out", default="out/verify_portable.json")
    a = ap.parse_args()

    common, no, nn = pair_files(a.old, a.new)
    print("旧片 %d 条 / 新片 %d 条 / 配对成功 %d 条" % (no, nn, len(common)))
    if not common:
        sys.exit("没有可配对的音频，检查 --old/--new")

    # 均匀抽样，避免只取片头
    if a.n and len(common) > a.n:
        idx = np.linspace(0, len(common) - 1, a.n).astype(int)
        sample = [common[i] for i in idx]
    else:
        sample = common

    ev = EmoVoice(model="r34")
    print("模板 %d 条，开始逐对比较 %d 对 …" % (len(ev.keys), len(sample)), flush=True)

    rows = []
    for i, (fo, fn) in enumerate(sample):
        po = os.path.join(a.old, fo)
        pn = os.path.join(a.new, fn)
        try:
            eo, en = ev.m.embed(po), ev.m.embed(pn)
        except Exception as e:
            rows.append({"file": fo, "error": str(e)[:80]})
            continue
        cos = float(np.dot(eo, en))
        ro, rn = ev.check(po), ev.check(pn)
        rows.append({
            "file": fo, "new_file": fn,
            "cos": round(cos, 4),
            "old_role": ro["role"], "old_emo": ro["emo"], "old_z1": ro["z1"],
            "new_role": rn["role"], "new_emo": rn["emo"], "new_z1": rn["z1"],
            "role_same": ro["role"] == rn["role"],
            "emo_same": (ro["role"], ro["emo"]) == (rn["role"], rn["emo"]),
            "old_rz": round(abs(ro["role_z"]), 3), "new_rz": round(abs(rn["role_z"]), 3),
        })
        if (i + 1) % 20 == 0:
            print("  %d/%d" % (i + 1, len(sample)), flush=True)

    ok = [r for r in rows if "error" not in r]
    print("\n=== 结果 n=%d（失败 %d）===" % (len(ok), len(rows) - len(ok)))
    cos = np.array([r["cos"] for r in ok])
    print("embedding 余弦: min %.4f p10 %.4f p25 %.4f 中位 %.4f" % (
        cos.min(), np.percentile(cos, 10), np.percentile(cos, 25), np.median(cos)))
    print("  <0.90 的: %d 条    <0.95 的: %d 条" % (int((cos < 0.90).sum()), int((cos < 0.95).sum())))

    n_role = sum(r["role_same"] for r in ok)
    n_emo = sum(r["emo_same"] for r in ok)
    print("角色一致: %d/%d = %.0f%%" % (n_role, len(ok), 100 * n_role / len(ok)))
    print("角色+情绪档一致: %d/%d = %.0f%%" % (n_emo, len(ok), 100 * n_emo / len(ok)))

    print("\n角色分布  旧片 %s / 新片 %s" % (
        dict(collections.Counter(r["old_role"] for r in ok)),
        dict(collections.Counter(r["new_role"] for r in ok))))

    flips = [r for r in ok if not r["role_same"]]
    if flips:
        print("\n=== 角色翻转 %d 条 ===" % len(flips))
        print("%-26s %6s %-8s %-8s %6s %6s" % ("file", "cos", "旧", "新", "旧rz", "新rz"))
        for r in flips:
            print("%-26s %6.3f %-8s %-8s %6.2f %6.2f" % (
                r["file"], r["cos"], r["old_role"], r["new_role"], r["old_rz"], r["new_rz"]))

    # 低余弦的单独列，这些是片源差异导致的音色漂移
    low = sorted([r for r in ok if r["cos"] < 0.90], key=lambda r: r["cos"])
    if low:
        print("\n=== 余弦 <0.90（片源音色漂移）%d 条 ===" % len(low))
        for r in low[:12]:
            print("  %-26s cos %.3f  旧 %s/%s  新 %s/%s" % (
                r["file"], r["cos"], r["old_role"], r["old_emo"], r["new_role"], r["new_emo"]))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写 ->", a.out)


if __name__ == "__main__":
    main()
