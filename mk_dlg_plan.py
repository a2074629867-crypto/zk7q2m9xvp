"""把 plan 转成 dialog_gate 要的验收清单。

映射依据（六类情绪定档，见 MEMORY.md）：
  soft/委屈  ← 1−A     excited/兴奋  ← A×V
  loud/激动反抗 ← D    nervous/紧张  ← A×(1−D)
  wary/警惕  ← e2v disgusted        normal/calm/neutral/平静 ← V
"""
import json

EMO_MAP = {
    "soft": "委屈", "wronged": "委屈", "begging": "委屈",
    "excited": "兴奋",
    "loud": "激动反抗", "defiant": "激动反抗",
    "nervous": "紧张", "panic": "紧张",
    "wary": "警惕",
    "normal": "平静", "calm": "平静", "neutral": "平静",
}
WHO_MAP = {"Edmund": "Thomas", "Other": "Helena"}

rows = [json.loads(l) for l in open("G:/_setup/_castle_en_ch123_plan.jsonl", encoding="utf-8")]
out, skip = [], []
for r in rows:
    if r.get("speaker") == "narrator":
        continue
    voice = r.get("voice") or ""
    emo_en = voice.split("_")[1] if voice.count("_") >= 1 else ""
    emo = EMO_MAP.get(emo_en)
    who = WHO_MAP.get(r["speaker"], r["speaker"])
    p = "G:/_setup/_audio_ch123/out/%s.wav" % r["id"]
    if not emo:
        skip.append((r["id"], voice, "no emo map"))
        continue
    out.append({"path": p, "who": who, "emo": emo, "id": r["id"], "text": r["text"]})

with open("G:/_setup/_dlg_plan.jsonl", "w", encoding="utf-8") as f:
    for o in out:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")

import collections
print("清单 %d 条" % len(out))
print("who:", dict(collections.Counter(o["who"] for o in out)))
print("emo:", dict(collections.Counter(o["emo"] for o in out)))
if skip:
    print("跳过", len(skip), skip[:5])
