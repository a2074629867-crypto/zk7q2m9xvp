# -*- coding: utf-8 -*-
"""gate_nat.py —— 第 6 闸：自然度下限（NISQA-MOS/DIS/COL + SQUIM-SUBJ 的 z 均值）。

判据全部沿用 `_nat_guard` 10-27 的标定，不重新发明：
  FAIL score < -2.3σ ／ WARN < -1.4σ ／ 语音 <0.9s 判不出（NA）
  该阈值来自「残差噪声 p95 = 2.15」，只作**下限筛**，不能排序、不能选最优 take
  （_nat_guard 文档：真数据 AUC 0.49~0.56，全部覆盖 0.5 ⇒ 分不开细粒度，
   但对「明显不行」在合成已知坏样本上 AUC 0.90）

★ 本轮新增的**档级归因**：同档多条一起 FAIL ⇒ 是参考档坏（换素材重生成），
  不是这几十条各自坏。判据：档内 FAIL 比例 ≥50% 且档内可判条数 ≥3。
  实测依据（2026-11-12）：Charles_angry_1 8/9、Charles_nervous_1 13/13、
  Charles_defiant_1 3/3、Thomas_begging_1 3/4 全部 FAIL，而 Charles_soft_1 0/23。
  同一批测量、同一套阈值下这种「整档塌」不可能是逐条随机缺陷。

★ 阈值有效性对照（同批同参照实测）：
  已交付旁白 _mt_pick 865 条 → FAIL 2.1%（在设计 FPR 5% 内）
  对白 239 条 → FAIL 33.1%
  同一把尺子，旁白不误报，所以对白那 33% 不是标定漂移。
"""
import json, os, sys

sys.path.insert(0, "G:/_setup")
RES = "G:/_setup/_nat_dlg.json"
VOICE_NAT = "G:/_setup/_voice_nat.json"
TIER_VERDICT = "G:/_setup/_tier_ref_verdict.json"
REF_MIN = 2.5        # 参考音频 NISQA-MOS 下限：低于它，生成结果必然跟着塌
_R = {}
_V = {}


def _voice_mos():
    """参考音频自身的 NISQA-MOS（_voice_nat.json，84 条，p10 1.42 / p50 2.34）。"""
    global _V
    if not _V:
        try:
            _V = json.load(open(VOICE_NAT, encoding="utf-8"))
        except Exception:
            _V = {}
    return _V


def _tier_verdict():
    """逐档换档结论表（_tier_ref_verdict.json）。

    ★ 2026-11-12 22:10 修正：原来用「参考 MOS < 2.5 ⇒ 素材天花板」推断 ref_poor，
      被同句 A/B 推翻 —— Thomas_loud_1 参考只有 2.19，旧档重生成却有 MOS 2.82
      （原文件本身 2.80），根本没有质量缺陷；而 Charles_nervous_1（1.52）确实只出 1.55。
      两者不单调 ⇒ 2.5 这个切点是拍脑袋的。
      新规则：**只有做过同句 A/B 且结论为 replace=true 的档**才允许判 ref_poor。
      未验证的档一律判 nat_fail（可重跑），宁可疑成「生成退化」也不许误判成「素材坏」——
      误判成 C 会让整批条目被永久放弃。
    """
    try:
        return json.load(open(TIER_VERDICT, encoding="utf-8"))
    except Exception:
        return {}


def idx():
    global _R
    if not _R:
        _R = json.load(open(RES, encoding="utf-8"))
        # 档级归因（"tier"：voice 名）
        plan = {}
        for l in open("G:/_setup/_dlg_plan_v2.jsonl", encoding="utf-8"):
            l = l.strip()
            if l:
                o = json.loads(l); plan[o["id"]] = o
        by = {}
        for k, v in _R.items():
            by.setdefault(plan[k]["voice"], []).append(v)
        for t, rows in by.items():
            m = [r for r in rows if r["verdict"] in ("FAIL", "OK", "WARN")]
            nf = sum(1 for r in m if r["verdict"] == "FAIL")
            bad = (len(m) >= 3 and nf / len(m) >= 0.5)
            for r in rows:
                r["tier"] = t
                r["tier_n"] = len(m)
                r["tier_fail"] = nf
                r["tier_bad"] = bad
    return _R


CANON_OUT = "G:/_setup/_audio_ch123/out"


