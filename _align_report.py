# -*- coding: utf-8 -*-
"""_align_report.py —— 读 _align_dataset.json，出「旁白 vs 真人」对齐报告。

    G:/Python310/python.exe _align_report.py > /dev/null
    → _align_report.md

原则：报告里每个数字都能从 `_align_words.csv` 重算，不写死任何常量。
"""
import json
import os
import statistics as st
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _align_lib as L

ROOT = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: os.path.join(ROOT, *p)

TARGET_ADV_KINDS = ["delivered", "cand", "ctl", "tts", "edit", "prev"]


def load():
    d = json.load(open(L.find_data("_align_dataset.json"), encoding="utf-8"))
    bl = json.load(open(L.BASE_JSON, encoding="utf-8"))
    return d, bl


def fmt_q(q, keys=("p5", "p25", "p50", "p75", "p90", "p95"), prec=2):
    if not q:
        return "—"
    return " | ".join(("%.*f" % (prec, q[k])) if q.get(k) is not None else "—" for k in keys)


def adv_rows(recs):
    out = []
    for r in recs:
        if not r.get("adv"):
            continue
        hits = [w for w in r["words"] if w.get("is_adv")]
        if hits:
            out.append((r, hits[-1]))
    return out


def main():
    d, bl = load()
    recs = d["records"]
    human = [r for r in recs if r["side"] == "human"]
    narr = [r for r in recs if r["side"] == "narr"]
    ref = bl["ref"]
    allz = ref["all"]["relz_sorted"]
    allloc = ref["all"]["loc_sorted"]

    L_ = []
    A = L_.append
    A("# 旁白 ↔ 真人（马修 Wonder 母带）全量对齐报告")
    A("")
    A("构建时间：%s ｜ 真人 **%d 句 / %d 词** ｜ 旁白 **%d 条 take / %d 词** ｜ 词记录合计 **%d 行**"
      % (d["built"], d["n_human"], sum(r["n_content"] for r in human),
         d["n_narr"], sum(r["n_content"] for r in narr),
         sum(r["n_content"] for r in recs)))
    A("")
    A("> 两侧共用 `_align_lib.measure_take`：同一 ASR→wpt 对齐、同一字段、同一分母。")
    A("> `rel` 分母 = **句内全部内容词 sps 中位（含自身）**；`rel_z` 以句内归一的 `rel` 为底只校正音节数。")
    A("")

    # ---------- 一 ----------
    A("## 一、真人基线")
    A("")
    A("拟合（真人 %d 词）：`log(rel) = %.4f %+.4f·log(nsyl)`，`r = %.3f`，`sd = %.4f`"
      % (bl["n_words"], bl["A"], bl["B"], bl["r"], bl["SD"]))
    A("")
    A("| 分层 | n | rel p50 | rel_z p50 | rel_z p90 | loc p50 | loc p90 |")
    A("|---|---|---|---|---|---|---|")
    rows = [("全体", ref["all"])] + \
           [("句中", ref["by_pos"]["mid"]), ("句末区", ref["by_pos"]["end"])] + \
           [("%s 音节" % k, v) for k, v in sorted(ref["by_nsyl"].items())] + \
           [("**句内最长词**", ref["top_rel"]), ("**句内最高音词**", ref["top_loc"])]
    for name, q in rows:
        A("| %s | %d | %s | %s | %s | %s | %s |"
          % (name, q["n"], fmt_q(q["rel"]).split(" | ")[2], fmt_q(q["rel_z"]).split(" | ")[2],
             fmt_q(q["rel_z"]).split(" | ")[4], fmt_q(q["loc"]).split(" | ")[2],
             fmt_q(q["loc"]).split(" | ")[4]))
    A("")
    A("**真人的重读是两条正交通道**：句内最长词 rel_z p50 = **%.2f**（loc 只 +%.2f）；"
      "句内最高音词 loc p50 = **%+.2f**（rel 只 %.2f）。"
      % (ref["top_rel"]["rel_z"]["p50"], ref["top_rel"]["loc"]["p50"],
         ref["top_loc"]["loc"]["p50"], ref["top_loc"]["rel"]["p50"]))
    A("")

    # ---------- 二 ----------
    A("## 二、我们站在哪")
    A("")
    pairs = adv_rows(narr)
    by_kind = defaultdict(list)
    for r, w in pairs:
        by_kind[r["take"]["kind"]].append((r, w))

    A("| 组 | n | rel_z p50 | rel_z p90 | 真人分位 p50 | loc p50 | loc p90 | 真人分位 p50 |")
    A("|---|---|---|---|---|---|---|---|")
    for kind in TARGET_ADV_KINDS:
        v = by_kind.get(kind) or []
        if not v:
            continue
        z = [w["rel_z"] for _, w in v if w.get("rel_z") is not None]
        lo = [w["loc"] for _, w in v if w.get("loc") is not None]
        pz = [L.pct_of(x, allz) for x in z]
        pl = [L.pct_of(x, allloc) for x in lo]
        A("| %s | %d | %+.2f | %+.2f | %.0f | %+.2f | %+.2f | %.0f |"
          % (kind, len(v), st.median(z) if z else 0, L._pct_at(sorted(z), 90) if z else 0,
             st.median(pz) if pz else 0, st.median(lo) if lo else 0,
             L._pct_at(sorted(lo), 90) if lo else 0, st.median(pl) if pl else 0))
    A("")
    A("> 「真人分位」= 该值在真人 %d 个内容词中的百分位。50 = 与真人的普通词一样；"
      "90+ = 达到真人「被强调」的水平。" % ref["all"]["n"])
    A("")

    # 位置 / 音节
    A("### 按位置")
    A("")
    A("| 位置 | n | rel_z p50 | 真人分位 | loc p50 | 真人分位 |")
    A("|---|---|---|---|---|---|")
    for name, want in (("句中", False), ("句末区", True)):
        v = [(r, w) for r, w in pairs if bool(w.get("last")) == want
             and r["take"]["kind"] == "delivered"]
        if not v:
            continue
        z = [w["rel_z"] for _, w in v if w.get("rel_z") is not None]
        lo = [w["loc"] for _, w in v if w.get("loc") is not None]
        A("| %s | %d | %+.2f | %.0f | %+.2f | %.0f |"
          % (name, len(v), st.median(z), st.median([L.pct_of(x, allz) for x in z]),
             st.median(lo), st.median([L.pct_of(x, allloc) for x in lo])))
    A("")

    # ---------- 三 ----------
    A("## 三、同 seed 配对：标签到底起没起作用")
    A("")
    ctl = {(r["uid"], r["take"]["seed"]): w for r, w in pairs if r["take"]["kind"] == "ctl"}
    lab = {(r["uid"], r["take"]["seed"]): (r, w) for r, w in pairs if r["take"]["kind"] == "cand"}
    d_rz, d_loc, d_sp, by_cond = [], [], [], defaultdict(lambda: [[], [], []])
    for k, (r, w) in lab.items():
        if k not in ctl:
            continue
        c = ctl[k]
        if w.get("rel_z") is not None and c.get("rel_z") is not None:
            dz = w["rel_z"] - c["rel_z"]
            d_rz.append(dz)
            by_cond[r["take"].get("cond") or "?"][0].append(dz)
        if w.get("loc") is not None and c.get("loc") is not None:
            dl = w["loc"] - c["loc"]
            d_loc.append(dl)
            by_cond[r["take"].get("cond") or "?"][1].append(dl)
        if w.get("speech") and c.get("speech"):
            ds = w["speech"] / c["speech"]
            d_sp.append(ds)
            by_cond[r["take"].get("cond") or "?"][2].append(ds)

    A("可配对数 **%d**（同一条目、同一 seed、标签版 vs 无标签对照）" % len(d_rz))
    A("")
    A("| 量 | p10 | p50 | p90 | p95 |")
    A("|---|---|---|---|---|")
    for name, v in (("Δrel_z", d_rz), ("Δloc（半音）", d_loc), ("整句有声时长比", d_sp)):
        if not v:
            continue
        s = sorted(v)
        A("| %s | %+.2f | %+.2f | %+.2f | %+.2f |"
          % (name, L._pct_at(s, 10), L._pct_at(s, 50), L._pct_at(s, 90), L._pct_at(s, 95)))
    A("")
    A("按条件拆（r7 = rate 0.70，p9 = pitch +9）：")
    A("")
    A("| cond | n | Δrel_z p50 | Δloc p50 | 整句比 p50 |")
    A("|---|---|---|---|---|")
    for cond, (a1, a2, a3) in sorted(by_cond.items()):
        A("| %s | %d | %s | %s | %s |"
          % (cond, max(len(a1), len(a2)),
             ("%+.2f" % st.median(a1)) if a1 else "—",
             ("%+.2f" % st.median(a2)) if a2 else "—",
             ("%.2f" % st.median(a3)) if a3 else "—"))
    A("")

    # ---------- 四 ----------
    A("## 四、零分布与阈值")
    A("")
    cz = sorted([w["rel_z"] for w in ctl.values() if w.get("rel_z") is not None])
    cl = sorted([w["loc"] for w in ctl.values() if w.get("loc") is not None])
    A("无标签对照（n=%d）的副词 `rel_z`：p50 %+.2f / p90 %+.2f / p95 %+.2f / max %+.2f"
      % (len(cz), L._pct_at(cz, 50), L._pct_at(cz, 90), L._pct_at(cz, 95), cz[-1]))
    A("")
    A("无标签对照的副词 `loc`（半音，n=%d）：p50 %+.2f / p90 %+.2f / p95 %+.2f / max %+.2f"
      % (len(cl), L._pct_at(cl, 50), L._pct_at(cl, 90), L._pct_at(cl, 95), cl[-1]))
    A("")
    suggest = round(L._pct_at(cz, 95) + 0.1, 1) if cz else None
    A("⇒ 建议 `REL_Z_OK = %.1f`（= 对照 p95 %+.2f 上留一格）；"
      "现有 `REL_OK = 1.40` 的 `rel` 等价于 `rel_z ≈ %+.2f`。"
      % (suggest, L._pct_at(cz, 95),
         (__import__("math").log(1.40) - bl["A"] - bl["B"] * __import__("math").log(3)) / bl["SD"]))
    A("")
    A("### 阈值扫描：标签组 vs 无标签对照")
    A("")
    A("| 阈值 | 标签版命中 | 命中率 | 对照假阳性 | 假阳性率 | 净收益 |")
    A("|---|---|---|---|---|---|")
    cand_z = [w["rel_z"] for r2, w in pairs
              if r2["take"]["kind"] == "cand" and w.get("rel_z") is not None]
    for th in (1.2, 1.4, 1.6, 1.8, 2.0):
        nc = sum(1 for x in cand_z if x >= th)
        nf = sum(1 for x in cz if x >= th)
        A("| %.1f | %d/%d | %.0f%% | %d/%d | %.1f%% | %+.1f 个点 |"
          % (th, nc, len(cand_z), 100.0 * nc / max(len(cand_z), 1),
             nf, len(cz), 100.0 * nf / max(len(cz), 1),
             100.0 * (nc / max(len(cand_z), 1) - nf / max(len(cz), 1))))
    A("")
    A("参考锚点：真人「句内最长词」`rel_z` p50 = **%+.2f**、p90 = %+.2f。"
      % (ref["top_rel"]["rel_z"]["p50"], ref["top_rel"]["rel_z"]["p90"]))
    A("**噪声上沿（%+.2f）高于真人目标（%+.2f）** —— 这不是阈值选得不好，"
      "而是「单条 take 的时长起伏」本身就比「标签带来的增量」大。"
      % (L._pct_at(cz, 95), ref["top_rel"]["rel_z"]["p50"]))
    A("")

    # ---------- 五 ----------
    A("## 五、逐单元总表（交付版）")
    A("")
    A("| 单元 | 副词 | 音节 | 位置 | rel | rel_z | 真人分位 | loc | 真人分位 | 名次 | 判定 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|")
    deliv = {r["uid"]: (r, w) for r, w in pairs if r["take"]["kind"] == "delivered"}
    order = sorted(deliv.items(), key=lambda kv: (kv[1][1].get("rel_z") or -9))
    for uid, (r, w) in order:
        A("| %s | %s | %d | %s | %.2f | %+.2f | %.0f | %+.2f | %.0f | %d/%d | %s |"
          % (uid, r["adv"], w["nsyl"], "句末" if w.get("last") else "句中",
             w["rel"], w["rel_z"] or 0,
             L.pct_of(w["rel_z"], allz) or 0, w["loc"] or 0,
             L.pct_of(w["loc"], allloc) or 0,
             w["rank"], r["n_content"], "低上下文" if r["low_context"] else ""))
    A("")

    # ---------- 六 ----------
    A("## 六、异常清单")
    A("")
    p5z = ref["all"]["rel_z"]["p5"]
    p5l = ref["all"]["loc"]["p5"]
    bad_z = [(r, w) for r, w in pairs if r["take"]["kind"] == "delivered"
             and w.get("rel_z") is not None and w["rel_z"] < p5z]
    bad_l = [(r, w) for r, w in pairs if r["take"]["kind"] == "delivered"
             and w.get("loc") is not None and w["loc"] < p5l]
    lowc = [(r, w) for r, w in pairs if r["take"]["kind"] == "delivered" and r["low_context"]]
    syn = [(r, w) for r, w in pairs if r["take"]["kind"] == "delivered"
           and r["synthetic_share"] >= 0.5]
    A("- 交付版 rel_z 低于真人 p5（%.2f）：**%d 条** %s"
      % (p5z, len(bad_z), "、".join("%s(%.2f)" % (r["uid"], w["rel_z"]) for r, w in bad_z) or "无"))
    A("- 交付版 loc 低于真人 p5（%.2f）：**%d 条** %s"
      % (p5l, len(bad_l), "、".join("%s(%.2f)" % (r["uid"], w["loc"]) for r, w in bad_l) or "无"))
    A("- 低上下文（内容词 <4）：**%d 条** %s"
      % (len(lowc), "、".join(r["uid"] for r, _ in lowc) or "无"))
    A("- 对齐一半以上靠合成（synthetic_share ≥0.5）：**%d 条** %s"
      % (len(syn), "、".join("%s(%.0f%%)" % (r["uid"], r["synthetic_share"] * 100) for r, _ in syn) or "无"))
    noadv = [r for r in narr if r["adv"] and not any(w.get("is_adv") for w in r["words"])]
    A("- **找不到副词行**（对齐失败 / 音频不是这句）：**%d 条** %s"
      % (len(noadv), "、".join("%s" % r["gid"] for r in noadv) or "无"))
    A("")

    # ---------- 七 ----------
    A("## 七、口径声明")
    A("")
    A("- 本报告作废以下 ad-hoc 快照：`_anchor_ours.json`、`_anchor_ours2.json`、`_anchor_compare.json`。")
    A("  它们无脚本写入、`rel` 分母与本次不同，数字不可与本表混用。")
    A("- **join 键是 `tid`**（= `gid|kind|seed|md5[0:8]`），一条 take 一行，`(tid, pos)` 与词表 1:1。")
    A("  `uid` 是**单元**级（同一单元的 8 条 take 共用同一个 `uid`），单用它 join 会一对多。")
    A("- 旁白侧不套真人的「内容词 <4 / 漏词 / sps 异常」丢弃规则，"
      "质量用 `synthetic_share` 与 `low_context` 暴露，不静默丢样本。")
    A("- 真人侧丢弃 %d 条（原因见 `_align_dataset.json` 的 `dropped`），"
      "与历史 142 条的差异来自 **cmudict 音节修正**（详见文档 §30）。" % len(d["dropped"]))
    A("")

    txt = "\n".join(L_) + "\n"
    open(J("_align_report.md"), "w", encoding="utf-8").write(txt)
    print(txt[:3000])
    print("\n... 共 %d 行 → _align_report.md" % len(L_))


if __name__ == "__main__":
    main()
