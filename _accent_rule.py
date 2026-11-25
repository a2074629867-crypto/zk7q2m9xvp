# -*- coding: utf-8 -*-
"""Stage B：把「明显错的重读」抓出来。

判据只做一件事：**该句的音高重音峰，落在了一个修饰语 / 功能词上，而且压过了它的中心词。**
为什么不用「每个词都打分」：那样又会退回"全库平均"的老路，把句子本来的起伏当噪声。
这里只问一个布尔问题 —— 这一句的重音峰，语法上该不该是它。

规则：
  R1 重音峰压在修饰语上：peak.dep ∈ MODSET 且 prom(peak) − prom(head) ≥ T1
  R2 重音峰落在功能词上：peak.pos ∈ FUNC（det/adp/aux/pron/cc/sconj/part）
  （peak = 该句 prom 最大的词；prom = 词内 F0 中位 − 全句中位，半音）

用法：
  G:/Python310/python.exe -u _accent_rule.py --a _accent_feat_old.jsonl --b _accent_feat_new.jsonl --t1 3.0
"""
import argparse
import json
import os
from collections import Counter

ROOT = r"G:/_setup"

MODSET = {"advmod", "amod", "aux", "auxpass", "det", "neg", "nummod", "poss",
          "case", "mark", "cc", "npadvmod", "compound", "prt", "quantmod",
          "predet", "expl", "preconj"}
FUNC = {"ADP", "DET", "CCONJ", "SCONJ", "AUX", "PRON", "PART", "PUNCT", "NUM"}
CONTENT = {"NOUN", "VERB", "ADJ", "ADV", "PROPN"}


def load(p):
    out = {}
    p = p if os.path.isabs(p) else os.path.join(ROOT, p)
    for ln in open(p, encoding="utf-8"):
        r = json.loads(ln)
        out[r["id"]] = r
    return out


USE_CONS = False   # True 时只认「双估计器一致」的词（见 _accent_fix_f0.py）
USE_CONS90 = False # True 时用 cons90（词内 F0 高点的一致值）—— 峰高判据的正确输入


def _val(w):
    """取该词的 F0 代表值。
    USE_CONS90：只接受双估计器一致且 p90 那一档也一致的 cons90（峰高用，§5.1）
    USE_CONS  ：接受 p50 一致值 cons
    默认      ：单估计器 p50（**不可用于判决**，保留只为复现旧结果）
    """
    if USE_CONS90:
        v = w.get("cons90")
        return None if v is None else float(v)
    if USE_CONS:
        if not w.get("ok") or w.get("cons") is None:
            return None
        return float(w["cons"])
    return w["p50"]


