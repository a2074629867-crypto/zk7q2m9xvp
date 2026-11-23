# -*- coding: utf-8 -*-
"""castle_characters.py v4 —— 角色画像（最终版）

三处关键修正：
  1. 姓氏前排除称谓：`Hooper` 不再匹配 `Mr Hooper`（那是父亲），`Kingshaw` 不匹配 `Mrs Kingshaw`
  2. 台词只在引号「外」匹配归属词（避免 'Charles is a sensible boy' 算成 Charles 说的）
  3. **代词归属**：书里大量用 `he said` / `she said`，按「同一段落内最近被提到的同性角色」归属，
     否则 Helena 只有 2 句台词（实际远不止）

输出 G:/_setup/castle_characters.json
"""
import html
import json
import re
import zipfile
from collections import Counter

EPUB = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/reader-app/books/king-of-the-castle.epub"

ROLES = [
    ("Edmund Hooper", ["Edmund", "Hooper"], "M", "main", "埃德蒙·胡珀"),
    ("Charles Kingshaw", ["Charles", "Kingshaw"], "M", "main", "查尔斯·金斯肖"),
    ("Joseph Hooper", ["Joseph", "Mr Joseph Hooper", "Mr Hooper"], "M", "main", "约瑟夫·胡珀"),
    ("Helena Kingshaw", ["Helena", "Mrs Helena Kingshaw", "Mrs Kingshaw"], "F", "main", "海伦娜·金斯肖"),
    ("Anthony Fielding", ["Fielding", "Anthony"], "M", "support", "安东尼·菲尔丁"),
    ("Alice Boland", ["Alice", "Mrs Alice Boland", "Mrs Boland", "Boland"], "F", "support", "爱丽丝·博兰"),
    ("Ellen Hooper", ["Ellen Hooper", "Ellen"], "F", "mentioned", "艾伦·胡珀"),
    ("Joseph Hooper Sr.", ["his grandfather", "the old man", "grandfather"], "M", "minor", "老胡珀（祖父）"),
    ("Miss Mellitt", ["Miss Mellitt", "Mellitt"], "F", "minor", "梅利特小姐"),
    ("Enid Tyson", ["Enid Tyson", "Mrs Enid Tyson", "Enid"], "F", "minor", "伊妮德·泰森"),
    ("Fenwick", ["Fenwick"], "M", "minor", "芬威克"),
    ("Lesage", ["Lesage"], "M", "minor", "勒萨日"),
    ("Crawford", ["Crawford"], "M", "minor", "克劳福德"),
    ("Broughton-Smith", ["Broughton-Smith", "Broughton"], "M", "minor", "布劳顿-史密斯"),
    ("Devereux", ["Devereux"], "M", "minor", "德弗罗"),
    ("Casey", ["Casey"], "M", "minor", "凯西"),
    ("Gough", ["Gough"], "M", "minor", "高夫"),
    ("Lynch", ["Lynch"], "M", "minor", "林奇"),
    ("Turville", ["Turville"], "M", "minor", "特维尔"),
    ("Mr Gardner", ["Mr Gardner", "Gardner"], "M", "minor", "加德纳先生"),
    ("Mr Busby", ["Mr Busby", "Busby"], "M", "minor", "巴斯比先生"),
    ("Mr Taylor", ["Mr Taylor", "Taylor"], "M", "minor", "泰勒先生"),
    ("Mrs Fielding", ["Mrs Fielding"], "F", "minor", "菲尔丁太太"),
    ("Mrs Devereux", ["Mrs Devereux"], "F", "minor", "德弗罗太太"),
]

ATTR = (r"(?:said|asked|replied|answered|shouted|whispered|cried|muttered|added|"
        r"continued|repeated|murmured|yelled|screamed|told|began|put in|went on|"
        r"called|snapped|demanded|suggested|agreed|admitted|protested)")
THINK = r"(?:thought|wondered|decided|remembered|realised|realized)"
TITLES = {"Mr", "Mrs", "Miss", "Dr"}
BARE_SURNAMES = {"Hooper", "Kingshaw", "Boland", "Fielding", "Devereux", "Crawford",
                 "Fenwick", "Lesage", "Casey", "Gough", "Lynch", "Turville",
                 "Gardner", "Busby", "Taylor", "Mellitt", "Tyson", "Broughton"}


def alias_re(a):
    toks = a.split()
    parts = []
    for t in toks:
        e = re.escape(t)
        if t.rstrip(".") in TITLES:
            e = e.rstrip("\\.") + r"\.?"
        parts.append(e)
    pat = r"\s+".join(parts)
    if len(toks) == 1 and a in BARE_SURNAMES:
        pat = r"(?<!Mr )(?<!Mrs )(?<!Miss )(?<!Dr )" + pat
    return pat


