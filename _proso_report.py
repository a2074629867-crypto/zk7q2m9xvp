# -*- coding: utf-8 -*-
"""_proso_report.py —— Prosogram glissando 层的中文报告。

    G:/Python310/python.exe _proso_report.py     -> _proso_report.md
"""
import json
import math
import os
import re
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: os.path.join(ROOT, *p)

OUT = []


def A(s=""):
    OUT.append(s)


def pct_at(v, p):
    v = sorted(v)
    if not v:
        return None
    i = (len(v) - 1) * p
    lo = int(i)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def med(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else None


def f1(x, nd=1):
    return "—" if x is None else ("%%.%df" % nd) % x


def sign_p(k, n):
    """双尾符号检验（正态近似 + 连续性校正）。k = 正号个数。"""
    if n == 0:
        return 1.0
    z = (abs(k - n / 2.0) - 0.5) / math.sqrt(n / 4.0)
    return 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))


def two_prop_z(k1, n1, k2, n2):
    """两比例 z 检验（非独立样本，仅作量级参考）。"""
    p = (k1 + k2) / float(n1 + n2)
    se = math.sqrt(p * (1 - p) * (1.0 / n1 + 1.0 / n2))
    return (k1 / float(n1) - k2 / float(n2)) / se if se else 0.0


def z2p(z):
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def rate(rows, key):
    """有滑率（%）"""
    if not rows:
        return None
    return 100.0 * sum(1 for w in rows if w[key] > 0) / len(rows)


def unit_of(gid):
    m = re.match(r"^n:([^:]+)", gid or "")
    return m.group(1) if m else (gid or "")


