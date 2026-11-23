# -*- coding: utf-8 -*-
"""gate_report.py —— 把对白闸结果翻成人能看的交付口径。

为什么要单独一层：`PASS 88/239 = 36.8%` 这个数字会被误读成「63% 的音频是坏的」。
实际拆开是五类，其中只有 REGEN 和「真质量」需要动音频，其余是**测不了**或**素材缺**。

分类（互斥，按优先级）：
  A 通过          声学 + 声纹 + 情绪全过
  B 待重生成      闸门判 REGEN（真缺陷）
  C 缺档未验证    ref_fallback —— 档不存在，情绪没验过（素材问题，不是音频坏）
  D 短句未验收    1-3 词 / 时长 <0.9s —— 声学指标在这种时长上不成立
  E 情绪边缘      在 p10~p25 之间，或撞 HARD_CAP（数学顶）
  F 待人工        其余 MANUAL

用法：
  G:/Python310/python.exe gate_report.py --gate _gate_dlg_v11.json \
      --plan _dlg_plan_v2.jsonl --out _dlg_report_v11.md
"""
import argparse
import collections
import json
import os


def words(t):
    t = (t or "").replace("\u2018", " ").replace("\u2019", "'")
    return len([k for k in t.split() if any(c.isalpha() for c in k)])


MEAS = {"too_short", "spk_short", "emo_short", "role_unmeasurable"}
EDGE = {"emo_low", "emo_marginal", "hard_cap", "bimodal", "emo_unreachable"}


def classify(x, grp=None):
    """grp: {(who, emo): [达标数, 总数]} —— 用于区分「素材问题」与「这条文本本身弱」。"""
    codes = {r["code"] for r in x["reasons"]}
    if x["verdict"] == "PASS":
        return "A"
    # ★ 2026-11-15 17:3x：emo_low 但**同角色同情绪已有多条达标** ⇒ 不是素材/档位问题，
    #   是这一句的文本本身够不到目标强度（实测 c2_0430 `Do not answer me back, please.`
    #   是温和制止；Joseph 激动反抗另外 9 条实测 0.65~0.75 全达标，只有它 0.457）。
    #   这类重生成无效（同参考同 seed 字节级相同，md5 已核），归 B 会让人白跑，
    #   归 C 会让人去找素材 —— 都错。归 E「生成层推不动」，处理动作是人耳/改标注。
    #   ★ 必须放在 REGEN→B 之前：c2_0430 的 verdict 就是 REGEN，放后面永远走不到。
    if "emo_low" in codes and grp:
        _p = grp.get("_plan", {}).get(x.get("_sid") or "") or {}
        _ok, _tot = grp.get((_p.get("who"), _p.get("emo")), (0, 0))
        if _ok >= 5:
            return "E"
    if x["verdict"] == "REGEN":
        return "B"
    # G = 句内一致性（音色突变 / 换人 / 声学阶跃）。优先级在 B 之后、C 之前：
    # 它是音频物理缺陷，比「参考库缺档」更该先修；但不影响 B（REGEN）的判断。
    # G 收两个音色维度闸：第 4 闸（句内一致）与第 5 闸（档内一致）——
    #   都是「这个声音不像这个人」，处理动作相同（换档重生成）。
    if codes & {"intra_severe", "intra_switch", "intra_drift", "scs_outlier"}:
        return "G"
    # H = 自然度不达标（第 6 闸）。音质维度，与 G 并列；排在 C 之前，
    #   因为它是音频本身的缺陷，而 C 只是「参考库没这个情绪」。
    if "nat_fail" in codes:
        return "H"
    # C 统一收「素材问题」：没有这个情绪的档（ref_fallback），
    #   或者有这个档但参考片段本身质量不合格（ref_poor，MOS<2.5）。
    #   两者处理动作相同 —— 补/换素材，不是重跑生成。
    # ★ emo_unreachable 必须排在 C 之前：它是「生成层数学上限，换任何素材都推不动」，
    #   不是「缺素材」。归 C 会让人一直去找素材，白费。
    if "emo_unreachable" in codes:
        return "E"
    # ★ 短句优先归 D（2026-11-15 17:0x 修）
    #   `MIN_SPK_DUR=1.0` 只挡 <1.0s，所以 1.1~1.6s 的句子照样跑情绪判据，
    #   而 1 秒级句子的信号值噪声就有 ±0.015 —— 实测 4 条（c2_0295 1.12s /
    #   c2_0324 1.12s / c3_0872 1.28s / c3_0921 1.57s）与 p10 的差距分别是
    #   0.014 / 0.001 / 0.041 / 0.010，全在噪声量级。
    #   它们原来落 C（「去换素材」），但换任何素材也测不准 —— 处理动作其实是「人耳听」，
    #   跟 D 一样。让 D 的优先级高于 C，避免把人赶去找根本不存在的问题。
    try:
        _dur = float((x.get("tech") or {}).get("dur") or 0)
    except (TypeError, ValueError):
        _dur = 0.0
    if _dur and _dur < 2.0 and (codes & {"ref_fallback", "ref_poor"}):
        return "D"
    if codes & {"ref_fallback", "ref_poor"}:
        return "C"
    if codes & MEAS:
        return "D"
    if codes & EDGE:
        return "E"
    return "F"