def analyse(rec, t1):
    """返回 (规则命中列表, 该句 peak 信息, 逐词 prom 表)。"""
    med = rec["med"]
    rows = []
    for w in rec["words"]:
        v = _val(w)
        if v is None or w["nfr"] < 4 or not w["pos"]:
            continue
        rows.append(dict(w=w["w"], pos=w["pos"], dep=w["dep"], head=w["head"],
                         i=w["i"], hi=w["hi"], prom=round(v - med, 2)))
    if not rows:
        return [], None, rows
    idx = {r["i"]: r for r in rows}
    content = [r for r in rows if r["pos"] in CONTENT]
    if not content:
        return [], None, rows
    peak = max(content, key=lambda r: r["prom"])
    head = idx.get(peak["hi"])
    info = dict(peak=peak["w"], pos=peak["pos"], dep=peak["dep"],
                prom=peak["prom"],
                head=(head["w"] if head else peak["head"]),
                head_prom=(head["prom"] if head else None),
                delta=(round(peak["prom"] - head["prom"], 2) if head else None))
    hits = []
    if peak["pos"] in FUNC:
        hits.append(("R2", dict(info)))
    elif peak["dep"] in MODSET and head is not None and head["pos"] in CONTENT:
        if peak["prom"] - head["prom"] >= t1:
            hits.append(("R1", dict(info)))
    # 任意修饰语压过中心词（排序用，不单独判死）
    worst = None
    for r in rows:
        if r is peak or r["dep"] not in MODSET:
            continue
        h = idx.get(r["hi"])
        if h is None or h["pos"] not in CONTENT:
            continue
        d = r["prom"] - h["prom"]
        if d >= t1 and (worst is None or d > worst[2]):
            worst = (r["w"], h["w"], round(d, 2))
    info["worst_extra"] = worst
    return hits, info, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="_accent_feat_old.jsonl")
    ap.add_argument("--b", default="_accent_feat_new.jsonl")
    ap.add_argument("--t1", type=float, default=3.0)
    ap.add_argument("--json", default="_accent_viol.json")
    ap.add_argument("--cons", action="store_true",
                    help="只用双估计器一致的词（输入需先过 _accent_fix_f0.py）")
    ap.add_argument("--cons90", action="store_true",
                    help="峰高用 cons90（词内 F0 高点的一致值）；这是 §5.1 的正确输入")
    a = ap.parse_args()
    global USE_CONS, USE_CONS90
    USE_CONS = a.cons
    USE_CONS90 = a.cons90
    if USE_CONS90:
        print("口径：cons90（p90 双估计器一致），Δ>14st 的词已在前置被丢弃")

    A = load(a.a)
    B = load(a.b)
    common = sorted(set(A) & set(B))
    print("A(验收) %d 条 / B(三档) %d 条 / 共同 %d 条   T1=%.1f st"
          % (len(A), len(B), len(common), a.t1))

    res = {}
    for tag, D in (("old", A), ("new", B)):
        nr1 = nr2 = 0
        per = {}
        for sid in common:
            hits, info, rows = analyse(D[sid], a.t1)
            if hits:
                per[sid] = dict(hits=[h[0] for h in hits], info=info, text=D[sid]["text"])
                for h in hits:
                    if h[0] == "R1":
                        nr1 += 1
                    else:
                        nr2 += 1
        res[tag] = dict(n=len(common), r1=nr1, r2=nr2, per=per)
        print("  %-4s R1(重音压在修饰语) %3d 条 / R2(重音落在功能词) %3d 条  → 合计 %d 条"
              % (tag, nr1, nr2, nr1 + nr2))

    both = set(res["old"]["per"]) & set(res["new"]["per"])
    only_old = set(res["old"]["per"]) - set(res["new"]["per"])
    only_new = set(res["new"]["per"]) - set(res["old"]["per"])
    print("\n两版都命中 %d 条 / 只有验收版命中 %d 条 / 只有三档版命中 %d 条"
          % (len(both), len(only_old), len(only_new)))

    print("\n只有验收版命中的前 15 条（三档版已修好）：")
    rank = sorted(only_old, key=lambda s: -abs(res["old"]["per"][s]["info"].get("delta") or 0))
    for sid in rank[:15]:
        i = res["old"]["per"][sid]["info"]
        print("  %s  peak=%-12s(%s/%s) prom%+.1fst  head=%-10s %+.1fst  Δ%+.1f"
              % (sid, i["peak"], i["pos"], i["dep"], i["prom"],
                 i["head"], i["head_prom"] or 0, i["delta"] or 0))

    print("\n三档版新出现的（前 8 条，需要听）：")
    for sid in list(only_new)[:8]:
        i = res["new"]["per"][sid]["info"]
        print("  %s  peak=%-12s(%s/%s) prom%+.1fst  head=%-10s  Δ%+.1f"
              % (sid, i["peak"], i["pos"], i["dep"], i["prom"], i["head"], i["delta"] or 0))

    if "c2_0191" in common:
        print("\n--- c2_0191 ---")
        for tag in ("old", "new"):
            h, i, rows = analyse((A if tag == "old" else B)["c2_0191"], a.t1)
            print("  %-3s peak=%s(%s/%s) prom%+.1fst head=%s(%+.1fst) Δ%+.1f hits=%s"
                  % (tag, i["peak"], i["pos"], i["dep"], i["prom"], i["head"],
                     i["head_prom"] or 0, i["delta"] or 0, [x[0] for x in h]))

    out = {"t1": a.t1, "common": len(common),
           "old": {"r1": res["old"]["r1"], "r2": res["old"]["r2"],
                   "ids": sorted(res["old"]["per"])},
           "new": {"r1": res["new"]["r1"], "r2": res["new"]["r2"],
                   "ids": sorted(res["new"]["per"])},
           "both": sorted(both), "only_old": sorted(only_old),
           "only_new": sorted(only_new),
           "detail_old": res["old"]["per"], "detail_new": res["new"]["per"]}
    p = a.json if os.path.isabs(a.json) else os.path.join(ROOT, a.json)
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写 " + p)


if __name__ == "__main__":
    main()