def main():
    d = json.load(open(J("_proso.json"), encoding="utf-8"))
    mp = json.load(open(J("_proso_map.json"), encoding="utf-8"))
    al = json.load(open(J("_align_dataset.json"), encoding="utf-8"))
    bl = json.load(open(J("_align_baseline.json"), encoding="utf-8"))
    T, W, N, P = d["takes"], d["words"], d["nuclei"], d["profiles"]
    tmap = {t["tid"]: t for t in T}
    byt = defaultdict(list)
    for w in W:
        byt[w["tid"]].append(w)
    nuc = defaultdict(list)
    for x in N:
        nuc[x["tid"]].append(x)

    A("# Prosogram glissando 层：旁白 vs 真人")
    A()
    A("> 生成：`_proso_tg.py`（造 TextGrid）→ Praat 7.0.02 + Prosogram 3.05（`praat_run.praat`）")
    A("> → `_proso_parse.py`（解析）→ 本报告。测量核仍是 `_align_lib`，这一层是**加在它上面的第二路**。")
    A()

    # ---------- 一 ----------
    A("## 一、能不能用：音节核产出率")
    A()
    A("Prosogram 的核心是「把 F0 简化成直线段，再用听感阈值判这段算不算真的动了」。")
    A("阈值 `G = 0.16–0.32/T²` 半音（T = 核长秒数），1997 年用重合成回放做听辨实验标定。")
    A("前置条件是**它得先找到音节核**——旁白气声重，这一关不一定过。")
    A()
    tot_iv = sum(t["n_iv"] for t in T)
    tot_nu = sum(t["n_nucl"] for t in T)
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 输入 take | 403（真人 159 + 旁白 244） |")
    A("| 产出 take | **%d**（1 条失败） |" % len(T))
    A("| 音节区间 | %d |" % tot_iv)
    A("| 识别出核 | %d |" % tot_nu)
    A("| 总产出率 | **%.0f%%** |" % (100.0 * tot_nu / max(1, tot_iv)))
    A()
    A("| kind | n | 产出率 p50 |")
    A("|---|---|---|")
    for k in ("human", "delivered", "cand", "ctl", "tts", "edit", "prev"):
        g = [t for t in T if t["kind"] == k] or [t for t in T if t["side"] == k]
        if not g:
            continue
        A("| %s | %d | %.0f%% |" % (k, len(g), 100 * med([t["yield_rate"] for t in g])))
    A()
    miss = [mp[k]["tid"] for k in mp if mp[k]["tid"] not in tmap]
    if miss:
        A("失败 %d 条：%s。" % (len(miss), "、".join("`%s`" % m for m in miss[:3])))
        A("Prosogram 报 `No syllabic nuclei found in speech signal`——该条气声段内没有可用的发声帧，")
        A("不是我们的 TextGrid 有问题（同批其余 %d 条都读到了 `syll` 层）。" % (len(T) - len(miss)))
        A()

    # ---------- 二 ----------
    A("## 二、真人：有滑是常态，不是强调标记")
    A()
    H = [w for w in W if w["side"] == "human"]
    hb = defaultdict(list)
    for w in H:
        hb[w["tid"]].append(w)
    top_rz, top_loc, rest = [], [], []
    for tid, ws in hb.items():
        ok = [w for w in ws if w.get("rel_z") is not None and w.get("loc") is not None and w["n_nuclei"]]
        if len(ok) < 4:
            continue
        a = max(ok, key=lambda w: w["rel_z"])
        b = max(ok, key=lambda w: w["loc"])
        top_rz.append(a)
        top_loc.append(b)
        rest.extend([w for w in ok if w is not a and w is not b])

    A("| 组 | n | 有滑率 | 上滑率 | 滑幅 p50 | 滑幅 p75 |")
    A("|---|---|---|---|---|---|")
    for tag, rows in (("句内最长词", top_rz), ("句内最高音词", top_loc), ("其余词", rest), ("全体", H)):
        mags = [w["max_abs_intra"] for w in rows if w["n_move"] > 0]
        A("| %s | %d | %.1f%% | %.1f%% | %s | %s |" % (
            tag, len(rows), rate(rows, "n_move"), rate(rows, "n_up"),
            f1(med(mags), 2), f1(pct_at(mags, .75) if mags else None, 2)))
    A()
    A("**读法**：真人自己就有 %.0f%% 的词带核内滑音——「有滑」是朗读的常态。" % rate(H, "n_move"))
    k1 = sum(1 for w in top_rz if w["n_move"] > 0)
    k2 = sum(1 for w in rest if w["n_move"] > 0)
    zr = two_prop_z(k1, len(top_rz), k2, len(rest))
    A("真正的信号是**选择性**：句内最长词 %.1f%% vs 其余 %.1f%%，**+%.1f 个点**"
      "（两比例 z = %.2f，p ≈ %.4f；同句内非独立，只作量级参考）。"
      % (rate(top_rz, "n_move"), rate(rest, "n_move"),
         rate(top_rz, "n_move") - rate(rest, "n_move"), zr, z2p(zr)))
    A("上滑率同样：%.1f%% vs %.1f%%，+%.1f 点。"
      % (rate(top_rz, "n_up"), rate(rest, "n_up"), rate(top_rz, "n_up") - rate(rest, "n_up")))
    A()
    A("幅度反而不分：最长词滑幅 p50 = %s 半音，其余词 %s 半音。**真人不是把滑音做得更大，是把滑音放到该放的词上。**"
      % (f1(med([w["max_abs_intra"] for w in top_rz if w["n_move"] > 0]), 2),
         f1(med([w["max_abs_intra"] for w in rest if w["n_move"] > 0]), 2)))
    A()

    # ---------- 三 ----------
    A("## 三、我们：没有选择性")
    A()
    A("| kind | 副词 有滑 | 同句其他词 有滑 | 差 | 副词 上滑 | 其他 上滑 | 差 |")
    A("|---|---|---|---|---|---|---|")
    for k in ("delivered", "cand", "ctl", "tts", "edit", "prev"):
        g = [w for w in W if w["kind"] == k]
        adv = [w for w in g if w["is_adv"]]
        oth = [w for w in g if not w["is_adv"]]
        if not adv:
            continue
        a1, o1 = rate(adv, "n_move"), rate(oth, "n_move")
        a2, o2 = rate(adv, "n_up"), rate(oth, "n_up")
        A("| %s | %.1f%% (n=%d) | %.1f%% (n=%d) | **%+.1f** | %.1f%% | %.1f%% | %+.1f |" % (
            k, a1, len(adv), o1, len(oth), a1 - o1, a2, o2, a2 - o2))
    A()
    g = [w for w in W if w["kind"] == "delivered"]
    adv = [w for w in g if w["is_adv"]]
    oth = [w for w in g if not w["is_adv"]]
    A("交付版副词比同句其他词高 **%+.1f 个点**（真人目标是 +%.1f）。"
      % (rate(adv, "n_move") - rate(oth, "n_move"), rate(top_rz, "n_move") - rate(rest, "n_move")))
    A("而且**对照组的差（%+.1f）比交付版还大**——说明这个差值在我们的数据里主要是噪声，不是标签。"
      % (rate([w for w in W if w["kind"] == "ctl" and w["is_adv"]], "n_move")
         - rate([w for w in W if w["kind"] == "ctl" and not w["is_adv"]], "n_move")))
    A()

    # ---------- 四 ----------
    A("## 四、同单元同 seed 配对：标签在滑音通道上**完全没有留下痕迹**")
    A()
    idx = defaultdict(dict)
    for t in T:
        if t["side"] == "narr":
            idx[(unit_of(t["gid"]), t["seed"])][t["kind"]] = t
    pairs = [(v["cand"], v["ctl"]) for v in idx.values() if "cand" in v and "ctl" in v]
    A("可用配对 **%d 对**（同一单元、同一 seed，一条打标签一条不打），其中 %d 对两侧副词都有音节核。"
      % (len(pairs), len([1 for a, b in pairs if a["adv_nucl"] and b["adv_nucl"]])))
    A()
    A("### 4.1 连续量（符号检验）")
    A()
    A("| 量 | Δ p50 | Δ>0 | n | 符号检验 p |")
    A("|---|---|---|---|---|")
    rows = [
        ("整句 max\\|intra\\|（半音）", [a["max_abs_intra"] - b["max_abs_intra"] for a, b in pairs]),
        ("**副词** max\\|intra\\|（半音）", [a["adv_max_intra"] - b["adv_max_intra"]
                                        for a, b in pairs if a["adv_nucl"] and b["adv_nucl"]]),
        ("整句 mean\\|intra\\|（半音）", [a["mean_abs_intra"] - b["mean_abs_intra"] for a, b in pairs]),
        ("副词核相对时长", [a["adv_rel_dur"] - b["adv_rel_dur"]
                     for a, b in pairs if a["adv_nucl"] and b["adv_nucl"]]),
    ]
    for tag, v in rows:
        v = [x for x in v if x is not None]
        if not v:
            continue
        k = sum(1 for x in v if x > 0)
        A("| %s | %+.2f | %.0f%% | %d | %.3f |" % (tag, med(v), 100.0 * k / len(v), len(v), sign_p(k, len(v))))
    A()
    A("### 4.2 有滑 / 上滑 / 下滑（McNemar 配对）")
    A()
    A("| 判定 | 两者都有 | 只 cand | 只 ctl | 都没有 |")
    A("|---|---|---|---|---|")
    for lab, f in (("副词有上滑", lambda t: t["adv_up"] > 0),
                   ("副词有下滑", lambda t: t["adv_down"] > 0),
                   ("副词有任何滑", lambda t: t["adv_move"] > 0)):
        sub = [(a, b) for a, b in pairs if a["adv_nucl"] and b["adv_nucl"]]
        tt = sum(1 for a, b in sub if f(a) and f(b))
        tf = sum(1 for a, b in sub if f(a) and not f(b))
        ft = sum(1 for a, b in sub if not f(a) and f(b))
        ff = sum(1 for a, b in sub if not f(a) and not f(b))
        A("| %s | %d | **%d** | **%d** | %d |" % (lab, tt, tf, ft, ff))
    A()
    A("不一致对分别是 **9 vs 8**（上滑）、**10 vs 10**（下滑）、**7 vs 5**（有任何滑）——")
    A("**全部在 50/50 上**。打标签既不增加也不减少副词上的滑音。")
    A()
    A("### 4.3 这条结论意味着什么")
    A()
    dv = [a["max_abs_intra"] - b["max_abs_intra"] for a, b in pairs]
    da = [a["adv_max_intra"] - b["adv_max_intra"] for a, b in pairs if a["adv_nucl"] and b["adv_nucl"]]
    A("整句起伏 Δ %+.2f 半音（%.0f%% 为正，p = %.2f，**不显著**）；"
      % (med(dv), 100.0 * sum(1 for x in dv if x > 0) / len(dv), sign_p(sum(1 for x in dv if x > 0), len(dv))))
    A("副词滑幅 Δ %+.2f 半音（%.0f%% 为正，p = %.3f）。"
      % (med(da), 100.0 * sum(1 for x in da if x > 0) / len(da), sign_p(sum(1 for x in da if x > 0), len(da))))
    A()
    A("合起来就是一句话：**`<pitch, semitones=9>` 只把目标词整体抬上去，没有改动它的轮廓。**")
    A("这和之前「pitch 只能整体移调、不能先压后冲」是同一件事——现在有了听感阈值标定的独立测量佐证。")
    A("而 `loc`（词级音高偏移）那边确实有 87 分位的效果，说明**抬升是真的，轮廓是空的**。")
    A()

    # ---------- 五 ----------
    A("## 五、节奏：其实已经对齐了")
    A()
    A("Prosogram 的 prosodic profile 顺带给了 nPVI（相邻音节时长的成对变异），这是真正的节奏指标。")
    A()
    A("| 指标 | 真人 p50 | 旁白 p50 |")
    A("|---|---|---|")
    for k, lab in (("npvi_nucldur", "nPVI（核时长）"), ("npvi_sylldur", "nPVI（音节时长）")):
        A("| %s | %s | %s |" % (lab,
                                f1(med([p.get(k) for p in P if p["side"] == "human"]), 1),
                                f1(med([p.get(k) for p in P if p["side"] == "narr"]), 1)))
    A("| nPVI（元音时长） | n/a | n/a |")
    A()
    A("元音时长算不出来是因为我们只给了 `syll` 层、没有音素层——Prosogram 需要 `phon` 层才能切元音。")
    A("要补这一项，得先做音素级对齐（cmudict 有 ARPAbet，可以拆），但那是另一件事。")
    A()
    A("**nPVI 核时长 71.7 vs 69.7 —— 已经对齐。**")
    A("之前说「我们把节奏抹平了」是错的口径：`rel` 只是**测量时**除以句中位，音频本身没动过，")
    A("所以 nPVI 这类基于原始时长的指标当然不受影响。被抹平的是**可比性处理**，不是节奏。")
    A()

    # ---------- 六 ----------
    A("## 六、音域：我们更宽，但三分之一是八度错误")
    A()

    def rng(f):
        f = sorted(f)
        if len(f) < 4:
            return None
        return 12 * math.log2(pct_at(f, .9) / pct_at(f, .1))

    def fold(f, ref):
        out = []
        for v in f:
            while v > ref * math.sqrt(2):
                v /= 2
            while v < ref / math.sqrt(2):
                v *= 2
            out.append(v)
        return out

    stat = {}
    for side in ("human", "narr"):
        raw, fo = [], []
        for t in T:
            if t["side"] != side:
                continue
            f = [x["f0_med"] for x in nuc[t["tid"]] if x["f0_med"] > 0]
            if len(f) < 4:
                continue
            raw.append(rng(f))
            fo.append(rng(fold(f, st.median(f))))
        raw = [x for x in raw if x]
        fo = [x for x in fo if x]
        stat[side] = (med(raw), med(fo), len(raw))
    dis = defaultdict(int)
    tot = defaultdict(int)
    for x in N:
        tot[x["side"]] += 1
        if x["discont"]:
            dis[x["side"]] += 1
    A("| 量 | 真人 | 旁白 |")
    A("|---|---|---|")
    A("| Prosogram PitchRange（ST） | %s | %s |" % (
        f1(med([p["pitch_range_st"] for p in P if p["side"] == "human"])),
        f1(med([p["pitch_range_st"] for p in P if p["side"] == "narr"]))))
    A("| 核中位 F0 的 p10–p90（ST） | %s | %s |" % (f1(stat["human"][0]), f1(stat["narr"][0])))
    A("| 八度折叠后同上（ST） | %s | %s |" % (f1(stat["human"][1]), f1(stat["narr"][1])))
    A("| 音高断点率 | %.1f%% | %.1f%% |" % (
        100.0 * dis["human"] / max(1, tot["human"]), 100.0 * dis["narr"] / max(1, tot["narr"])))
    A()
    A("折叠掉八度错误后仍差 **%.1f 倍**（%s vs %s ST），说明「我们音域更宽」是真差异，不是纯噪声。"
      % (stat["narr"][1] / stat["human"][1], f1(stat["narr"][1]), f1(stat["human"][1])))
    A("但旁白的音高断点率是真人的 %.1f 倍（气声导致跟踪跳八度），**绝对量不能直接当结论用**。"
      % (dis["narr"] / max(1, dis["human"])))
    A()

    # ---------- 七 ----------
    A("## 七、结论与接入方式")
    A()
    A("### 结论")
    A()
    A("1. **这层能跑**：产出率 72%，402/403 成功，可以进回环。")
    A("2. **不能当闸门**：对照组在「副词有滑率」上（+8.4 点）不低于交付版（+1.9 点），")
    A("   同 seed 配对的 McNemar 是 9:8 / 10:10 / 7:5——**标签在滑音通道上没有效果**。")
    A("   拿它做 PASS/FAIL 只会误杀。")
    A("3. **能当靶子**：真人句内最长词比其余词高 **+20.2 个点**（z=%.1f），" % zr)
    A("   上滑率高 **+10.1 个点**，而滑幅**不变大**。我们现在是 +1.9 点。")
    A("4. **最硬的一条**：`<pitch>` 抬的是**寄存器**，不是**轮廓**。")
    A("   同 seed 配对里，副词滑幅 Δ %+.2f 半音（p=%.2f），" % (med(da), sign_p(sum(1 for x in da if x > 0), len(da))))
    A("   有滑/上滑/下滑三个判定的不一致对全部落在 50/50。")
    A("   而 `loc`（词级音高偏移）那边是 87 分位——**抬升是真的，轮廓是空的**。")
    A()
    A("### 接入方式（不改现有闸门）")
    A()
    A("| 层 | 字段 | 用途 |")
    A("|---|---|---|")
    A("| 词级 | `adv_max_intra` / `adv_rel_dur` / `glide` | 报表 + 人耳复核时的定位 |")
    A("| take 级 | `adv_move` / `adv_up` / `adv_down` | 滑音类型，单条太噪，只做聚合 |")
    A("| take 级 | `npvi_nucldur` / `pitch_range_st` | 节奏与音域体检，不进判据 |")
    A("| 组级 | 副词有滑率 − 同句其他词有滑率 | **进度条**，真人 +20.2 点 |")
    A()
    A("**关键点：这个量只能在组级用。** 单条 take 的副词只有一个音节核，「有滑/没滑」是二值的，")
    A("方差大到没法判。真正能判的是**一批 take 的选择性**——真人 121 句的 +20.2 点，")
    A("我们 55 条交付版 +1.9 点，这个差距是稳的。")
    A()

    # ---------- 八 ----------
    A("## 八、产物与复现")
    A()
    A("| 文件 | 内容 |")
    A("|---|---|")
    A("| `_proso_tg.py` | 造 `syll` 层 TextGrid + 自定义 Pitch（floor 60 / ceil 250 / vt 0.20） |")
    A("| `E:/tool/praat/prosogram/praat_run.praat` | 无表单驱动 Prosogram |")
    A("| `_proso_parse.py` | 解析 `_data.txt` → 数据集（按时间把核映射回词实例） |")
    A("| `_proso.json` | %d take / %d 词 / %d 核 / %d profile |" % (len(T), len(W), len(N), len(P)))
    A("| `_proso_words.csv` | 词级平表（`tid`+`pos` 可与 `_align_words.csv` join） |")
    A("| `_proso_takes.csv` | take 级平表 |")
    A("| `_proso_nuclei.csv` | 核级明细（3153 行） |")
    A("| `_proso_profile.csv` | Prosogram 原生韵律画像（nPVI / 音域 / glissando 分布） |")
    A()
    A("**已知限制**：")
    A()
    A("- `_data.txt` 的 `rowLabel` 只有时间，没有音节标签（Prosogram 读了 `syll` 层但不把标签写进这张表）")
    A("  ⇒ 核到词的映射按 `nucl_t1` 落点，落在间隙时取最近词边界。")
    A("- 我们用的是**词边界 + cmudict 音节数**等分出来的 `syll` 层，不是真正的音节边界；")
    A("  多音节词内部切分是近似的。单音节词（副词大多是）不受影响。")
    A("- 气声重的条目（HNR < 3 dB）跟踪不稳，音高断点率 10% vs 真人 4%。")
    A("- 许可 CC BY-NC：内部测量可以，对外分发输出需另议。")

    open(J("_proso_report.md"), "w", encoding="utf-8").write("\n".join(OUT) + "\n")
    print("→ _proso_report.md  %d 行" % len(OUT))


if __name__ == "__main__":
    main()
