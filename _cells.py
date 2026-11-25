# -*- coding: utf-8 -*-
"""
_cells.py —— 按 §15 五层给 716 句打 cell 标签，并**检验这套分类有没有用**。

用户要求（2026-11-25 03:2x）：
  「按句子长度、主谓宾结构、句子重点分类，分成很多种…各个标准都来几句，多不怕，只要能得到数据就行，
    反正就是一定要有相关性，必须要有用，不能做了没用。」

⇒ 分完不算完。必须回答：**同一个 cell 里的句子，韵律是不是真的比跨 cell 更接近？**
   如果 cell 标签解释不了韵律方差（η² 落在置换零分布里），这套分类就是白做，直接报"没用"。

五层（与 PROSODY_ACTION §15 一致）：
  scene  引述 / 叙述 / 描写
  struct 简单 / 并列 / 主从1 / 主从2+      ← 主谓宾结构
  len    ≤8 / 9-17 / 18-27 / ≥28 词
  focus  句末(宽) / 窄(对比) / 引述焦点
输出：
  _cells.json         每句的标签 + 韵律描述量
  _cells_report.md    分布、合并、η² 与置换检验
"""
import json, re, math, random, statistics as st, collections
import numpy as np
import spacy

NLP = spacy.load("en_core_web_sm")

NEG_FOCUS = {"not", "only", "but", "even", "never", "rather", "just", "still",
             "merely", "alone", "nobody", "nothing", "none", "nor"}
QUOTE = re.compile(r'[“”"‘’]|—')


def load():
    texts = {}
    for k, v in json.load(open("_wl_final2.json", encoding="utf-8")).items():
        texts[k.rsplit("/", 1)[-1]] = v["text"]
    nw = {}
    for line in open("_accent_feat_new.jsonl", encoding="utf-8"):
        r = json.loads(line)
        nw[r["id"]] = r["nw"]
    return texts, nw


def label_struct(doc):
    """数「有主语的小句」。主谓宾结构的粗粒度就靠它。"""
    n_clause = 0
    for tok in doc:
        if tok.pos_ in ("VERB", "AUX") and tok.dep_ in ("ROOT", "conj", "advcl", "ccomp",
                                                       "xcomp", "relcl", "acl", "csubj"):
            if any(c.dep_ in ("nsubj", "nsubjpass", "expl") for c in tok.children):
                n_clause += 1
    n_sub = sum(1 for t in doc if t.dep_ in ("advcl", "ccomp", "relcl", "acl", "csubj", "xcomp"))
    n_coord = sum(1 for t in doc if t.dep_ == "conj" and t.pos_ in ("VERB", "AUX"))
    n_sent_split = len([s for s in doc.sents]) - 1

    if n_sub == 0 and n_coord == 0 and n_sent_split == 0:
        return "简单"
    if n_sub == 0 and (n_coord > 0 or n_sent_split > 0):
        return "并列"
    if n_sub == 1:
        return "主从1"
    return "主从2+"


def label_focus(doc, text):
    has_quote = bool(QUOTE.search(text)) or any(t.lemma_.lower() in ("say", "ask", "reply", "cry", "tell")
                                                for t in doc if t.pos_ == "VERB")
    if has_quote:
        return "引述焦点"
    low = [t.text.lower() for t in doc]
    if any(w in NEG_FOCUS for w in low):
        return "窄焦点"
    return "句末焦点"


def label_scene(doc, text):
    if QUOTE.search(text):
        return "引述"
    n_adj = sum(1 for t in doc if t.pos_ == "ADJ")
    cop = any(t.lemma_ == "be" for t in doc)
    if n_adj >= 3 or (cop and n_adj >= 2):
        return "描写"
    return "叙述"


def len_band(n):
    if n <= 8:
        return "≤8"
    if n <= 17:
        return "9-17"
    if n <= 27:
        return "18-27"
    return "≥28"


def desc_from_prosody(r):
    w = r["words"]
    meds = [x["f0_med_rel"] for x in w if x["f0_med_rel"] is not None]
    rngs = [x["f0_range_st"] for x in w if x["f0_range_st"] is not None]
    slps = [abs(x["f0_slope_st_s"]) for x in w if x["f0_slope_st_s"] is not None]
    durs = [x["dur"] for x in w]

    def usable(x):
        if x["f0_med_rel"] is None or x["dur"] < 0.12:
            return False
        return x["voiced_ratio"] * (x["dur"] / 0.01) >= 5

    peaks = []
    for i in range(1, len(w) - 1):
        if not all(usable(x) for x in (w[i - 1], w[i], w[i + 1])):
            continue
        m = [w[i - 1]["f0_med_rel"], w[i]["f0_med_rel"], w[i + 1]["f0_med_rel"]]
        peaks.append(2 * m[1] - m[0] - m[2])

    dmed = [abs(p["d_med"]) for p in r["pairs"] if p["d_med"] is not None]
    end = w[-1]["t1"] if w else 0

    return {
        "span_st": round(float(np.percentile(meds, 90) - np.percentile(meds, 10)), 2) if len(meds) >= 4 else None,
        "wrange_med": round(st.median(rngs), 2) if rngs else None,
        "absdmed_med": round(st.median(dmed), 2) if dmed else None,
        "absdmed_p90": round(float(np.percentile(dmed, 90)), 2) if len(dmed) >= 5 else None,
        "peak_max": round(max(peaks), 2) if peaks else None,
        "slope_med": round(st.median(slps), 1) if slps else None,
        "dur_med": round(st.median(durs), 2) if durs else None,
        "wps": round(len(w) / end, 2) if end > 0.5 else None,
    }


