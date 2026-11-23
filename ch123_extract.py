# -*- coding: utf-8 -*-
"""前三章台词提取 v2：正确处理 don’t / it’s 这类撇号。"""
import json
import re
from collections import Counter

T = open("G:/_setup/_book/book.txt", encoding="utf-8").read()
T = re.sub(r"\s+", " ", T)
CH = T[T.find("=== ch001"):T.find("=== ch004")]

# ’ 后面紧跟字母 = 撇号（don’t / it’s / I’ll），不是引号结束
QUOTE = re.compile(r"‘((?:[^‘’]|’(?=[A-Za-z]))*)’")

segs = []
for m in QUOTE.finditer(CH):
    q = m.group(1).strip()
    if not q:
        continue
    segs.append(dict(q=q,
                     before=CH[max(0, m.start() - 260):m.start()].strip(),
                     after=CH[m.end():m.end() + 260].strip(),
                     pos=m.start()))

# 说话人
SPEAK = r"(?:said|asked|whispered|shouted|cried|answered|repeated|added|told)"
def who(s):
    q, b, a = s["q"], s["before"], s["after"]
    # 引号后紧跟 "X said"
    m = re.match(r"^[,\s]*(?:(?:his father|the boy|the man|his mother|she|he)\s+)?" + SPEAK + r"?[,\s]*([A-Z][a-z]+(?: [A-Z][a-z]+)?)", a)
    tail = a[:120]
    if re.search(r"^(?:,|\s)*his father\b", tail):
        return "Joseph"
    if re.search(r"^(?:,|\s)*his mother\b", tail):
        return "MrsK"
    m = re.match(r"^[,\s]*([A-Z][a-z]+)\s+" + SPEAK, a)
    if m:
        n = m.group(1)
        return {"Edmund": "Edmund", "Charles": "Charles", "Kingshaw": "Charles",
                "Hooper": "Edmund", "Joseph": "Joseph"}.get(n, n)
    # 引号前 "X said, ‘"
    m = re.search(r"([A-Z][a-z]+(?: [A-Z][a-z]+)?)\s+(?:had\s+)?" + SPEAK + r"\s*[,\s]*$", b)
    if m:
        n = m.group(1)
        if n.endswith("Hooper") and n != "Hooper":
            return "Joseph"
        return {"Edmund": "Edmund", "Charles": "Charles", "Kingshaw": "Charles",
                "Hooper": "Edmund", "Joseph": "Joseph"}.get(n, n)
    # 呼语
    if re.search(r"\bEdmund\b", q):
        return "Joseph" if len(q.split()) > 6 else "?"
    if re.search(r"\bKingshaw\b|\bCharles\b", q):
        return "Edmund"
    if re.search(r"\bMummy\b", q, re.I):
        return "Charles"
    if re.search(r"\bfather\b", q, re.I):
        return "Edmund"
    return "?"

for s in segs:
    s["who"] = who(s)

# 合并：同一引号被叙述打断（前段不以句末标点结尾 且 中间 gap < 80）
merged = []
for s in segs:
    if merged:
        p = merged[-1]
        tail = p["q"].rstrip()
        gap = s["pos"] - p["pos"] - len(p["q"]) - 2
        if tail and tail[-1] not in ".!?" and 0 <= gap < 90:
            p["q"] = tail + " " + s["q"]
            p["after"] = s["after"]
            p["who"] = p["who"] if p["who"] != "?" else s["who"]
            continue
    merged.append(dict(s))

keep = [s for s in merged if len(s["q"].split()) >= 2]
json.dump(dict(total=len(merged), items=keep),
          open("G:/_setup/_ch123_raw.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("引号段 %d → 合并 %d → 保留 %d" % (len(segs), len(merged), len(keep)))
print(Counter(s["who"] for s in keep))
for i, s in enumerate(keep):
    print("%2d [%-7s] %s" % (i, s["who"], s["q"][:130]))
