# -*- coding: utf-8 -*-
"""mc_pause_rules.py —— 从马修真人母带里学「停顿规则」（v2 分层版）。

v1 的问题：ASR 标点不全，283 个「无标点」间隙里混进 85 个 >=0.6s 的标点级停顿。
v2 改为按**时长分层**判定性质，不依赖 ASR 标点：

  micro  0.06-0.15s  词间微隙（塞音闭合/VAD 抖动），不算停顿
  breath 0.15-0.30s  轻换气
  pause  0.30-0.60s  明显换气
  punct  >=0.60s     标点/句界级

输出 G:/_setup/mc_pause_rules.json
"""
import bisect
import json
import re
from collections import Counter, defaultdict

import numpy as np
import soundfile as sf

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
WORDS = "G:/GPT-SoVITS/_dataset_v5full/wonder_final.json"
OUT = "G:/_setup/mc_pause_rules.json"
SR = 32000

CONJ_COORD = set("and but or nor yet so for".split())
CONJ_SUB = set("""because when while if though although unless until since as than that
which who whom whose where whether after before once whenever wherever whereas
whereby wherein whilst""".split())
ART = set("the a an".split())
PREP = set("""of in on at to with from by about into over under through between across
around like without within upon toward towards against along behind beyond during
except inside outside past off onto unto per via""".split())
PRON = set("""i you he she it we they me him her us them my your his its our their
this these those what something someone anything anyone everyone everything nothing
nobody anybody himself herself itself myself yourself themselves ourselves""".split())
AUX = set("""is are was were be been being am do does did have has had will would
can could shall should may might must""".split())
NEG = set("not no never none nothing nobody".split())
ADV = set("""very just still even only too also always now then here there again
once almost really quite rather well back away together apart instead anyway
perhaps maybe actually finally suddenly simply truly slowly quickly softly""".split())

PRIORITY = [("CONJ_SUB", CONJ_SUB), ("CONJ_COORD", CONJ_COORD), ("NEG", NEG),
            ("AUX", AUX), ("ART", ART), ("PREP", PREP), ("PRON", PRON), ("ADV", ADV)]

PUNCT_MAP = {",": "comma", ".": "period", "?": "question", "!": "exclam",
             ";": "semicolon", ":": "colon"}

TIERS = [("micro", 0.06, 0.15), ("breath", 0.15, 0.30),
         ("pause", 0.30, 0.60), ("punct", 0.60, 99)]


def tier(d):
    for name, lo, hi in TIERS:
        if lo <= d < hi:
            return name
    return "below"


def norm(w):
    return re.sub(r"^[^\w']+|[^\w']+$", "", w.lower())


def cls_of(word):
    w = norm(word)
    if not w:
        return "OTHER"
    for name, s in PRIORITY:
        if w in s:
            return name
    if w.endswith("ly"):
        return "ADV"
    return "OTHER"


def trailing_punct(word):
    m = re.search(r"([,\.\?;:!]+)\s*$", word)
    if not m:
        return None
    return PUNCT_MAP.get(m.group(1)[0], "other")


def vad_segments():
    x, sr = sf.read(MASTER, dtype="float64", always_2d=True)
    x = x.mean(1)
    assert sr == SR, sr
    hop = int(SR * 0.010)
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() - 35.0)
    i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]:
                j += 1
            if i > 0 and j < len(m) and (j - i) < 8:
                m[i:j] = True
            i = j
        else:
            i += 1
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) < 12:
                m[i:j] = False
            i = j
        else:
            i += 1
    segs, i = [], 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]:
                j += 1
            segs.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return segs


def stats(vals):
    if not vals:
        return None
    a = np.array(vals, dtype=float)
    return dict(n=len(a), median=round(float(np.median(a)), 3),
                mean=round(float(a.mean()), 3),
                p10=round(float(np.percentile(a, 10)), 3),
                p25=round(float(np.percentile(a, 25)), 3),
                p75=round(float(np.percentile(a, 75)), 3),
                p90=round(float(np.percentile(a, 90)), 3),
                max=round(float(a.max()), 3))