def clean(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[ \t]+", " ", s)
    return s


z = zipfile.ZipFile(EPUB)
chapters = []
for i in range(1, 19):
    try:
        chapters.append((i, clean(z.read("OEBPS/ch%03d.xhtml" % i).decode("utf-8", "ignore"))))
    except KeyError:
        pass
print("章节 %d | 词 %d" % (len(chapters), len(" ".join(t for _, t in chapters).split())))

PAT = {}
RX = {}
for canon, aliases, sex, kind, cn in ROLES:
    PAT[canon] = "|".join(alias_re(a) for a in sorted(aliases, key=len, reverse=True))
    RX[canon] = re.compile(r"\b(?:%s)\b" % PAT[canon])

out = {c: dict(cn=cn, sex=sx, kind=k, aliases=al, total=0, per_chapter=Counter(),
               n_named=0, n_pron=0, n_thoughts=0, quotes=[], thoughts=[])
       for c, al, sx, k, cn in ROLES}

for ci, txt in chapters:
    mentions = []
    for canon, aliases, sex, kind, cn in ROLES:
        for m in RX[canon].finditer(txt):
            mentions.append((m.start(), canon, sex))
            out[canon]["total"] += 1
            out[canon]["per_chapter"][ci] += 1
    mentions.sort()

    qspans = [(m.start(), m.end()) for m in re.finditer(r"'[^']*'", txt)]

    def outside(pos):
        return not any(a <= pos < b for a, b in qspans)

    # 名字归属
    for canon in PAT:
        p = PAT[canon]
        for m in re.finditer(r"\b(?:%s)\s+%s[,:]?\s*'([^']{6,220})'" % (p, ATTR), txt):
            if outside(m.start()):
                out[canon]["n_named"] += 1
                out[canon]["quotes"].append(dict(ch=ci, text=m.group(1).strip(), how="name"))
        for m in re.finditer(r"'([^']{6,220})'[,]?\s*(?:%s\s+)?\b((?:%s))\s+%s" % (ATTR, p, ATTR), txt):
            if outside(m.start(2)):
                out[canon]["n_named"] += 1
                out[canon]["quotes"].append(dict(ch=ci, text=m.group(1).strip(), how="name"))
        for m in re.finditer(r"\b(?:%s)\s+%s[,:]?\s*([^'.']{10,170})" % (p, THINK), txt):
            if outside(m.start()):
                out[canon]["n_thoughts"] += 1
                out[canon]["thoughts"].append(dict(ch=ci, text=m.group(1).strip()))

    # 代词归属（两种语序都要）
    #   A) he said, '...'   → 说话者在后
    #   B) '...' she said   → 说话者在前文
    def pick(pos, sex):
        seg = max(txt.rfind("\n", 0, pos), txt.rfind(".", 0, pos))
        seg = max(0, seg + 1)
        cand = [x for x in mentions if seg <= x[0] < pos and x[2] == sex]
        return cand[-1][1] if cand else None

    for m in re.finditer(r"\b(he|she|He|She)\s+%s\b" % ATTR, txt):
        sex = "M" if m.group(1).lower() == "he" else "F"
        canon = pick(m.start(), sex)
        if not canon:
            continue
        qm = re.match(r"[,:]?\s*'([^']{6,220})'", txt[m.end():])
        if qm:
            out[canon]["n_pron"] += 1
            out[canon]["quotes"].append(dict(ch=ci, text=qm.group(1).strip(), how="pron"))

    for m in re.finditer(r"'([^']{6,220})'[,]?\s*(?:%s\s+)?\b(he|she)\s+%s" % (ATTR, ATTR), txt):
        sex = "M" if m.group(2).lower() == "he" else "F"
        canon = pick(m.start(1), sex)
        if not canon:
            continue
        out[canon]["n_pron"] += 1
        out[canon]["quotes"].append(dict(ch=ci, text=m.group(1).strip(), how="pron"))

for c in out:
    out[c]["per_chapter"] = dict(out[c]["per_chapter"])
    out[c]["chapters"] = sorted(out[c]["per_chapter"].keys())
    out[c]["n_quotes"] = out[c]["n_named"] + out[c]["n_pron"]
    out[c]["quotes"] = out[c]["quotes"][:10]
    out[c]["thoughts"] = out[c]["thoughts"][:4]

ORDER = {"main": 0, "support": 1, "mentioned": 2, "minor": 3}
rows = sorted(out.items(), key=lambda kv: (kv[1]["sex"] != "M", ORDER[kv[1]["kind"]], -kv[1]["total"]))

for sex, label in (("M", "男"), ("F", "女")):
    print("\n" + "=" * 106)
    print("【%s】" % label)
    print("%-20s %-12s %-9s %6s %7s %7s %7s %6s" %
          ("全名", "中文", "类型", "提及", "台词(名)", "台词(代)", "台词合计", "独白"))
    print("=" * 106)
    for canon, d in rows:
        if d["sex"] != sex:
            continue
        print("%-20s %-12s %-9s %6d %7d %7d %7d %6d"
              % (canon, d["cn"], d["kind"], d["total"], d["n_named"], d["n_pron"],
                 d["n_quotes"], d["n_thoughts"]))

print("\n\n【主要角色台词（含代词归属）】")
for canon, d in rows:
    if d["kind"] not in ("main", "support"):
        continue
    print("\n--- %s（%s）  名归属 %d / 代归属 %d" % (canon, d["cn"], d["n_named"], d["n_pron"]))
    for q in d["quotes"][:5]:
        print("   ch%-2d [%s] '%s'" % (q["ch"], q["how"], q["text"][:110]))

json.dump(out, open("G:/_setup/castle_characters.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n写出 G:/_setup/castle_characters.json")
