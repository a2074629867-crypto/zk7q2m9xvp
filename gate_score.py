# -*- coding: utf-8 -*-
"""给 dialog_gate 的产出打分：PASS 纯度 / 整体准确率 / 逐角色三档。

为什么单独一个脚本
------------------
`dialog_gate.py` 只报「判定分布」，不报「判对没有」——因为它不知道真值。
真值在台账 `_ch123_final.json` 的 who 字段里（人工标注的目标角色）。
做方案对比时必须把两者合起来算，否则「PASS 多了 6 条」看不出是变好了还是变烂了。

指标口径
--------
  PASS 纯度   = PASS 档里 role == 目标角色的比例   ← 交付质量，最重要
  整体准确率  = 全部行 role == 目标角色的比例
  三档分布    = 每个目标角色的 PASS / MANUAL / REGEN

用法
----
  python gate_score.py out/gate_59.json out/gate_59_C.json ...
  python gate_score.py --json out/gate_59_split.json     # 机器可读
"""
import os
import sys
import json
import argparse
import collections

ROLE_MAP = {"C": "Charles", "E": "Thomas", "Charles": "Charles", "Thomas": "Thomas",
            "Edmund": "Thomas", "Hooper": "Thomas"}


def norm_role(w):
    return ROLE_MAP.get(w, w)


def score(rows, manifest):
    got = []
    for r in rows:
        s = r.get("spk")
        tgt = norm_role(r.get("who") or "")
        pred = s["role"] if s else None
        ok = (pred == tgt) if pred else None
        got.append({
            "id": r["id"], "who": tgt, "pred": pred,
            "ok": ok, "verdict": r["verdict"],
            "role_gap": s["role_gap"] if s else None,
            "z_target": s["z_target"] if s else None,
            "why": [f["code"] for f in r.get("reasons", [])],
        })

    n = len(got)
    npass = sum(1 for g in got if g["verdict"] == "PASS")
    pass_ok = sum(1 for g in got if g["verdict"] == "PASS" and g["ok"])
    tot_ok = sum(1 for g in got if g["ok"])
    per = collections.defaultdict(collections.Counter)
    for g in got:
        per[g["who"]][g["verdict"]] += 1
    bad_pass = [g for g in got if g["verdict"] == "PASS" and not g["ok"]]
    return {
        "n": n,
        "pass": npass,
        "pass_acc": round(100.0 * pass_ok / npass, 1) if npass else 0.0,
        "acc": round(100.0 * tot_ok / n, 1) if n else 0.0,
        "dist": dict(collections.Counter(g["verdict"] for g in got)),
        "per_role": {k: {v: c.get(v, 0) for v in ("PASS", "MANUAL", "REGEN")}
                     for k, c in sorted(per.items())},
        "bad_pass": [{"id": g["id"], "who": g["who"], "pred": g["pred"],
                      "role_gap": g["role_gap"], "z_target": g["z_target"]} for g in bad_pass],
        "rows": got,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--manifest", default="G:/_setup/_ch123_final.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    man = json.load(open(a.manifest, encoding="utf-8"))
    out = {}
    print("%-22s %4s %5s %8s %7s %14s  %s" % (
        "方案", "n", "PASS", "PASS纯度", "总准确", "Thomas(P/M/R)", "Charles(P/M/R)"))
    for f in a.files:
        rows = json.load(open(f, encoding="utf-8"))
        s = score(rows, man)
        out[os.path.basename(f)] = s
        t, c = s["per_role"].get("Thomas", {}), s["per_role"].get("Charles", {})
        print("%-22s %4d %5d %7.1f%% %6.1f%% %14s  %s" % (
            os.path.basename(f)[:22], s["n"], s["pass"], s["pass_acc"], s["acc"],
            "%d/%d/%d" % (t.get("PASS", 0), t.get("MANUAL", 0), t.get("REGEN", 0)),
            "%d/%d/%d" % (c.get("PASS", 0), c.get("MANUAL", 0), c.get("REGEN", 0))))
        if s["bad_pass"]:
            print("   PASS 里的错: " + ", ".join(
                "%s(%s→%s gap%+.2f z%+.2f)" % (b["id"], b["who"], b["pred"],
                                               b["role_gap"], b["z_target"])
                for b in s["bad_pass"]))

    if a.json:
        p = "G:/_setup/out/gate_score.json"
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n写 ->", p)


if __name__ == "__main__":
    main()
