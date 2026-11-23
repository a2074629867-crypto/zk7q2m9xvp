# -*- coding: utf-8 -*-
"""两个 LLM 的盲标交叉验证 + 与声学实测对账。

输入：_adv_task/out_ds_p*.json + out_hy_p*.json + key.json
输出：
  - 一致率（都选同一词 / 都 none / 分歧）
  - 与 _adv_all.json（声学 rel）对账：LLM 说该慢的，实际慢了吗
"""
import argparse
import glob
import json
import os
import re
import statistics
from collections import Counter, defaultdict

ROOT = "G:/_setup"
TASK = os.path.join(ROOT, "_adv_task")
PLAN = "B:/mt-tts/data/plan/mt_plan3b.json"


def load(prefix):
    out = {}
    for f in sorted(glob.glob(os.path.join(TASK, "out_%s_p*.json" % prefix))):
        t = open(f, encoding="utf-8").read()
        m = re.search(r"\[.*\]", t, re.S)
        if not m:
            print("  !! %s 无 JSON 数组" % os.path.basename(f))
            continue
        try:
            arr = json.loads(m.group(0))
        except Exception as e:
            print("  !! %s 解析失败 %s" % (os.path.basename(f), e))
            continue
        for r in arr:
            if "id" not in r:
                continue
            out[str(r["id"])] = str(r.get("pick", "")).strip() or "none"
        print("  %-22s %d 条" % (os.path.basename(f), len(arr)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--acoustic", default=os.path.join(ROOT, "_adv_all.json"))
    ap.add_argument("--json", default=os.path.join(ROOT, "_adv_final.json"))
    a = ap.parse_args()

    key = json.load(open(os.path.join(TASK, "key.json"), encoding="utf-8"))
    print("=== 载入 ===")
    ds = load("ds")
    hy = load("hy")
    ids = sorted(set(ds) | set(hy))
    print("合并 %d 条（ds %d / hy %d）" % (len(ids), len(ds), len(hy)))

    miss = [i for i in sorted(key) if i not in ds or i not in hy]
    if miss:
        print("!! 缺失 %d 条：%s" % (len(miss), ",".join(miss[:12])))

    both_same = both_none = ds_only = hy_only = 0
    agree_pick = 0
    for i in ids:
        d = ds.get(i, "").lower()
        h = hy.get(i, "").lower()
        if d == h:
            if d == "none":
                both_none += 1
            else:
                both_same += 1
        elif d == "none" or h == "none":
            if d == "none":
                hy_only += 1
            else:
                ds_only += 1
        else:
            ds_only += 1
            hy_only += 1

    n = len(ids)
    print("\n=== 两模型一致性（n=%d）===" % n)
    print("  都选同一词   %3d  %5.1f%%" % (both_same, 100.0 * both_same / n))
    print("  都判 none    %3d  %5.1f%%" % (both_none, 100.0 * both_none / n))
    print("  ds 标 hy none %3d  %5.1f%%" % (ds_only, 100.0 * ds_only / n))
    print("  hy 标 ds none %3d  %5.1f%%" % (hy_only, 100.0 * hy_only / n))
    exact = sum(1 for i in ids if ds.get(i, "").lower() == hy.get(i, "").lower())
    print("  完全一致     %3d  %5.1f%%" % (exact, 100.0 * exact / n))
    both_pick = sum(1 for i in ids if ds.get(i, "").lower() != "none"
                    and hy.get(i, "").lower() != "none")
    if both_pick:
        print("  两边都标了词的 %d 条中，选同一个词 %d 条 = %.1f%%"
              % (both_pick, both_same, 100.0 * both_same / both_pick))

    print("\n=== 各模型标注量 ===")
    for nm, d in (("ds", ds), ("hy", hy)):
        k = sum(1 for v in d.values() if v.lower() != "none")
        print("  %s: 标 %d / %d = %.1f%%" % (nm, k, len(d), 100.0 * k / max(1, len(d))))

    # 与声学对账
    acc = {}
    if os.path.exists(a.acoustic):
        for r in json.load(open(a.acoustic, encoding="utf-8")):
            if r["seed"] == "rate":
                continue
            acc.setdefault(r["uid"], []).append(r)

    rows = []
    for i in sorted(key):
        k = key[i]
        uid = k["uid"]
        d = ds.get(i, "").lower()
        h = hy.get(i, "").lower()
        if d == h and d != "none":
            verdict = "AGREE"
        elif d != h and "none" in (d, h):
            verdict = "ONE_SIDE"
        elif d != h:
            verdict = "CONFLICT"
        else:
            verdict = "BOTH_NONE"
        obs = [x for x in acc.get(uid, []) if x["adv"].lower() == (d if d != "none" else "")]
        rels = [x["rel"] for x in obs if x["rel"] is not None]
        rows.append(dict(aid=i, uid=uid, ch=k["ch"], ds=d, hy=h, verdict=verdict,
                         rels=rels, rel_med=round(statistics.median(rels), 3) if rels else None))

    print("\n=== 与声学对账（LLM 说该慢的，实际慢了吗）===")
    for tag in ("AGREE", "ONE_SIDE", "CONFLICT"):
        sub = [r for r in rows if r["verdict"] == tag and r["rel_med"] is not None]
        if not sub:
            continue
        good = sum(1 for r in sub if r["rel_med"] >= 1.20)
        ok_mid = sum(1 for r in sub if r["rel_med"] >= 1.00)
        print("  %-9s n=%-3d  已达标(rel≥1.2) %2d (%4.1f%%)   rel≥1.0 %2d (%4.1f%%)   中位 %.3f"
              % (tag, len(sub), good, 100.0 * good / len(sub),
                 ok_mid, 100.0 * ok_mid / len(sub),
                 statistics.median([r["rel_med"] for r in sub])))

    json.dump(rows, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写出 %s" % a.json)

    print("\n=== 需打标签重生（LLM 一致但 rel<1.2）===")
    todo = [r for r in rows if r["verdict"] == "AGREE"
            and (r["rel_med"] is None or r["rel_med"] < 1.20)]
    plan = {str(it["id"]): it for it in
            (lambda d: d if isinstance(d, list) else d.get("items", []))
            (json.load(open(PLAN, encoding="utf-8")))}
    for r in todo:
        print("  %-8s %-12s rel=%-6s | %s"
              % (r["uid"], r["ds"], r["rel_med"], plan.get(r["uid"], {}).get("text", "")[:70]))
    print("  合计 %d 个单元" % len(todo))


if __name__ == "__main__":
    main()
