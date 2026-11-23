# -*- coding: utf-8 -*-
"""castle_scan.py —— 扫《I'm the King of the Castle》全文，抽人物候选。

方法（三路交叉，避免漏）：
  1. 所有大写开头的词频（排除句首常见词表）
  2. 称谓前缀：Mr./Mrs./Miss/Master/Dr. + Name
  3. 对话归属动词：said/asked/… + Name，以及 Name + said/…
  4. 每章的分布（判断是否只出现在某章）
输出 G:/_setup/castle_characters_raw.json
"""
import html
import json
import re
import zipfile
from collections import Counter, defaultdict

EPUB = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/reader-app/books/king-of-the-castle.epub"

STOP = set("""The He She It They We You I But And Then When Now There Here His Her Their Our
My Your This That These Those What Who Why How Where If So As At In On Of For With From
Not No Yes Oh Well All Some Any One Two Three Mr Mrs Miss Master Dr Sir Madam
After Before Once Later Soon Still Just Only Even Again Always Never Perhaps Maybe
It's I'm He's She's Don't Didn't Can't Couldn't Wouldn't Shouldn't Wasn't Isn't Aren't
Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April
May June July August September October November December
Kingshaw Hooper Warings Hang Wood Leydell Castle
Chapter""".split())


def clean(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[ \t]+", " ", s)
    return s


z = zipfile.ZipFile(EPUB)
chapters = []
for i in range(1, 19):
    name = "OEBPS/ch%03d.xhtml" % i
    try:
        raw = z.read(name).decode("utf-8", "ignore")
    except KeyError:
        continue
    chapters.append((i, clean(raw)))

full = "\n\n".join(t for _, t in chapters)
print("章节 %d | 字符 %d | 词 %d" % (len(chapters), len(full), len(full.split())))

# ---------- 1) 词频 ----------
cap = Counter(re.findall(r"\b([A-Z][a-z]{2,})\b", full))
cand = {w: n for w, n in cap.items() if w not in STOP and n >= 3}
print("\n【大写词频 top 40（已去常见词）】")
for w, n in sorted(cand.items(), key=lambda kv: -kv[1])[:40]:
    print("  %-18s %d" % (w, n))

# ---------- 2) 称谓 ----------
titles = Counter()
for m in re.finditer(r"\b(Mr|Mrs|Miss|Master|Dr|Doctor)\.?\s+([A-Z][a-z]+)", full):
    titles["%s %s" % (m.group(1), m.group(2))] += 1
print("\n【称谓 + 姓】")
for k, v in titles.most_common(30):
    print("  %-22s %d" % (k, v))

# ---------- 3) 对话归属 ----------
ATTR = ("said|asked|replied|answered|shouted|whispered|cried|muttered|added|continued|"
        "repeated|murmured|yelled|screamed|told|began|went on|put in")
after = Counter(re.findall(r"\b(?:%s)\s+(?:to\s+\w+\s+)?([A-Z][a-z]+)" % ATTR, full))
before = Counter(re.findall(r"\b([A-Z][a-z]+)\s+(?:%s)\b" % ATTR, full))
print("\n【…said X 形式】")
for k, v in after.most_common(25):
    if k not in STOP:
        print("  %-18s %d" % (k, v))
print("\n【X said… 形式】")
for k, v in before.most_common(25):
    if k not in STOP:
        print("  %-18s %d" % (k, v))

# ---------- 4) 每章分布 ----------
per_ch = defaultdict(dict)
for idx, t in chapters:
    c = Counter(re.findall(r"\b([A-Z][a-z]{2,})\b", t))
    for w in set(list(cand.keys()) + list(after.keys()) + list(before.keys())):
        if c.get(w):
            per_ch[w][idx] = c[w]

json.dump(dict(chapters=[i for i, _ in chapters],
               capfreq=dict(cap), candidates=cand,
               titles=dict(titles), attr_after=dict(after), attr_before=dict(before),
               per_chapter={k: v for k, v in per_ch.items()}),
          open("G:/_setup/castle_characters_raw.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
open("G:/_setup/castle_full.txt", "w", encoding="utf-8").write(full)
print("\n写出 castle_full.txt / castle_characters_raw.json")
