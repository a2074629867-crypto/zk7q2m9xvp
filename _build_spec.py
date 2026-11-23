# -*- coding: utf-8 -*-
"""_build_spec.py —— 生成云端批量候选的 spec.json（B/C/G 类）。

每个条目按「情绪 → 参考档」的**语义正确**映射取 2 个参考 × 2 个 seed。
注意：不做「按语义批量重派档」（DECISIONS 20:22 已推翻），
这里只是给每个条目**换参考条**试音，必要时才换档位，由下游择优决定。

输出 G:/_setup/_cloud_spec.json
"""
import json
import os

HERE = "G:/_setup"
lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
plan = {json.loads(l)["id"]: json.loads(l)
        for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
buckets = json.load(open(os.path.join(HERE, "_dlg_buckets_v25.json"), encoding="utf-8"))
gate = {x["id"]: x for x in json.load(open(os.path.join(HERE, "_gate_dlg_v25.json"), encoding="utf-8"))}

# 情绪 → 优先参考档（按 lib 里真实存在的顺序）
EMO2REF = {
    ("Thomas", "激动反抗"): ["defiant", "loud"],
    ("Thomas", "警惕"): ["wary", "scold"],
    ("Thomas", "委屈"): ["wronged", "begging"],
    ("Thomas", "兴奋"): ["excited"],
    ("Thomas", "紧张"): ["nervous"],
    ("Thomas", "平静"): ["calm"],
    ("Charles", "警惕"): ["wary", "neutral"],
    ("Charles", "委屈"): ["wronged", "soft"],
    ("Charles", "平静"): ["neutral"],
    ("Charles", "兴奋"): ["excited"],
    ("Charles", "紧张"): ["nervous"],
    ("Charles", "激动反抗"): ["angry", "defiant"],
    ("Joseph", "激动反抗"): ["defiant", "normal"],
    ("Joseph", "委屈"): ["wronged", "normal"],
    ("Joseph", "平静"): ["normal"],
    ("Joseph", "紧张"): ["nervous", "normal"],
    ("Helena", "委屈"): ["wronged"],
    ("Helena", "平静"): ["calm", "neutral"],
}


def voices_for(who, emo, k=2):
    """取该角色/情绪下前 2 个可用参考档的第 1 条（多参考档只取一条，避免候选爆炸）。"""
    out = []
    for key in EMO2REF.get((who, emo), []):
        items = (lib.get(who) or {}).get(key) or []
        if items:
            out.append("%s_%s_1" % (who, key))
        if len(out) >= k:
            break
    return out


items, skipped = [], []
ids = [i for k in "BCG" for i in buckets[k]]
for i in ids:
    p, g = plan[i], gate[i]
    who, emo = p["who"], p["emo"]
    vs = voices_for(who, emo)
    if not vs:
        skipped.append((i, who, emo))
        continue
    items.append(dict(id=i, text=p.get("text_src") or p["text"], voices=vs, seeds=[42, 7],
                      who=who, emo=emo, cur=p["voice"],
                      codes=[c["code"] for c in g["reasons"]]))

spec = dict(items=items)
json.dump(spec, open(os.path.join(HERE, "_cloud_spec.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
n = sum(len(x["voices"]) * len(x["seeds"]) for x in items)
print("条目 %d，候选 %d 条" % (len(items), n))
for x in items:
    print("  %-8s %-8s %-6s cur=%-20s → %s" % (x["id"], x["who"], x["emo"], x["cur"], ",".join(x["voices"])))
if skipped:
    print("跳过（无可用档）:", skipped)