def eta2(vals, labels):
    """单因素方差解释率 η² = SS_between / SS_total"""
    vals = np.asarray(vals, float)
    groups = collections.defaultdict(list)
    for v, l in zip(vals, labels):
        groups[l].append(v)
    gm = vals.mean()
    ssb = sum(len(g) * (np.mean(g) - gm) ** 2 for g in groups.values())
    sst = ((vals - gm) ** 2).sum()
    return ssb / sst if sst > 0 else 0.0


def perm_p(vals, labels, obs, n=300):
    lab = list(labels)
    cnt = 0
    for _ in range(n):
        random.shuffle(lab)
        if eta2(vals, lab) >= obs:
            cnt += 1
    return cnt / n


def main():
    texts, nw = load()
    P = json.load(open("_prosody5_all.json", encoding="utf-8"))
    rows = []
    for sid, text in texts.items():
        doc = NLP(text)
        n = nw.get(sid) or len([t for t in doc if not t.is_punct])
        rows.append({
            "id": sid, "nw": n,
            "scene": label_scene(doc, text),
            "struct": label_struct(doc),
            "len": len_band(n),
            "focus": label_focus(doc, text),
            **desc_from_prosody(P[f"{sid}|new"]),
        })

    # ---- 分布 ----
    print(f"句子 {len(rows)}")
    for key in ("scene", "struct", "len", "focus"):
        c = collections.Counter(r[key] for r in rows)
        print(f"  {key}: {dict(c)}")

    full = collections.Counter((r["struct"], r["len"], r["focus"]) for r in rows)
    print(f"  三维 cell 数 = {len(full)}；≥8 句的 cell = {sum(1 for v in full.values() if v >= 8)}")
    print(f"  最大 cell {full.most_common(3)}")

    # ---- 合并：<8 句的 cell 先并 focus，再并 len ----
    def merged_label(r):
        if full[(r["struct"], r["len"], r["focus"])] >= 8:
            return f'{r["struct"]}|{r["len"]}|{r["focus"]}'
        if full[(r["struct"], r["len"], "句末焦点")] >= 8:
            return f'{r["struct"]}|{r["len"]}|句末焦点*'
        return f'{r["struct"]}|{r["len"]}|*'
    for r in rows:
        r["cell"] = merged_label(r)
    c2 = collections.Counter(r["cell"] for r in rows)
    print(f"  合并后 cell 数 = {len(c2)}；≥8 句 = {sum(1 for v in c2.values() if v >= 8)}；"
          f"最小 = {min(c2.values())}")

    # ---- 有效性检验 ----
    D = ["span_st", "wrange_med", "absdmed_med", "absdmed_p90", "peak_max", "slope_med", "dur_med", "wps"]
    print("\nη²（cell 解释的方差比例）与置换 p 值（300 次）")
    hdr = f"{'描述量':<14}{'η²(cell)':>10}{'p':>7}{'η²(struct|固定len)':>20}{'p':>7}{'η²(focus|固定len)':>20}{'p':>7}"
    print(hdr)
    report = []
    for d in D:
        sub = [r for r in rows if r[d] is not None]
        if len(sub) < 100:
            print(f"{d:<14} 样本不足 {len(sub)}"); continue
        vals = [r[d] for r in sub]
        e_all = eta2(vals, [r["cell"] for r in sub])
        p_all = perm_p(vals, [r["cell"] for r in sub], e_all, 200)

        e_s = e_s_p = e_f = e_f_p = None
        # 固定 len 档内看 struct / focus（去掉长度这个混杂）
        ss = [r for r in sub if r["len"] in ("9-17", "18-27") and len(sub) > 0]
        if len(ss) >= 80:
            v2 = [r[d] for r in ss]
            e_s = eta2(v2, [r["struct"] for r in ss]); e_s_p = perm_p(v2, [r["struct"] for r in ss], e_s, 200)
            e_f = eta2(v2, [r["focus"] for r in ss]); e_f_p = perm_p(v2, [r["focus"] for r in ss], e_f, 200)
        f = lambda x: ("  —" if x is None else f"{x:.3f}")
        print(f"{d:<14}{f(e_all):>10}{p_all:>7.2f}{f(e_s):>20}{('' if e_s_p is None else f'{e_s_p:.2f}'):>7}"
              f"{f(e_f):>20}{('' if e_f_p is None else f'{e_f_p:.2f}'):>7}")
        report.append(dict(desc=d, n=len(sub), eta_cell=round(e_all, 3), p_cell=p_all,
                           eta_struct=round(e_s, 3) if e_s is not None else None,
                           p_struct=e_s_p, eta_focus=round(e_f, 3) if e_f is not None else None,
                           p_focus=e_f_p))

    json.dump({"rows": rows, "cells": dict(c2), "report": report},
              open("_cells.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n→ _cells.json")


if __name__ == "__main__":
    main()