LABEL = {
    "A": "通过（声学+声纹+情绪全过）",
    "B": "待重生成（真缺陷）",
    "C": "素材不可用（缺档 / 参考片段质量不达标，需换素材）",
    "D": "短句未验收（声学指标不成立）",
    "G": "音色一致性异常（句内突变/换人/档内离群，第 4+5 闸）",
    "H": "自然度不达标（NISQA+SQUIM 下限筛，第 6 闸）",
    "E": "情绪边缘 / 生成层不可达（p10~p25、撞数学顶、结构性推不动）",
    "F": "待人工",
}


def _solvable(lib, who, emo):
    """该角色/情绪在参考库里现在有没有可用档。"""
    if not lib or not who or not emo:
        return "—"
    # ★ 2026-11-13 02:10：原先这里 `except Exception: alts=set()` 静默兜底，
    #   结果 CLI 直接跑（没设 PYTHONPATH）时 `import dialog_gate` 因找不到 emo_bench 失败，
    #   整张表被无声判成「素材仍缺」—— 结论全反，还不报错。
    #   现在：先补 emo_bench 路径重试；真失败就显式打一行警告，不再假装有结论。
    alts = _emo2en().get(emo) or set()
    have = set((lib.get(who) or {}).keys())
    return "档已补齐，重跑可解" if (alts & have) else "素材仍缺"


_M2E = {}