def main():
    segs = vad_segments()
    d = json.load(open(WORDS, encoding="utf-8"))
    words = []
    for s in d["slices"]:
        for t0, t1, w in s.get("words", []):
            words.append((float(t0), float(t1), w))
    words.sort(key=lambda t: t[0])
    mids = [(a + b) / 2 for a, b, _ in words]
    t0s = [a for a, b, _ in words]

    gaps = []
    for k in range(1, len(segs)):
        g0, g1 = segs[k - 1][1], segs[k][0]
        dur = g1 - g0
        if dur < 0.06:
            continue
        # 对齐修正：词时间戳只有起点（80ms 粒度），且 VAD 在词尾弱音处会提前
        # 判定语音结束（-35dB 相对峰值），所以「中点法」会把间隙后的词误判成前词、
        # 「间隙起点 + 中点」又会跳过前词。最稳的是用**词起点**：
        # 前词 = 最后一个起点 <= 间隙起点；后词 = 第一个起点 >= 间隙终点。
        pi = bisect.bisect_right(t0s, g0) - 1
        ni = bisect.bisect_left(t0s, g1)
        if pi < 0 or ni >= len(words) or ni <= pi:
            continue
        gaps.append(dict(t=round(g0, 3), dur=round(dur, 3),
                         prev=words[pi][2], next=words[ni][2],
                         pi=pi, ni=ni, tier=tier(dur),
                         pp=trailing_punct(words[pi][2])))

    by_tier = defaultdict(list)
    for g in gaps:
        by_tier[g["tier"]].append(g)

    res = dict(meta=dict(master=MASTER, words=len(words), segs=len(segs),
                         gaps=len(gaps), span=round(segs[-1][1], 2),
                         wpm=round(len(words) / (segs[-1][1] / 60), 1),
                         words_per_gap=round(len(words) / len(gaps), 2)))

    res["all"] = stats([g["dur"] for g in gaps])
    res["tiers"] = {}
    for name, lo, hi in TIERS:
        v = by_tier.get(name, [])
        if not v:
            continue
        res["tiers"][name] = dict(
            range=[lo, hi], n=len(v), share=round(len(v) / len(gaps), 3),
            stats=stats([g["dur"] for g in v]),
            by_next_class={k: dict(stats=stats(vv), share=round(len(vv) / len(v), 3))
                           for k, vv in sorted(
                               ((k, [g["dur"] for g in v if cls_of(g["next"]) == k])
                                for k in set(cls_of(g["next"]) for g in v)),
                               key=lambda kv: -len(kv[1]))},
            by_prev_class={k: dict(stats=stats(vv), share=round(len(vv) / len(v), 3))
                           for k, vv in sorted(
                               ((k, [g["dur"] for g in v if cls_of(g["prev"]) == k])
                                for k in set(cls_of(g["prev"]) for g in v)),
                               key=lambda kv: -len(kv[1]))})

    # 标点细分
    punct_gaps = defaultdict(list)
    for g in gaps:
        if g["pp"]:
            punct_gaps[g["pp"]].append(g)
    res["punct"] = {}
    for k, v in sorted(punct_gaps.items(), key=lambda kv: -len(kv[1])):
        sub = {}
        for nk in set(cls_of(g["next"]) for g in v):
            vv = [g["dur"] for g in v if cls_of(g["next"]) == nk]
            if len(vv) >= 3:
                sub[nk] = dict(stats=stats(vv), share=round(len(vv) / len(v), 3))
        res["punct"][k] = dict(n=len(v), stats=stats([g["dur"] for g in v]),
                               by_next_class=sub)

    # 具体词条件概率（按 tier 分开）
    occ = Counter()
    for _, _, w in words:
        occ[norm(w)] += 1

    def word_rows(gap_list, min_occ=1):
        c = Counter()
        vals = defaultdict(list)
        for g in gap_list:
            k = norm(g["next"])
            c[k] += 1
            vals[k].append(g["dur"])
        rows = []
        for w, n in c.items():
            o = occ.get(w, 0)
            if o < min_occ:
                continue
            rows.append(dict(word=w, hits=n, occ=o,
                             p=round(n / o, 3) if o else None,
                             median=round(float(np.median(vals[w])), 3)))
        rows.sort(key=lambda r: (-(r["p"] or 0), -r["hits"]))
        return rows

    res["breath_next"] = word_rows(by_tier.get("breath", []) + by_tier.get("pause", []), 2)
    res["punct_next"] = word_rows(by_tier.get("punct", []), 3)

    # 连词专项：按「前词标点」三分（句号后 / 逗号后 / 无标点）
    def conj_profile(w):
        o = occ.get(w, 0)
        if not o:
            return None
        mine = [g for g in gaps if norm(g["next"]) == w]
        per = [g["dur"] for g in mine if g["pp"] in ("period", "question", "exclam")]
        com = [g["dur"] for g in mine if g["pp"] == "comma"]
        non = [g["dur"] for g in mine if not g["pp"]]
        short = [g["dur"] for g in mine if g["dur"] < 0.6]
        return dict(word=w, occ=o, n_before=len(mine),
                    p_before=round(len(mine) / o, 3),
                    after_period=dict(n=len(per), med=round(float(np.median(per)), 3) if per else None),
                    after_comma=dict(n=len(com), med=round(float(np.median(com)), 3) if com else None),
                    no_punct=dict(n=len(non), med=round(float(np.median(non)), 3) if non else None),
                    short=dict(n=len(short), med=round(float(np.median(short)), 3) if short else None))

    res["conj"] = {}
    for w in ["and", "but", "so", "then", "because", "when", "as", "that",
              "which", "if", "or", "for", "while", "than"]:
        p = conj_profile(w)
        if p:
            res["conj"][w] = p

    # 短停落在哪些词之后（换气点）
    prev_c = Counter()
    for g in by_tier.get("breath", []) + by_tier.get("pause", []):
        prev_c[norm(g["prev"])] += 1
    res["breath_prev_top"] = [dict(word=w, n=n, cls=cls_of(w)) for w, n in prev_c.most_common(25)]

    res["gaps_per_sentence"] = round(len(gaps) / max(1, len(punct_gaps.get("period", []))), 2)

    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------- 打印 ----------
    print("=" * 60)
    print("母带 %.2f min | %d 词 | %.1f wpm | 间隙 %d | 每 %.2f 词一个间隙"
          % (segs[-1][1] / 60, len(words), res["meta"]["wpm"], len(gaps),
             res["meta"]["words_per_gap"]))
    print("=" * 60)
    print("\n【分层】")
    for name, lo, hi in TIERS:
        t = res["tiers"].get(name)
        if not t:
            continue
        s = t["stats"]
        print("  %-7s %.2f-%.2fs  n=%3d (%4.1f%%)  中位 %.2fs  p75 %.2f  p90 %.2f"
              % (name, lo, hi, t["n"], 100 * t["share"], s["median"], s["p75"], s["p90"]))

    print("\n【标点停顿】")
    for k, v in res["punct"].items():
        s = v["stats"]
        print("  %-10s n=%3d  中位 %.2fs  p25 %.2f  p75 %.2f  p90 %.2f  max %.2f"
              % (k, v["n"], s["median"], s["p25"], s["p75"], s["p90"], s["max"]))

    for tname in ("breath", "pause"):
        t = res["tiers"].get(tname)
        if not t:
            continue
        print("\n【%s 换气落在什么词之前】(n=%d)" % (tname, t["n"]))
        for k, v in t["by_next_class"].items():
            s = v["stats"]
            print("  %-10s n=%3d (%4.1f%%)  中位 %.2f  p75 %.2f" %
                  (k, s["n"], 100 * v["share"], s["median"], s["p75"]))
        print("  -- 落在什么词之后 --")
        for k, v in t["by_prev_class"].items():
            s = v["stats"]
            print("  %-10s n=%3d (%4.1f%%)  中位 %.2f" %
                  (k, s["n"], 100 * v["share"], s["median"]))

    print("\n【连词前的停顿：按前词标点三分】")
    print("  %-8s %5s %6s | %6s %7s | %6s %7s | %6s %7s"
          % ("词", "出现", "前有停", "句号后", "中位", "逗号后", "中位", "无标点", "中位"))
    for w, p in res["conj"].items():
        a, b, c = p["after_period"], p["after_comma"], p["no_punct"]
        print("  %-8s %5d %6d | %6d %7s | %6d %7s | %6d %7s"
              % (w, p["occ"], p["n_before"], a["n"], a["med"] if a["med"] else "-",
                 b["n"], b["med"] if b["med"] else "-",
                 c["n"], c["med"] if c["med"] else "-"))

    print("\n【换气前一个词 top】")
    for r in res["breath_prev_top"][:18]:
        print("  %-14s n=%2d  %s" % (r["word"], r["n"], r["cls"]))

    print("\n【标点停顿后接什么词 top】")
    for r in res["punct_next"][:18]:
        print("  %-14s n=%2d 出现%3d  P=%.2f  中位%.2f"
              % (r["word"], r["hits"], r["occ"], r["p"] or 0, r["median"]))

    print("\n写出 %s" % OUT)


if __name__ == "__main__":
    main()
