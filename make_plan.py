"""生成 plan：每条文本 → 音色 wav + 参考文本

音色映射原则（保守，先跑通再调）：
- 不打 emo 标签（用户红线：短对话句一律不打）
- 只靠「换参考音」区分角色与情绪强弱
- 默认用各角色的基准档；带感叹号/命令语气的换强档

2026-11-10 补档：Joseph 新增 normal 三条（Hope Gap 原片，f0_sd 17.0/13.8/18.4，
  动态 8.4/13.9/12.8dB，均为完整陈述句，留一法 gap ≥ +0.550）。
  narrator 与 Joseph 对白基线统一改用 Joseph_normal_1；叙述用同一声线是单人朗读
  有声书的常规做法，不视为缺陷。
"""
import json
import re

SRC = r"G:/_setup/_castle_en_ch123_cast.jsonl"
OUT = r"G:/_setup/_castle_en_ch123_plan.jsonl"

BASE = {
    "Charles": "Charles_neutral_1",
    "Edmund": "Thomas_calm_1",
    "Joseph": "Joseph_normal_1",
    "Helena": "Helena_wary_1",
    "Other": "Helena_defiant_1",
    "narrator": "Joseph_normal_1",
}
STRONG = {
    "Charles": "Charles_excited_1",
    "Edmund": "Thomas_loud_1",
    "Joseph": "Joseph_defiant_1",
    "Helena": "Helena_excited_1",
    "Other": "Helena_excited_1",
    "narrator": "Joseph_normal_1",
}
SOFT = {
    "Charles": "Charles_soft_1",
    "Edmund": "Thomas_begging_1",
    "Joseph": "Joseph_nervous_1",
    "Helena": "Helena_nervous_1",
    "Other": "Helena_nervous_1",
    "narrator": "Joseph_normal_1",
}

STRONG_RE = re.compile(r"!|‘[A-Z][A-Z ]{3,}’|\b(shut up|liar|scaredy|daren'?t|I dare|get out|stupid)\b", re.I)
SOFT_RE = re.compile(r"^(‘)?(No|Yes|Well|Oh|It|May|I don'?t know)[\s.…’,]", re.I)

rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
out = []
for r in rows:
    sp = r["speaker"]
    t = r["text"]
    voice = BASE[sp]
    if STRONG_RE.search(t):
        voice = STRONG[sp]
    elif SOFT_RE.search(t):
        voice = SOFT[sp]
    r["voice"] = voice
    r["voice_base"] = BASE[sp]
    out.append(r)

with open(OUT, "w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

from collections import Counter
print("rows", len(out))
print("voice:", dict(Counter(r["voice"] for r in out)))
tot_words = sum(r["words"] for r in out)
print("words", tot_words, " 预计音频时长 %.1f 分钟" % (tot_words / 155))
print("\n--- 抽样 ---")
for r in out[:6] + out[400:406]:
    print("  %-9s %-8s %-18s %s" % (r["id"], r["speaker"], r["voice"], r["text"][:60]))
