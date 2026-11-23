# -*- coding: utf-8 -*-
"""用多模型投票结果重建对白验收清单（v2）。

区别只在 `emo` 字段：v1 是 `voice` 后缀的规则映射（Thomas_calm_1 → 平静，69/110 条都套这一档），
v2 是四份独立标注 + 仲裁的多数结果（见 _emo_vote/_emo_final.jsonl）。
音频不动，所以这一版测的是**纯标注准确性**对判定结果的影响，与生成质量解耦。
"""
import collections
import json

PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
EMO = "G:/_setup/_emo_vote/_emo_final.jsonl"
OUT = "G:/_setup/_dlg_plan_v2.jsonl"
WHO_MAP = {"Edmund": "Thomas", "Other": "Helena"}

final = {}
for l in open(EMO, encoding="utf-8"):
    if l.strip():
        r = json.loads(l)
        final[r["id"]] = r

rows = [json.loads(l) for l in open(PLAN, encoding="utf-8") if l.strip()]
out, miss = [], []
for r in rows:
    if r.get("speaker") == "narrator":
        continue
    e = final.get(r["id"])
    if not e or not e.get("emo"):
        miss.append(r["id"])
        continue
    out.append({
        "path": "G:/_setup/_audio_ch123/out/%s.wav" % r["id"],
        "who": WHO_MAP.get(r["speaker"], r["speaker"]),
        "emo": e["emo"],
        "id": r["id"],
        "text": r["text"],
    })

with open(OUT, "w", encoding="utf-8") as f:
    for o in out:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")

print("清单 %d 条 -> %s" % (len(out), OUT))
if miss:
    print("缺标注", len(miss), miss[:5])
print("who:", dict(collections.Counter(o["who"] for o in out)))
print("emo:", dict(collections.Counter(o["emo"] for o in out)))
