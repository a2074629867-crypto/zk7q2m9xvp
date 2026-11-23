# -*- coding: utf-8 -*-
"""cast_from_seed.py —— 用「已确认为某人说的几条 cue」当种子，在全片里扩出这个人的所有可用句。

为什么需要它
------------
无监督聚类对同一部片里的**同龄儿童**分不开（实测 Rambow 751 条里 635 条全挤一簇，
因为声纹模型主要在成人数据上训练）。所以流程改成：
    读字幕文本 + 时间点 → 人工确认 5–10 条「这个人说的」→ 种子扩增
这比盲聚类可靠一个量级：种子本身可复核，扩出来的每条都能回看原文。

用法
----
    python cast_from_seed.py --cues G:/MOVIE_DL/_cues_rambow \\
        --seeds 513.5,518.6,525.6,529.2,535.2,539.7,547.0,552.9,557.8 \\
        --out G:/MOVIE_DL/_cast_leecarter --f0min 140 --f0max 260 --top 40

判据（都踩过坑）
----------------
  - 种子 ≥4 条才能算质心；<4 条留一法没意义
  - 留一法：拿掉一条，用剩 8 条算质心，看这条的余弦是否仍 >0.5 → 种子内部一致
  - multi=True（字幕 `-` 混人）与 sfx=True（`(...)` 音效）一律不进候选
  - F0 硬夹：跨声部的不可能是同一个人，即使余弦高也是模型被音色骗了
  - 阈值默认取「种子内部最小留一法余弦 − 0.10」，不拍脑袋
"""
import argparse
import json
import os
import shutil

import sys

import numpy as np

sys.path.insert(0, "G:/_setup")

