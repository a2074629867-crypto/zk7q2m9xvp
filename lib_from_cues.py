# -*- coding: utf-8 -*-
"""lib_from_cues.py —— 把 emo_cut 的 [入库] 候选并进声纹库，产出新库 json。

口径
----
只有 `emo[emo].ok == True` 的（指标过 P25 + 硬检查全过 + 角色差 ≥ 0.4）才入，
和 emo_cut.py 的 [入库] 标签完全一致，不另立标准。

情绪档名映射
------------
`_emo_refs.json` 用的是口语档名（excited / angry / soft / neutral / loud / calm /
scold / begging），emo_cut 用的是六类中文名。这里的映射只为**可读性**，
角色归属只看 role 前缀，不看档名：

    兴奋 → excited    激动反抗 → angry    委屈 → soft
    紧张 → tense      警惕 → wary         平静 → calm

用法
----
  python lib_from_cues.py --cand _emo_auto/candidates.json --out _emo_auto_refs.json
  python lib_from_cues.py --cand ... --out ... --drop-soft   # 对照组：不新增 soft 档
"""
import argparse
import json
import os
import sys

sys.path.insert(0, "G:/_setup")

EMO2BUCKET = {"兴奋": "excited", "激动反抗": "angry", "委屈": "soft",
              "紧张": "tense", "警惕": "wary", "平静": "calm"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", required=True, help="emo_cut.py 的 candidates.json")
    ap.add_argument("--lib", default="G:/_setup/_emo_refs.json", help="基线库")
    ap.add_argument("--out", required=True)
    ap.add_argument("--drop-soft", action="store_true",
                    help="不新增 soft 档（对照组：避免磁铁效应）")
    ap.add_argument("--only-role", help="只给这个角色加素材（做模板配平实验用）")
    ap.add_argument("--max-add", type=int, default=0,
                    help="每个角色最多加几条（按指标值从高到低取），0=不限")
    a = ap.parse_args()

    base = json.load(open(a.lib, encoding="utf-8"))
    rows = json.load(open(a.cand, encoding="utf-8"))

    # 先按指标值排好序，--max-add 才有意义（取最好的那几条，不是先到先得）
    pairs = []
    seen = set()
    for r in rows:
        for emo, e in (r.get("emo") or {}).items():
            if not e.get("ok"):
                continue
            if a.drop_soft and emo == "委屈":
                continue
            if a.only_role and r["role"] != a.only_role:
                continue
            key = (r["role"], EMO2BUCKET.get(emo, emo), r["path"])
            if key in seen:
                continue
            seen.add(key)
            pairs.append((r, emo, e))
    pairs.sort(key=lambda t: -t[2]["value"])

    added = 0
    per_role = {}
    for r, emo, e in pairs:
        if a.max_add and per_role.get(r["role"], 0) >= a.max_add:
            continue
        bucket = EMO2BUCKET.get(emo, emo)
        base.setdefault(r["role"], {}).setdefault(bucket, []).append({
            "path": r["path"], "text": r["text"],
            "value": e["value"], "tier": e["tier"], "gap": r["gap"]})
        per_role[r["role"]] = per_role.get(r["role"], 0) + 1
        added += 1

    json.dump(base, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(len(v) for emos in base.values() for v in emos.values())
    print("新增 %d 条 → %s（库共 %d 条）" % (added, a.out, n))
    for role, emos in base.items():
        print("  %-8s %s" % (role, {k: len(v) for k, v in emos.items()}))

    # 并库后必须复测：模板分布变了，z 与 gap 全都会动。
    # 实测（59 条成品、修好 z 取最大值之后）：
    #   25 模板 → 38 PASS；全量并库 74 模板 → **42 PASS、纯度 100%、总准确率 91.5%**（最好）；
    #   只补 Charles +6/+12 → 37 PASS（不如全量）。
    # 所以这里不再断言「必须配平」——之前那个结论是 z 被 dict 覆盖算错造成的假象。
    cnt = {r: sum(len(v) for v in emos.values()) for r, emos in base.items()}
    if len(cnt) >= 2:
        print("模板分布：%s（最大差 %.0f%%）" % (
            cnt, 100.0 * (max(cnt.values()) - min(cnt.values())) / max(min(cnt.values()), 1)))
    print("→ 换库后**必须**用 dialog_gate + gate_score 回放一套已知真值的成品再看"
          "\n   PASS 数与纯度；只报模板数不能说明变好还是变烂。")


if __name__ == "__main__":
    main()