def _emo2en():
    """取 dialog_gate 的 EMO2EN（唯一真源，不复制一份映射表）。"""
    if _M2E:
        return _M2E
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        import dialog_gate as DG
    except Exception:
        import sys
        for p in (os.path.join(here, "emo_bench"), here):
            if p not in sys.path:
                sys.path.insert(0, p)
        try:
            import dialog_gate as DG
        except Exception as e:
            print("⚠️ 无法载入 EMO2EN（%s: %s），C 类可解性一栏不可信" % (type(e).__name__, e))
            return {}
    _M2E.update(DG.EMO2EN)
    return _M2E


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", default="_dlg_report.md")
    ap.add_argument("--json", default="")
    ap.add_argument("--prev", default="", help="上一版闸结果，给「本轮变化」段用")
    ap.add_argument("--lib", default="G:/_setup/_emo_refs_all.json",
                    help="参考库，判 C 类「档是否已补齐」")
    a = ap.parse_args()

    rows = json.load(open(a.gate, encoding="utf-8"))
    plan = {}
    for l in open(a.plan, encoding="utf-8"):
        l = l.strip()
        if l:
            r = json.loads(l)
            plan[r["id"]] = r

    # 同 (who, emo) 的达标统计：给 classify 区分「素材问题」和「文本本身弱」
    grp = collections.Counter()
    tot_g = collections.Counter()
    for x in rows:
        sid = os.path.splitext(os.path.basename(x["wav"]))[0]
        x["_sid"] = sid
        p = plan.get(sid) or {}
        k = (p.get("who"), p.get("emo"))
        tot_g[k] += 1
        if x["verdict"] == "PASS":
            grp[k] += 1
    grp2 = {k: (grp[k], tot_g[k]) for k in tot_g}
    grp2["_plan"] = plan

    buckets = collections.defaultdict(list)
    for x in rows:
        buckets[classify(x, grp2)].append(x)

    n = len(rows)
    lines = []
    lines.append("# 对白链路交付报告\n")
    lines.append("数据源：`%s`（%d 条）\n" % (os.path.basename(a.gate), n))
    lines.append("## 一、分层（互斥，共 %d 条）\n" % n)
    lines.append("| 类 | 含义 | 条数 | 占全量 |")
    lines.append("|---|---|---|---|")
    # ★ 2026-11-13 01:40：原先只遍历 "ABCDEF"，G/H 两组（v20 里 17+2 条）被漏掉，
    #   各分项相加 220 ≠ 239 —— 报告自相矛盾。改为全量遍历并做求和断言。
    ORDER = "ABGHCDEF"
    for k in ORDER:
        c = len(buckets[k])
        lines.append("| %s | %s | %d | %.1f%% |" % (k, LABEL[k], c, 100.0 * c / n))
    lines.append("")
    tot = sum(len(buckets[k]) for k in ORDER)
    if tot != n:
        lines.append("> ⚠️ 分层合计 %d ≠ 总数 %d，分类逻辑有漏项。" % (tot, n))
        lines.append("")
    lines.append("**严格通过：%d 条（%.1f%%）**" % (len(buckets["A"]), 100.0 * len(buckets["A"]) / n))
    lines.append("")
    lines.append("**可听（含边缘需人耳）：%d 条（%.1f%%）** —— A %d + E %d"
                 % (len(buckets["A"]) + len(buckets["E"]),
                    100.0 * (len(buckets["A"]) + len(buckets["E"])) / n,
                    len(buckets["A"]), len(buckets["E"])))
    lines.append("")
    lines.append("**需要动音频：%d 条** —— B 待重生成 %d + G 音色一致性 %d + H 自然度 %d + C 缺档 %d"
                 % (len(buckets["B"]) + len(buckets["G"]) + len(buckets["H"]) + len(buckets["C"]),
                    len(buckets["B"]), len(buckets["G"]), len(buckets["H"]), len(buckets["C"])))
    lines.append("")
    lines.append("**测不了（不是坏）：%d 条** —— D 短句 %d + F 待人工 %d"
                 % (len(buckets["D"]) + len(buckets["F"]),
                    len(buckets["D"]), len(buckets["F"])))
    lines.append("")

    # 短句按词数拆
    d = buckets["D"]
    if d:
        by = collections.Counter()
        for x in d:
            by[min(words(x.get("text")), 4)] += 1
        lines.append("### D 短句按词数\n")
        lines.append("| 词数 | 条数 |")
        lines.append("|---|---|")
        for k in sorted(by):
            lines.append("| %s | %d |" % (k if k < 4 else "4+", by[k]))
        lines.append("")
        lines.append("> 1-3 词条目上，声纹 embedding 与 F0 统计不成立（0.5s 不足以刻画说话人）。"
                     "这类**不能判 PASS，也不能算坏**，交付时单列。\n")

    # C 缺档按角色情绪
    c = buckets["C"]
    if c:
        cc = collections.Counter()
        for x in c:
            er = x.get("emo_res") or {}
            cc[(x["who"], er.get("emo"))] += 1
        lines.append("### C 缺档明细（素材缺口）\n")
        lines.append("| 角色 | 情绪 | 条数 | 可解性 |")
        lines.append("|---|---|---|---|")
        # ★ 2026-11-13 02:05：C 是「这条音频当时用替代档生成」，不等于「现在还没素材」。
        #   wary/defiant 档补齐后，Thomas/警惕 仍有 3 条卡在 C（旧音频没重跑），
        #   报告却统一写「TTS 重跑变不出这些档」—— 结论反了。按参考库现状分两栏。
        lib = {}
        if a.lib and os.path.exists(a.lib):
            lib = json.load(open(a.lib, encoding="utf-8"))
        for (who, emo), k in cc.most_common():
            lines.append("| %s | %s | %d | %s |" % (who, emo, k, _solvable(lib, who, emo)))
        lines.append("")
        lines.append("> 详见 `_missing_refs_report.md`。"
                     "「素材仍缺」= TTS 重跑变不出来；「档已补齐」= 重跑就能解决，只是还没重跑。\n")

    # B 待重生成
    b = buckets["B"]
    if b:
        lines.append("### B 待重生成明细\n")
        lines.append("| id | 角色 | 原因 | 文本 |")
        lines.append("|---|---|---|---|")
        for x in b:
            codes = ", ".join(sorted({r["code"] for r in x["reasons"]}))
            lines.append("| `%s` | %s | %s | %s |"
                         % (x["id"], x["who"], codes, (x.get("text") or "")[:44]))
        lines.append("")

    # G 音色一致性 / H 自然度 —— 都是「音频本身有缺陷」，要重生成，得给出可查清单
    for key, tag in (("G", "音色一致性异常（第 4+5 闸）"), ("H", "自然度不达标（第 6 闸）")):
        grp = buckets[key]
        if not grp:
            continue
        lines.append("### %s 明细\n" % tag)
        lines.append("| id | 角色 | 判因 | 文本 |")
        lines.append("|---|---|---|---|")
        for x in grp:
            codes = ", ".join(sorted({r["code"] for r in x["reasons"]}))
            lines.append("| `%s` | %s | %s | %s |"
                         % (x["id"], x["who"], codes, (x.get("text") or "")[:40]))
        lines.append("")

    # E 边缘
    e = buckets["E"]
    if e:
        lines.append("### E 情绪边缘明细\n")
        lines.append("| id | 角色 | 情绪 | 值 | tier |")
        lines.append("|---|---|---|---|---|")
        for x in e:
            er = x.get("emo_res") or {}
            v = er.get("value")
            lines.append("| `%s` | %s | %s | %s | %s |"
                         % (x["id"], x["who"], er.get("emo"),
                            ("%.3f" % v) if isinstance(v, (int, float)) else "—",
                            er.get("tier")))
        lines.append("")

    # 电平
    # ★ 2026-11-12 修口径：tech["rms_db"] 是**全段 RMS**（含停顿时长），
    #   被停顿占比一拉就散，实测跨度 5.0dB，但这不是归一指标 —— 用它判「未归一」会误报。
    #   归一用 voiced RMS（去静音后能量平均），单独复核落 _voiced_rms.json。
    rms = [x["tech"]["rms_db"] for x in rows]
    pk = [x["tech"]["peak"] for x in rows]
    vr = {}
    try:
        vr = json.load(open("G:/_setup/_voiced_rms.json", encoding="utf-8"))
    except Exception:
        pass
    vv = [vr[x["id"]] for x in rows if x["id"] in vr and vr[x["id"]] is not None]
    # 闸覆盖：每道闸「真测了」多少条。NA 不是失败，但也绝不能当成通过 ——
    # 不分列就会把「62.8% 没测」说成「62.8% 通过」，或反过来把覆盖说成缺陷。
    lines.append("## 一之二、闸覆盖（真测了多少条）\n")
    lines.append("| 闸 | 可测 | 不可测 | 覆盖 | 不可测原因 |")
    lines.append("|---|---|---|---|---|")
    _COV = [("闸4 句内一致", "intra", "intra_unmeasurable", "声纹需≥3.8s；漂移需≥1.2s"),
            ("闸5 档内一致", "scs", "scs_unmeasurable", "档内不足 3 句无法互比；<2.0s 不判"),
            ("闸6 自然度", "nat", "nat_short", "NISQA 需≥0.9s")]
    for label, key, na_code, why in _COV:
        na = sum(1 for x in rows if (x.get(key) or {}).get("code") == na_code)
        ok = len(rows) - na
        lines.append("| %s | %d | %d | %.1f%% | %s |"
                     % (label, ok, na, 100.0 * ok / len(rows), why))
    lines.append("")
    lines.append("> 闸4 自 2026-11-14 起区分「双路通过」与「仅漂移通道通过」："
                 "`intra_ok` = 声纹+漂移都测了；`intra_drift_ok` = 只有漂移路（声纹需≥3.8s）。"
                 "后者不再记成「测不了」。")
    lines.append("")
    lines.append("> **闸4 漂移路对白用 `profile=dlg` 判据**（2026-11-14 15:40 起）：**不看 ΔF0**，"
                 "只认 |ln 谱质心|≥0.60 且 |Δ谱倾斜|≥4.0 同时超 + HNR 塌 + 能量极端。"
                 "依据：对白 |ΔF0| p95 = 8.9 半音（旁白仅 3.32），F0 大跳在表演里是语调。"
                 "详见 `_dlg_long_timbre.md`。")
    lines.append("")

    # ★ 2026-11-14 新增第 8 维：音色突变按物理位置三路（只报警，**不参与判决**）
    #   用户 15:48 纠正：音色突变最常见于「标点停顿之后换句」那一刻，不是句内。
    _SQ = [(x, x.get("timbre_seq") or {}) for x in rows]
    if any(s for _, s in _SQ):
        _al = [(x, s) for x, s in _SQ if s.get("level") == "alert"]
        _r2 = [(x, s) for x, s in _SQ if s.get("r2")]
        _r3 = [(x, s) for x, s in _SQ if s.get("r3")]
        _both = [(x, s) for x, s in _SQ if s.get("r2") and s.get("r3")]
        _ext = [(x, s) for x, s in _SQ
                if any(e.get("extreme") for e in (s.get("r1") or []))]
        lines.append("## 一之三、音色突变三路（第 8 维，只报警不判死）\n")
        lines.append("| 路 | 物理位置 | 判据 | 命中 |")
        lines.append("|---|---|---|---|")
        lines.append("| 路2 | **标点停顿之后**（重新起音） | 跨停顿(≥2 失声窗) + \\|ΔF0\\|≥6 半音 + 谱质心比≥1.3 | **%d** |" % len(_r2))
        lines.append("| 路3 | 句内（持续发声中途） | drift `profile=dlg` 判 FAIL（声道形状双维 / HNR 塌 / 能量极端） | **%d** |" % len(_r3))
        lines.append("| 两路都命中 | — | 两个失效模式重叠 | %d |" % len(_both))
        lines.append("| 路1 | 条与条之间（换句） | 同角色相邻 + 换参考档 + \\|ΔF0 中位\\|≥6 半音 | %d（**设计常态**，见下） |" % len(_ext))
        lines.append("")
        lines.append("> **路1 不报警的原因（实测）**：296 个换档相邻对的 \\|ΔF0\\| 中位就是 **6.4 半音**、"
                     "p95 12.7 —— 每句用不同参考档，跳 6 半音是常态不是 bug。"
                     "上表只统计 ≥14 半音（p98 之外）的极端值，作为「设计层」参考，不进待修清单。")
        lines.append("")
        if _r2:
            lines.append("### 路2 明细：标点停顿后换音区（用户最在意的场景）\n")
            lines.append("| id | 角色/情绪 | 时长 | 位置 | 停顿 | ΔF0 | 谱质心比 |")
            lines.append("|---|---|---|---|---|---|---|")
            for x, s in sorted(_r2, key=lambda z: -abs(max(z[1]["r2"], key=lambda y: abs(y["delta_st"]))["delta_st"])):
                h = max(s["r2"], key=lambda y: abs(y["delta_st"]))
                lines.append("| `%s` | %s %s | %.1fs | @%.2fs | %d 窗 | %+.1f | ×%.2f |"
                             % (x["id"], x["who"], x["emo"], x["tech"]["dur"],
                                h["t"], h["gap"], h["delta_st"], h["cen_ratio"]))
            lines.append("")
        if _r3:
            lines.append("### 路3 明细：句内音色/发声状态突变（drift dlg 的 FAIL 事件）\n")
            lines.append("| id | 角色/情绪 | 时长 | 位置 | 判据 |")
            lines.append("|---|---|---|---|---|")
            for x, s in _r3:
                h = s["r3"]
                lines.append("| `%s` | %s %s | %.1fs | @%.2fs | %s |"
                             % (x["id"], x["who"], x["emo"], x["tech"]["dur"],
                                h["t"], h["why"]))
            lines.append("")
        lines.append("> 第 8 维**不参与 `decide()`**：路2/路3 有元音切换噪声（/i/ 与 /u/ 谱质心差 2 倍），"
                     "误报不低，所以只进人耳队列。脚本 `gate_timbre_seq.py`，"
                     "全量分析 `_dlg_seq_report.md`。")
        lines.append("")

    lines.append("## 二、电平与峰值\n")
    if vv:
        vv.sort()
        lines.append("- **voiced RMS**（去静音后能量平均，归一指标）中位 %.2f dBFS，"
                     "区间 %.2f ~ %.2f（跨度 %.2f dB）"
                     % (vv[len(vv) // 2], vv[0], vv[-1], vv[-1] - vv[0]))
        lines.append("- 结论：%s（需求 23 要求 ≤1dB）"
                     % ("**已达标**" if vv[-1] - vv[0] <= 1.0 else "**未达标**"))
    lines.append("- 全段 RMS 中位 %.1f dBFS，区间 %.1f ~ %.1f（跨度 %.1f dB）"
                 "—— 含停顿时长，非归一指标，仅供时长/停顿参考"
                 % (sorted(rms)[len(rms) // 2], min(rms), max(rms), max(rms) - min(rms)))
    lines.append("- 峰值最大 %.3f，削波 %d 条" % (max(pk), sum(1 for p in pk if p >= 0.999)))
    lines.append("")

    # 本轮变化（只在给了 --prev 时出）：数字变化 + 谁进谁出，避免「A 变多了」这种无凭证结论
    if a.prev and os.path.exists(a.prev):
        prev_rows = json.load(open(a.prev, encoding="utf-8"))
        pb = collections.defaultdict(set)
        for x in prev_rows:
            pb[classify(x)].add(x["id"])
        lines.append("## 三、本轮变化（对比 `%s`）\n" % os.path.basename(a.prev))
        lines.append("| 类 | 上一版 | 本版 | 变化 |")
        lines.append("|---|---|---|---|")
        for k in ORDER:
            lines.append("| %s | %d | %d | %+d |"
                         % (k, len(pb[k]), len(buckets[k]), len(buckets[k]) - len(pb[k])))
        lines.append("")
        for k in ("A", "G", "H", "C", "E", "F"):
            cur = {x["id"] for x in buckets[k]}
            new_in = sorted(cur - pb[k])
            out = sorted(pb[k] - cur)
            if new_in or out:
                lines.append("- **%s** 新进 %d %s ｜ 移出 %d %s"
                             % (k, len(new_in), new_in if new_in else "",
                                len(out), out if out else ""))
        lines.append("")

    txt = "\n".join(lines)
    open(a.out, "w", encoding="utf-8").write(txt)
    print(txt)
    print("\n写出 %s" % a.out)
    if a.json:
        json.dump({k: [x["id"] for x in v] for k, v in buckets.items()},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("写出 %s" % a.json)


if __name__ == "__main__":
    main()
