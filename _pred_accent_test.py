# -*- coding: utf-8 -*-
"""检验"重音落位"判据能否预测人工偏好。

判据（全部只看文本可预测的东西）：
  sep      = 内容词平均 prom − 功能词平均 prom   （重音是否落在该落的词上）
  top_ct   = 句内最重的词是否内容词
  cov3     = 句内前 3 重里有几个是内容词
  sep_rank = 内容词在句内 prom 排名的平均分位（越小越靠前）

对照：centroid 最低（现有唯一的有效规则，74%）
按 Δcentroid 分档，看韵律判据在哪一档真的有用。
"""
import json
import os

LAB = "G:/_setup/_mt_labels_live.json"
SC = "G:/_setup/_mt_score_ch%d.json"
ST = "G:/_setup/_stress_ch1.json"
CHS = (1, 2, 3)


def load_stress():
    """按 (uid, seed) 索引逐词数据。ch1 有 545 候选。"""
    d = json.load(open(ST, encoding="utf-8"))
    out = {}
    for k, v in d.items():
        uid = v.get("uid")
        seed = str(v.get("seed"))
        ws = [w for w in (v.get("words") or []) if w.get("w") and w["w"] not in ".,;:!?-\"'()[]"]
        if len(ws) < 3:
            continue
        out[(uid, seed)] = ws
    return out


def feats(ws):
    c = [w["prom"] for w in ws if w["content"]]
    f = [w["prom"] for w in ws if not w["content"]]
    sep = (sum(c) / len(c) - sum(f) / len(f)) if c and f else 0.0
    order = sorted(range(len(ws)), key=lambda i: -ws[i]["prom"])
    top_ct = bool(ws[order[0]]["content"])
    cov3 = sum(1 for i in order[:3] if ws[i]["content"]) / min(3, len(order))
    # 内容词的平均排名分位（0=最前，1=最后）
    ranks = [order.index(i) / max(1, len(ws) - 1) for i in range(len(ws)) if ws[i]["content"]]
    sep_rank = sum(ranks) / len(ranks) if ranks else 1.0
    return dict(sep=sep, top_ct=top_ct, cov3=cov3, sep_rank=sep_rank,
                n_ct=len(c), n_fn=len(f))


def main():
    lab = json.load(open(LAB, encoding="utf-8"))
    sc = {}
    for ch in CHS:
        for r in json.load(open(SC % ch, encoding="utf-8")):
            sc[r["id"]] = r
    st = load_stress()
    print("ch1 逐词数据: %d 个 (uid,seed)" % len(st))

    rows = []
    skipped = 0
    for uid, v in lab.items():
        p = str(v.get("pick"))
        r = sc.get(uid)
        if not r or p in ("None", "none"):
            continue
        cm = {str(c["seed"]): c for c in r["cands"]}
        cn = cm.get(p)
        if not cn:
            continue
        rej = [(s, c) for s, c in cm.items() if s != p]
        if not rej:
            continue
        # 取重心最接近的落选者（2 候选时就是那一条）
        qs, qc = min(rej, key=lambda x: abs(x[1]["centroid"] - cn["centroid"]))
        ww = st.get((uid, p))
        lw = st.get((uid, qs))
        if not ww or not lw:
            skipped += 1
            continue
        rows.append(dict(uid=uid, d=cn["centroid"] - qc["centroid"],
                         W=feats(ww), L=feats(lw),
                         cen_w=cn["centroid"], cen_l=qc["centroid"]))

    print("可用 pair: %d 条（缺逐词数据跳过 %d 条）" % (len(rows), skipped))
    print()

    def acc(sub, key, greater=True):
        ok = t = 0
        for r in sub:
            a, b = r["W"][key], r["L"][key]
            if a == b:
                continue
            t += 1
            if (a > b) if greater else (a < b):
                ok += 1
        return ok, t

    near = [r for r in rows if abs(r["d"]) <= 150]
    bands = [("全部", rows), ("近平 |Δc|<=150", near),
             ("音色主导 |Δc|>150", [r for r in rows if abs(r["d"]) > 150])]

    KEYS = [("sep", True), ("sep", False), ("top_ct", True), ("cov3", True),
            ("cov3", False), ("sep_rank", False), ("sep_rank", True)]

    for name, sub in bands:
        print("=== %s  n=%d ===" % (name, len(sub)))
        # centroid 基线
        cb = sum(1 for r in sub if r["d"] < 0)
        print("  %-18s %2d/%2d = %3.0f%%" % ("centroid 低", cb, len(sub), 100 * cb / len(sub)))
        for k, dr in KEYS:
            ok, t = acc(sub, k, dr)
            if t >= 5:
                print("  %-18s %2d/%2d = %3.0f%%  (有效 n=%d)"
                      % (k + (" 高" if dr else " 低"), ok, t, 100 * ok / t, t))
        print()

    # 组合：centroid 低 且 sep 高
    print("=== 组合规则 ===")
    for name, sub in bands:
        combo = sum(1 for r in sub if r["d"] < 0 and r["W"]["sep"] > r["L"]["sep"])
        print("  %-18s centroid低 且 sep高: %d/%d = %.0f%%"
              % (name, combo, len(sub), 100 * combo / len(sub)))

    # 冲突分析：韵律与音色给出的答案不一致时，谁对？
    print()
    print("=== 冲突情形：centroid 认为 A 好，但 sep 认为 B 好 ===")
    conf = [r for r in rows
            if (r["d"] < 0) != (r["W"]["sep"] > r["L"]["sep"])]
    if conf:
        cen_ok = sum(1 for r in conf if r["d"] < 0)
        sep_ok = sum(1 for r in conf if r["W"]["sep"] > r["L"]["sep"])
        print("  冲突 %d 条：centroid 对 %d 条 (%.0f%%)，sep 对 %d 条 (%.0f%%)"
              % (len(conf), cen_ok, 100 * cen_ok / len(conf),
                 sep_ok, 100 * sep_ok / len(conf)))
    else:
        print("  没有冲突")


if __name__ == "__main__":
    main()