CACHE = "_emb_cache.npz"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cues", required=True)
    ap.add_argument("--seeds", required=True, help="逗号分隔的 t0（秒），要能对上 cues.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="r34")
    ap.add_argument("--f0min", type=float, default=0.0)
    ap.add_argument("--f0max", type=float, default=999.0)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--thr", type=float, default=0.0, help="指定阈值；0=自动（种子最小留一 -0.10）")
    ap.add_argument("--copy", action="store_true", help="把候选 wav 复制到 out")
    a = ap.parse_args()

    cj = os.path.join(a.cues, "cues.json")
    d = json.load(open(cj, encoding="utf-8"))
    cs = d["cues"] if isinstance(d, dict) and "cues" in d else d
    print("cue %d 条" % len(cs), flush=True)

    # ---- embedding（带缓存，重跑不重算）----
    files = [os.path.basename(c["path"]) for c in cs]
    cache_p = os.path.join(a.cues, CACHE)
    emb = None
    if os.path.exists(cache_p):
        z = np.load(cache_p, allow_pickle=True)
        if list(z["files"]) == files:
            emb = z["E"]
            print("复用缓存 %s" % cache_p, flush=True)
    if emb is None:
        from sv_onnx import SV
        sv = SV(name=a.model)
        rows = []
        for i, c in enumerate(cs, 1):
            rows.append(sv.embed(c["path"]))
            if i % 100 == 0:
                print("  提特征 %d/%d" % (i, len(cs)), flush=True)
        emb = np.array(rows, dtype=np.float32)
        np.savez(cache_p, E=emb, files=np.array(files, dtype=object))
        print("缓存 -> %s" % cache_p, flush=True)
    E = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)

    # ---- 种子定位 ----
    # 先按 t0 精确匹配（±0.15s，字幕切条时用）；匹配不上就退化成「这个时间点落在
    # 哪条 cue 里」（ASR 切条边界和字幕不同，但时间点本身是对的）。两者都没有才报错。
    seeds = [float(x) for x in a.seeds.split(",") if x.strip()]
    sidx = []
    for t in seeds:
        cand = [i for i, c in enumerate(cs) if abs(c["t0"] - t) <= 0.15]
        how = "t0"
        if not cand:
            cand = [i for i, c in enumerate(cs) if c["t0"] <= t <= c["t1"]]
            how = "内"
        if not cand:
            cand = [i for i, c in enumerate(cs) if abs(c["t0"] - t) <= 1.5]
            how = "近"
        if not cand:
            print("!! 种子 %.1fs 找不到对应 cue" % t, flush=True)
            continue
        i = min(cand, key=lambda j: abs(cs[j]["t0"] - t))
        print("   种子 %.1fs -> #%d (%s) %.1fs %s" % (
            t, i, how, cs[i]["t0"], cs[i]["text"][:48]), flush=True)
        sidx.append(i)
    if len(sidx) < 4:
        raise SystemExit("种子不足 4 条（找到 %d），先回字幕确认" % len(sidx))
    print("种子 %d 条：%s" % (len(sidx), [cs[i]["t0"] for i in sidx]), flush=True)

    S = E[sidx]
    cen = S.mean(0)
    cen /= np.linalg.norm(cen) + 1e-9

    # ---- 留一法验种子内部一致性 ----
    loo = []
    for k in range(len(sidx)):
        rest = np.delete(S, k, axis=0)
        c2 = rest.mean(0)
        c2 /= np.linalg.norm(c2) + 1e-9
        loo.append(float(S[k] @ c2))
    print("\n种子留一法余弦：min %.3f / 中位 %.3f / max %.3f" % (
        min(loo), float(np.median(loo)), max(loo)), flush=True)
    if min(loo) < 0.35:
        print("!! 有种子与其余不合（<0.35）——大概率选错了句子，回字幕复查", flush=True)

    thr = a.thr if a.thr > 0 else max(0.30, min(loo) - 0.10)
    print("扩增阈值 %.3f" % thr, flush=True)

    sims = E @ cen
    order = np.argsort(-sims)

    # ---- 硬检查 + 排序 ----
    picked, rejected = [], {"multi": 0, "sfx": 0, "dur": 0, "f0": 0, "seed": 0}
    seed_set = set(sidx)
    for k in order:
        c = cs[k]
        if k in seed_set:
            continue
        f0 = c.get("f0") or 0.0
        if c.get("multi"):
            rejected["multi"] += 1
            continue
        if c.get("sfx"):
            rejected["sfx"] += 1
            continue
        if c["dur"] < 1.0:
            rejected["dur"] += 1
            continue
        if f0 and not (a.f0min <= f0 <= a.f0max):
            rejected["f0"] += 1
            continue
        if sims[k] < thr:
            break
        picked.append(k)
        if len(picked) >= a.top:
            break

    print("候选 %d 条（跳过：混人 %d / 音效 %d / 太短 %d / F0越界 %d）" % (
        len(picked), rejected["multi"], rejected["sfx"], rejected["dur"], rejected["f0"]), flush=True)

    os.makedirs(a.out, exist_ok=True)
    rows = []
    for k in picked:
        c = cs[k]
        rec = {"t0": c["t0"], "dur": c["dur"], "sim": round(float(sims[k]), 3),
               "f0": c.get("f0"), "text": c["text"], "src": c["path"]}
        rows.append(rec)
        print("  %.3f f0=%-5s %7.1f %s" % (rec["sim"], rec["f0"], rec["t0"], c["text"][:78]), flush=True)
        if a.copy:
            shutil.copy2(c["path"], os.path.join(a.out, os.path.basename(c["path"])))

    # 种子也写进去，建库要带上
    for k in sidx:
        c = cs[k]
        rows.append({"t0": c["t0"], "dur": c["dur"], "sim": 1.0,
                     "f0": c.get("f0"), "text": c["text"], "src": c["path"], "seed": True})
        if a.copy:
            shutil.copy2(c["path"], os.path.join(a.out, os.path.basename(c["path"])))

    meta = {"cues": a.cues, "seeds": [cs[i]["t0"] for i in sidx],
            "loo": [round(x, 3) for x in loo], "thr": round(thr, 3),
            "f0_range": [a.f0min, a.f0max], "rows": rows}
    json.dump(meta, open(os.path.join(a.out, "cast.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n-> %s/cast.json（%d 条，含 %d 条种子）" % (a.out, len(rows), len(sidx)), flush=True)


if __name__ == "__main__":
    main()
