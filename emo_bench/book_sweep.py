#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全书扫标：判每条成品的情绪是否演到位，输出重生成清单。

三件事：
  1. 文本预期  —— 用 EMO_RULES + **上下文**（prev_narr / 下一句）判这条该演什么
  2. 音频实测  —— VAD 五判据，按真人正例分位判档
  3. 矛盾清单  —— 该演却没演出来 / 没该演却过演

与 make_jobs.pick_emotion 的区别：那个只看单句，这里把 prev_narr 与相邻句
一起看，避免「下一句是对方的反应」这类误判。

用法：
  python book_sweep.py                 # 用 ch123_final_llm
  python book_sweep.py --dir ch123_final
  python book_sweep.py --emotion 兴奋   # 只看某一类
"""
import argparse
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

import verdict as V

AUDIO_ROOT = "G:/_setup"
FINAL_JSON = "G:/_setup/_ch123_final.json"
DIALOG = "G:/_setup/castle_dialog_v8.json"

INSULT = re.compile(
    r"\b(idiot|stupid|fool|damned?|bloody|hell|shut up|get out|crever|sale|menteur|"
    r"imbécile|idiot|salaud|con)\b", re.I)
BEG = re.compile(r"\b(please|don'?t|i can'?t|i want to go|let me|no more|stop)\b", re.I)
# 正面评价词：感叹号 + 这些才是真"兴奋/赞赏"，光有感叹号多半只是喊人
POS = re.compile(
    r"\b(good|great|brave|wonderful|splendid|amazing|marvel?lous|kind|beautiful|love|"
    r"hurrah|game|fun|clever|cunning|right|perfect|lovely|delicious|best)\b", re.I)
# 威胁/戒备语境词：疑问句要带这些才算"警惕"，否则只是普通提问
THREAT = re.compile(
    r"\b(careful|danger\w*|quiet|hide|hiding|afraid|scared|watch|hurry|behind|listen|"
    r"who'?s there|what was that|did you hear|creep\w*|lurk\w*)\b", re.I)
SHOUT = re.compile(r"\b(shout\w*|scream\w*|yell\w*|cried out|laughed|laughing|roared)\b", re.I)


def expect_emotion(who, text, prev_narr="", next_text=""):
    """返回 (预期情绪类别, 依据)。情绪类别用 verdict 的五类。

    收紧原则：只有感叹号不足以判兴奋（"Edmund!" 只是喊人），
    必须叠加正面评价词或催促词；疑问句要带威胁语义词才算警惕。
    """
    t = text.strip()
    if INSULT.search(t):
        return "激动反抗", "侮辱词"
    if "!" in t:
        if POS.search(t):
            return "兴奋", "感叹号+正面评价词"
        if re.search(r"\b(come|quick|look|run|hurry|here|now|open)\b", t, re.I) or t.count("!") >= 2:
            return "兴奋", "感叹号+催促/多重感叹"
        return "喊叫", "纯感叹（非兴奋）"
    if "..." in t or t.endswith("—"):
        return "委屈", "省略号/破折号（断续）"
    if BEG.search(t):
        return "委屈", "哀求词"
    if t.endswith("?"):
        if THREAT.search(t) or THREAT.search(prev_narr or ""):
            return "警惕", "疑问+威胁语境"
        return "提问", "普通疑问（非警惕）"
    # 注意：早期版本还有一条「上下文里出现 shout/laugh 就判兴奋」，
    # 实测把 "He waited, silent, scarcely breathing." 也判成兴奋了 —— 噪声太大，已删。
    # 文本层判不准的交给音频判据，不要硬猜。
    return None, "—"


def load_units():
    d = json.load(open(DIALOG, encoding="utf-8"))
    units = d["units"] if isinstance(d, dict) else d
    by_text = {}
    for u in units:
        by_text.setdefault((u.get("text") or "").strip(), u)
    return units, by_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(AUDIO_ROOT, "ch123_final_llm"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "book_sweep.json"))
    ap.add_argument("--emotion", default="")
    a = ap.parse_args()

    meta = json.load(open(FINAL_JSON, encoding="utf-8"))
    units, by_text = load_units()
    stats = V.load_stats()

    # 五判据的正例分位阈值（V.pct 需要完整 p10..p90，必须原样传）
    thr = {}
    for g, (src, key) in V.PRIMARY.items():
        st = stats[g]["signals"].get("%s:%s" % (src, key))
        if st:
            thr[g] = st

    import ser as S
    vox = S.VoxDim()
    rows = []
    for uid, m in meta.items():
        p = os.path.join(a.dir, uid + ".wav")
        if not os.path.exists(p):
            continue
        try:
            sc = vox.score(p) or {}
        except Exception:
            continue
        A = float(sc.get("arousal", 0)); Vv = float(sc.get("valence", 0)); D = float(sc.get("dominance", 0))
        txt = m.get("text") or ""

        # 找对应 unit 拿上下文
        u = by_text.get(txt.strip(), {})
        idx = u.get("i")
        prev_narr = u.get("prev_narr", "")
        # 下一句（同一全书里 i+1）
        nxt = ""
        for uu in units:
            if uu.get("i") == (idx + 1 if idx is not None else None):
                nxt = uu.get("text") or ""
                break
        exp, why = expect_emotion(m.get("who"), txt, prev_narr, nxt)

        # 五判据取值
        sig = {"兴奋": A * Vv, "激动反抗": D, "紧张": A * (1 - D), "委屈": 1 - A}
        tiers = {}
        for g, val in sig.items():
            if g in thr:
                q = V.pct(val, thr[g]["pos"])
                tiers[g] = {"val": round(val, 4), "pct": round(q * 100),
                            "tier": "到位" if q >= .25 else ("勉强" if q >= .10 else "没演出来")}
        rows.append({
            "uid": uid, "who": m.get("who"), "text": txt[:80],
            "A": round(A, 3), "V": round(Vv, 3), "D": round(D, 3),
            "f0": m.get("f0"), "dur": m.get("dur"),
            "expect": exp, "why": why, "signals": tiers,
            "gap": (exp and tiers.get(exp) and tiers[exp]["tier"] != "到位"),
        })

    if a.emotion:
        rows = [r for r in rows if r["expect"] == a.emotion]

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"thresholds": thr, "rows": rows}, f, ensure_ascii=False, indent=1)

    # 打印
    groups = {}
    for r in rows:
        groups.setdefault(r["expect"] or "（无明确情绪）", []).append(r)

    print(f"共 {len(rows)} 条  → {a.out}\n")
    for g, rs in sorted(groups.items(), key=lambda x: -len(x[1])):
        bad = [r for r in rs if r["gap"]]
        print(f"== 预期 {g}：{len(rs)} 条，**不到位 {len(bad)} 条**")
        for r in rs:
            s = r["signals"].get(g) if g in ("兴奋", "激动反抗", "紧张", "委屈") else None
            if s:
                flag = "  " if not r["gap"] else "✗ "
                print(f"  {flag}{r['uid']:6s} {r['who']} A={r['A']:.2f} V={r['V']:.2f} "
                      f"{g}={s['val']:.3f} 分位{s['pct']:3d}% {s['tier']:4s} | {r['text'][:46]}")
        print()

    bad_all = [r for r in rows if r["gap"]]
    print(f"### 重生成清单（{len(bad_all)} 条）")
    for r in bad_all:
        s = r["signals"][r["expect"]]
        print(f"  {r['uid']:6s} {r['who']} 预期{r['expect']} 实到{s['pct']}% ({s['tier']}) "
              f"依据={r['why']} | {r['text'][:50]}")


if __name__ == "__main__":
    main()
