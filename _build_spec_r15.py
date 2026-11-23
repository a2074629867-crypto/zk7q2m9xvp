# -*- coding: utf-8 -*-
"""_build_spec_r15.py —— 为三路音色突变 18 条构造本地重生成候选清单。

候选策略（风险从低到高）：
  1) 原 voice 档 + 多个 seed  —— 最稳，不动音色，只赌单次生成的运气
  2) 同角色同情绪的其他档 + seed 42 —— 备选，仅当原档多 seed 都不行才可能用

输出 `_spec_r15.json`：{"items":[{id,text,voices,seeds,who,emo,cur}], "meta":{...}}
"""
import json
import os

HERE = "G:/_setup"
LIB = os.path.join(HERE, "_emo_refs_all.json")
PLAN = os.path.join(HERE, "_dlg_plan_v2.jsonl")

# 路 2（标点停顿后换音区）6 条 + 路 3（句内声道突变）12 条，零重叠
ROAD2 = ["c1_0049", "c2_0195", "c1_0005", "c1_0037", "c2_0217", "c2_0230"]
ROAD3 = ["c2_0274", "c2_0308", "c2_0246", "c3_0625", "c2_0437", "c2_0368",
         "c3_0876", "c1_0153", "c2_0321", "c2_0372", "c2_0491", "c1_0158"]

SEEDS_CUR = [42, 7, 11]     # 原档：三个 seed
SEED_ALT = [42]             # 备选档：一个 seed


def main():
    lib = json.load(open(LIB, encoding="utf-8"))
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(PLAN, encoding="utf-8") if l.strip()}
    items, missing = [], []
    for rid in ROAD2 + ROAD3:
        p = plan.get(rid)
        if not p:
            missing.append(rid)
            continue
        cur = p.get("voice") or ""
        head, _, n = cur.rpartition("_")
        role, _, emo = head.partition("_")
        pool = ((lib.get(role) or {}).get(emo)) or []
        alts = ["%s_%s_%d" % (role, emo, k + 1) for k in range(len(pool))]
        voices = [cur] + [v for v in alts if v != cur][:2]
        items.append(dict(id=rid, text=p.get("text_src") or p["text"],
                          voices=voices, seeds=SEEDS_CUR,
                          alt_seeds=SEED_ALT, who=p["who"], emo=p["emo"], cur=cur,
                          road="2" if rid in ROAD2 else "3"))
    out = dict(items=items,
               meta=dict(n=len(items), road2=len(ROAD2), road3=len(ROAD3),
                         seeds_cur=SEEDS_CUR, seed_alt=SEED_ALT,
                         note="原档 3 seed + 备选档 1 seed；择优走 _cloud_pick.py 同口径"))
    json.dump(out, open(os.path.join(HERE, "_spec_r15.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    n_gen = sum(len(it["seeds"]) + len(it["alt_seeds"]) * (len(it["voices"]) - 1)
                for it in items)
    print("条目 %d（路2 %d / 路3 %d），计划生成 %d 个候选"
          % (len(items), len(ROAD2), len(ROAD3), n_gen))
    for it in items:
        print("  %-9s 路%s %-8s %-6s cur=%-20s voices=%s"
              % (it["id"], it["road"], it["who"], it["emo"], it["cur"], it["voices"]))
    if missing:
        print("!! 计划里找不到：", missing)


if __name__ == "__main__":
    main()