def check(wav, tier=None):
    """-> (verdict, note)；verdict ∈ PASS / MANUAL / NA

    ★ 2026-11-12 22:20 修：原来一律按 id 查 `_nat_dlg.json` 缓存。候选音频跑闸时
      缓存里的测量是**旧音频**的，等于换档后根本没测 —— r5 里 21 条候选全部返回
      旧档的 ref_poor，新档位白换。
      现在：只要 wav 不在交付目录 `_audio_ch123/out` 下，就**现测**，并用传入的
      tier（plan 里的 voice）做归因，不读缓存。
    """
    k = os.path.splitext(os.path.basename(wav))[0]
    d = os.path.normpath(os.path.dirname(os.path.abspath(wav))).replace("\\", "/")
    import _nat_guard as NM
    _st = NM.load_stat("dlg")          # ★ 对白专属参照（2026-11-12 23:50 标定）
    if d != CANON_OUT:
        try:
            r = dict(NM.verdict(wav, domain="dlg"))
        except Exception as e:
            return "NA", {"code": "nat_unmeasured", "why": "测量失败：%s" % e}
        r["tier"] = tier or r.get("tier")
    else:
        # 交付目录里的条目：缓存里有 raw，但**判决要按新参照重算** ——
        # 缓存里的 score/verdict 是旁白口径算的，直接用会沿用旧的误报。
        cached = idx().get(k)
        if cached is None:
            return "NA", {"code": "nat_unmeasured", "why": "无自然度测量记录"}
        rawm = cached.get("raw")
        if not rawm:
            return "NA", {"code": "nat_unmeasured", "why": "无原始分"}
        r = dict(NM.score_raw(dict(rawm), stat=_st, domain="dlg"))
        r["tier"] = tier or cached.get("tier")
        r["who"] = cached.get("who")
        r["emo"] = cached.get("emo")
    if r is None:
        return "NA", {"code": "nat_unmeasured", "why": "无自然度测量记录"}
    v = r["verdict"]
    if v == "UNKNOWN":
        return "NA", {"code": "nat_short", "why": r["why"]}
    if v == "FAIL":
        rm = (_voice_mos().get(r.get("tier") or "") or {}).get("mos")
        tv = _tier_verdict().get(r.get("tier") or "")
        if rm is not None and rm < REF_MIN and tv and tv.get("replace") is not True:
            # 参考分低，但这一档没验过换档 / 验过不该换 ⇒ 不许推断成素材天花板
            why = "自然度 %s；参考档 MOS %.2f 偏低，但%s ⇒ 按本条目生成退化处理" % (
                r["why"], rm,
                "同句 A/B 已证实换参考无效" if tv else "该档未做换档 A/B")
            if tv and tv.get("side_finding"):
                why += "（%s）" % tv["side_finding"][:60]
            return "MANUAL", {"code": "nat_fail", "why": why, "score": r.get("score"),
                              "tier": r.get("tier"), "ref_mos": round(float(rm), 2),
                              "tier_bad": bool(r.get("tier_bad"))}
        if rm is not None and rm < REF_MIN:
            why = "自然度 %s；★参考档自身 MOS %.2f < %.1f ⇒ 素材天花板，重生成无效，必须换参考片段" % (
                r["why"], rm, REF_MIN)
            return "MANUAL", {"code": "ref_poor", "why": why, "score": r.get("score"),
                              "tier": r.get("tier"), "ref_mos": round(float(rm), 2),
                              "tier_bad": bool(r.get("tier_bad"))}
        why = "自然度 %s" % r["why"]
        if r.get("tier_bad"):
            why += "；★该档整体 %d/%d 条 FAIL（%s）= 参考档质量问题，不是单条缺陷" % (
                r["tier_fail"], r["tier_n"], r["tier"])
        if rm is not None:
            why += "；参考档 MOS %.2f 尚可 ⇒ 是本条生成退化" % rm
        return "MANUAL", {"code": "nat_fail", "why": why, "score": r.get("score"),
                          "tier": r.get("tier"), "ref_mos": (round(float(rm), 2) if rm is not None else None),
                          "tier_bad": bool(r.get("tier_bad"))}
    if v == "WARN":
        return "PASS", {"code": "nat_warn", "why": "自然度%s（未越下限）" % r["why"],
                        "score": r.get("score"), "tier": r.get("tier")}
    return "PASS", {"code": "nat_ok", "why": "自然度%s" % r["why"],
                    "score": r.get("score"), "tier": r.get("tier")}


def report():
    d = idx()
    import collections
    print("== 档级自然度（同一档多条一起塌 = 档坏）")
    seen = {}
    for k, v in d.items():
        seen.setdefault(v.get("tier"), []).append(v)
    print("%-24s %4s %5s %5s %7s %s" % ("档", "n", "FAIL", "WARN", "中位σ", "归因"))
    for t, rows in sorted(seen.items(), key=lambda x: sum(r.get("score") or 0 for r in x[1]) / len(x[1])):
        sc = [r.get("score") for r in rows if r.get("score") is not None]
        sc.sort()
        med = sc[len(sc) // 2] if sc else 0
        nf = sum(1 for r in rows if r["verdict"] == "FAIL")
        print("%-24s %4d %5d %5d %7.2f %s" % (
            t, len(rows), nf, sum(1 for r in rows if r["verdict"] == "WARN"), med,
            "★整档可疑" if rows[0].get("tier_bad") else ""))
    print()
    print("判决:", dict(collections.Counter(v["verdict"] for v in d.values())))


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        for w in sys.argv[1:]:
            print(os.path.basename(w), check(w))
