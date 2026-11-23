# -*- coding: utf-8 -*-
"""_segcheck_dlg.py —— 对白 239 条的句内音色一致性检测（第 4 道闸的候选实现）。

为什么单独写：`dialog_gate.py:308` 每条只算**一个整条 embedding**，
中段音色突变会被整条平均掉 —— 闸 2 结构上就看不见句内跳变。

判据分两层，不混用：
  ① 声纹层：段间 embedding 互比（沿用 ch123_segcheck 的量法，阈值不写死）
  ② 正交层：F0 跨度 / 相邻段电平差 / 段数 —— 语调波动也会压低相似度，
             只有「声纹低 + F0 跳」同时成立才算音色突变候选。

阈值来源：**本语料自身分布**（分位数），不拿 0.55 这种跨语料绝对值，
因为 11-11 全量实测：955 条里 med 0.393 / p25 0.302，用 0.55 会判 421 条 SEVERE（44%），
那不是「44% 都炸了」，是尺子不适用。

用法：
  SEGCHK_DIR=G:/_setup/_segchk_dlg \
  C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe _segcheck_dlg.py
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/_setup")
import ch123_segcheck as SC

OUT = "G:/_setup/_segcheck_dlg.json"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
AUD = "G:/_setup/_audio_ch123/out"


def main():
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l); plan[o["id"]] = o
    rows = []
    for k, (i, p) in enumerate(sorted(plan.items()), 1):
        f = os.path.join(AUD, i + ".wav")
        if not os.path.exists(f):
            continue
        r = SC.check(f, verbose=False)
        if not r:
            rows.append({"id": i, "who": p["who"], "emo": p["emo"], "n": 0,
                         "dur": None, "min_sim": None})
            continue
        rows.append({"id": i, "who": p["who"], "emo": p["emo"],
                     "voice": p["voice"], "text": p["text"],
                     "n": r["n"], "dur": round(sum(x["dur"] for x in r["info"]), 2),
                     "min_sim": round(min(r["rows"]), 3),
                     "mean_sim": round(float(np.mean(r["rows"])), 3),
                     "worst": r["worst"], "f0_span": round(r["f0_span"], 1),
                     "lvl_max": round(r["lvl_max"], 1),
                     "segs": [{"i": x["i"], "t0": round(x["t0"], 2), "t1": round(x["t1"], 2),
                               "dur": round(x["dur"], 2), "f0": round(x["f0"], 1),
                               "db": round(x["db"], 1), "sim": round(r["rows"][x["i"]], 3)}
                              for x in r["info"]]})
        if k % 40 == 0:
            print("  %d/239" % k, flush=True)

    ok = [x for x in rows if x.get("min_sim") is not None]
    ms = np.array([x["min_sim"] for x in ok])
    print("\n可分段 %d / %d 条（1 段无法互比 = %d）"
          % (len(ok), len(rows), len(rows) - len(ok)), flush=True)
    if len(ms):
        q = {k: round(float(np.percentile(ms, v)), 3)
             for k, v in (("p01", 1), ("p02", 2), ("p05", 5), ("p10", 10),
                          ("p25", 25), ("p50", 50), ("min", 0))}
        print("最低段相似度分布:", q, flush=True)
        print("  <0.55: %d 条 (%.1f%%)  |  <0.45: %d 条"
              % ((ms < 0.55).sum(), (ms < 0.55).mean() * 100, (ms < 0.45).sum()), flush=True)
        # 正交条件：声纹低 + F0 跳
        both = [x for x in ok if x["min_sim"] < 0.55 and x["f0_span"] > 40]
        print("  声纹低(<0.55) 且 F0 跨度 >40Hz: %d 条  ← 音色突变候选" % len(both), flush=True)
        long = [x for x in ok if x["dur"] >= 8.0]
        lms = np.array([x["min_sim"] for x in long]) if long else np.array([])
        print("  长句(≥8s) %d 条，其最低相似度 med %.3f / p10 %.3f"
              % (len(long), np.median(lms) if len(lms) else 0,
                 np.percentile(lms, 10) if len(lms) else 0), flush=True)
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n落盘", OUT, flush=True)


if __name__ == "__main__":
    main()
