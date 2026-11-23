# -*- coding: utf-8 -*-
"""给对白逐句建「带上下文」的情绪标注材料。

为什么不能沿用 voice 后缀：`Thomas_calm_1` 被套在 69/110 条 Thomas 台词上，
连 "I am never afraid." / "Why?" 都算 calm；而原文写着 nervously 的那句标成 normal。
⇒ 情绪档必须**读原著段落上下文**重判，不是按角色套默认档。

输出 `_dlg_ctx.jsonl`，每行：
  id / who / text / voice / cur_emo / para（整段原文）/ prev / next
"""
import json

PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
OUT = "G:/_setup/_dlg_ctx.jsonl"

EMO_MAP = {
    "soft": "委屈", "wronged": "委屈", "begging": "委屈",
    "excited": "兴奋",
    "loud": "激动反抗", "defiant": "激动反抗",
    "nervous": "紧张", "panic": "紧张",
    "wary": "警惕",
    "normal": "平静", "calm": "平静", "neutral": "平静",
}
WHO_MAP = {"Edmund": "Thomas", "Other": "Helena"}

rows = [json.loads(l) for l in open(PLAN, encoding="utf-8") if l.strip()]
# 按 idx 排序，段落上下文才连得上
rows.sort(key=lambda r: r.get("idx", 0))

# 段落 → 该段所有行的文本（含旁白），提供说话场景
para_lines = {}
for r in rows:
    key = (r.get("chapter"), r.get("para"))
    para_lines.setdefault(key, []).append(r)

out = []
for i, r in enumerate(rows):
    if r.get("speaker") == "narrator":
        continue
    voice = r.get("voice") or ""
    emo_en = voice.split("_")[1] if voice.count("_") >= 1 else ""
    key = (r.get("chapter"), r.get("para"))
    para = " ".join(x["text"] for x in para_lines.get(key, []) if x["text"])
    prev = []
    for j in range(max(0, i - 2), i):
        p = rows[j]
        prev.append({"who": WHO_MAP.get(p.get("speaker"), p.get("speaker")), "text": p["text"]})
    nxt = []
    for j in range(i + 1, min(len(rows), i + 3)):
        p = rows[j]
        nxt.append({"who": WHO_MAP.get(p.get("speaker"), p.get("speaker")), "text": p["text"]})
    out.append({
        "id": r["id"],
        "who": WHO_MAP.get(r.get("speaker"), r.get("speaker")),
        "text": r["text"],
        "voice": voice,
        "cur_emo": EMO_MAP.get(emo_en, ""),
        "para": para,
        "prev": prev,
        "next": nxt,
    })

with open(OUT, "w", encoding="utf-8") as f:
    for o in out:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")

import collections
print("材料 %d 条 -> %s" % (len(out), OUT))
print("who:", dict(collections.Counter(o["who"] for o in out)))
print("当前 emo:", dict(collections.Counter(o["cur_emo"] for o in out)))
print("段落长 中位 %.0f 字" % (sorted(len(o["para"]) for o in out)[len(out) // 2]))
