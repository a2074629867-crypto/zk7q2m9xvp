# -*- coding: utf-8 -*-
"""_align_lib.py —— 旁白 take 与真人母带的**唯一测量核**。

## 为什么要有一个核

此前同一件事有三份实现，而且互相打架：

  _adv_prom.target_row        dur_x = sps / 其余内容词 sps 中位
  _anchor_analyze.words_stat  rel   = sps / 全部内容词 sps 中位（含自身）
  _anchor_ours.json           rel   = 又一份 ad-hoc 快照，无脚本写入

同一句两个词时，「含自身」与「不含自身」差 3~6%；
`_anchor_report.md` 写 rel p50 = 1.00，而 `_anchor_ours.json` 实际是 0.940。
两份数字都自称权威，无法判定谁对。

⇒ 本模块是**唯一**的词级测量实现。真人侧与旁白侧都只走 `measure_take()`，
字段、分母、音节校正、位置标记全部一致。

## 口径（五条硬规则）

1. `rel` 分母 = **句内全部内容词 sps 中位（含自身）**，与真人原有定义一致。
2. `rel_z` 以**句内归一的 `rel`** 为底，只校正音节数：
       rel_z = (log(rel) - A - B*log(nsyl)) / SD
   A/B/SD 只能用**真人**拟合。★ 禁止用绝对 sps 拟合 ——
   我们比真人快 2.1 倍，全体 log(sps) 低 0.74，rel_z 会被整体平移约 -1.9σ。
3. 内容词 < 4 的 take 照测，标 `low_context=True`，`rank` 不进汇总。
4. 每条 take 记录 wav 的 md5 与 prom 的 mtime，血缘可查（wav 换了 prom 没换 = 第 4 次教导）。
5. `loc` 两侧同函数同定义，真人 p50 = 0.81 是定义自带的偏置，两侧可直接比。

## 真人侧过滤（与 _anchor_analyze.py 逐条一致，改动会破坏 159 句/931 词的复现）

  无 prom → 测量异常 → 空 → 漏词（|原文词数-ASR词数| > 1）
  → 内容词 < MIN_WORDS(4) → 任一词 sps > 3×句中位（整句弃）
"""
import hashlib
import json
import math
import os
import re
import statistics as st

import _adv_check as AC
import _adv_prom as P

ROOT = os.path.dirname(os.path.abspath(__file__))


def find_data(name):
    """定位数据文件：脚本同目录优先，回落到仓库布局 <repo>/data/align/。

    场景：G:/_setup 是运行目录（文件就在旁边）；B:/mt-tts 里脚本在 scripts/、
    数据在 data/align/。不加这层回落，新检出直接跑 judge_cand 会 FileNotFoundError。
    """
    p = os.path.join(ROOT, name)
    if os.path.exists(p):
        return p
    for rel in (("..", "data", "align"), ("..", "..", "data", "align")):
        cand = os.path.abspath(os.path.join(ROOT, *rel, name))
        if os.path.exists(cand):
            return cand
    return p


BASE_JSON = find_data("_align_baseline.json")

# ---- 真人侧过滤参数（改这里会让 159 句/931 词复现失败）----
MIN_WORDS = 4
SPS_RATIO_MAX = 3.0

# ---- 通用 ----
LOW_CONTEXT_N = 4          # 内容词 < 4 → low_context（仍测，rank 不进汇总）
NEAR_K = 4                 # rel_nb 的邻居数


# ============================ 工具 ============================

def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def quant(v, qs=(5, 25, 50, 75, 90, 95)):
    """分位表；空列表返回 None。"""
    v = [x for x in v if x is not None]
    if not v:
        return None
    v = sorted(v)
    return {("p%d" % q): float(_pct_at(v, q)) for q in qs}


def _pct_at(sorted_v, q):
    """线性插值分位（与 numpy 默认一致，但不引 numpy）。"""
    if not sorted_v:
        return None
    if len(sorted_v) == 1:
        return sorted_v[0]
    pos = (len(sorted_v) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_v) - 1)
    frac = pos - lo
    return sorted_v[lo] * (1 - frac) + sorted_v[hi] * frac


def pct_of(value, sorted_vals):
    """value 在 sorted_vals 中的百分位（0~100，用中位秩）。"""
    if value is None or not sorted_vals:
        return None
    n = len(sorted_vals)
    below = sum(1 for x in sorted_vals if x < value)
    equal = sum(1 for x in sorted_vals if x == value)
    return 100.0 * (below + 0.5 * equal) / n


def describe(v, name=""):
    q = quant(v)
    if not q:
        return "%s 无数据" % name
    return ("%s n=%d  p5 %.2f  p25 %.2f  p50 %.2f  p75 %.2f  p90 %.2f  p95 %.2f"
            % (name, len([x for x in v if x is not None]), q["p5"], q["p25"],
               q["p50"], q["p75"], q["p90"], q["p95"]))


# ============================ 测量 ============================

def measure_take(wav, prom, text, adv=None, cws=None):
    """测一条 take，返回 {n_content, med_sps, synthetic_share, words:[...]}。

    words 里每个词保留 `_adv_prom.measure_one` 的全部原始字段
    （t0/t1/voiced/speech/share/rms_x/lin/peak/raw_peak/p90/n_fr/synthetic），
    再补 9 个派生字段（span/rel/rel_ex/rel_nb/rank/pos/last/is_adv）。

    `cws` 可传入已经测好的 `measure_one` 结果，避免重复解码（真人侧过滤链要复用）。
    `rel_z` 不在这里算 —— 它依赖真人拟合的系数，由 `apply_rel_z()` 统一填。
    """
    if cws is None:
        cws = P.measure_one(wav, prom, text)
    if not cws or len(cws) < 2:
        return None
    sps_all = [w["sps"] for w in cws if w.get("sps")]
    if len(sps_all) < 2:
        return None
    med = float(st.median(sps_all))
    if med <= 0:
        return None

    centers = [(w["t0"] + w["t1"]) / 2.0 for w in cws]
    out = []
    for i, w in enumerate(cws):
        sps = w["sps"]
        others = [q["sps"] for j, q in enumerate(cws) if j != i and q.get("sps")]
        near = sorted((j for j in range(len(cws)) if j != i),
                      key=lambda j: abs(centers[j] - centers[i]))[:NEAR_K]
        nb = [cws[j]["sps"] for j in near if cws[j].get("sps")]

        d = dict(w)
        d["span"] = round(w["t1"] - w["t0"], 3)
        d["rel"] = sps / med
        d["rel_ex"] = (sps / st.median(others)) if others else None
        d["rel_nb"] = (sps / st.median(nb)) if nb else None
        d["rank"] = 1 + sum(1 for q in cws if q.get("sps", 0) > sps)
        d["pos"] = i + 1
        d["last"] = i >= len(cws) - 2
        d["is_adv"] = bool(adv) and d["key"] == AC.norm(adv)
        d["rel_z"] = None                     # 待 apply_rel_z 填
        # 只保留可 JSON 化的类型
        for k, v in list(d.items()):
            if isinstance(v, (bool, int, str)) or v is None:
                continue
            try:
                d[k] = None if v is None else float(v)
            except (TypeError, ValueError):
                pass
        out.append(d)

    return dict(n_content=len(cws),
                med_sps=round(med, 6),
                synthetic_share=round(sum(1 for w in cws if w.get("synthetic")) / len(cws), 3),
                words=out)


# ============================ 基线 ============================

def fit_baseline(records, tag="human"):
    """用真人记录拟合 `log(rel) = A + B*log(nsyl)`，并算各层分位。

    ★ 底必须是 `rel`（句内归一），不是 `sps`。
    """
    ws = [w for r in records for w in r["words"]]
    pairs = [(math.log(w["nsyl"]), math.log(w["rel"]))
             for w in ws if w.get("rel") and w["rel"] > 0 and w.get("nsyl")]
    n = len(pairs)
    if n < 30:
        raise SystemExit("基线样本不足：%d" % n)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    b = sxy / sxx
    a = my - b * mx
    res = [p[1] - (a + b * p[0]) for p in pairs]
    sd = math.sqrt(sum(v * v for v in res) / (n - 1))

    bl = dict(tag=tag, n_words=n, n_recs=len(records),
              A=a, B=b, SD=sd,
              r=float(sxy / math.sqrt(sxx * sum((p[1] - my) ** 2 for p in pairs))))
    return bl


def rel_z_value(rel, nsyl, bl):
    """单个词的 rel_z。rel 必须是句内归一的 `sps/句中位`，不是绝对 sps。"""
    if not rel or rel <= 0:
        return None
    return (math.log(rel) - bl["A"] - bl["B"] * math.log(max(1, nsyl))) / bl["SD"]


def apply_rel_z(record, bl):
    """给一条记录里所有词填 rel_z（就地修改）。"""
    for w in record["words"]:
        w["rel_z"] = rel_z_value(w.get("rel"), w.get("nsyl") or 1, bl)
    return record


def build_reference(records):
    """真人参照分布：全体 / 逐音节 / 逐位置。"""
    ws = [w for r in records for w in r["words"]]

    def _pack(sub):
        return dict(
            n=len(sub),
            rel=_pvals([w["rel"] for w in sub]),
            rel_z=_pvals([w["rel_z"] for w in sub]),
            loc=_pvals([w["loc"] for w in sub]),
            sps=_pvals([w["sps"] for w in sub]),
            rel_sorted=sorted([w["rel"] for w in sub if w.get("rel")]),
            relz_sorted=sorted([w["rel_z"] for w in sub if w.get("rel_z") is not None]),
            loc_sorted=sorted([w["loc"] for w in sub if w.get("loc") is not None]),
        )

    ref = dict(all=_pack(ws), by_nsyl={}, by_pos={})
    for k in sorted({w["nsyl"] for w in ws if w.get("nsyl")}):
        ref["by_nsyl"][str(k)] = _pack([w for w in ws if w.get("nsyl") == k])
    for k, want in (("mid", False), ("end", True)):
        ref["by_pos"][k] = _pack([w for w in ws if bool(w.get("last")) == want])
    # 句内最长词 / 句内最高 loc 词（真人「重读」的两种形态）
    top_rel = [min(r["words"], key=lambda w: w["rank"]) for r in records if r["words"]]
    top_loc = []
    for r in records:
        c = [w for w in r["words"] if w.get("loc") is not None]
        if len(c) >= 4:
            top_loc.append(max(c, key=lambda w: w["loc"]))
    ref["top_rel"] = _pack(top_rel)
    ref["top_loc"] = _pack(top_loc)
    return ref


def _pvals(v):
    q = quant(v)
    return q if q else dict(p5=None, p25=None, p50=None, p75=None, p90=None, p95=None)


def save_baseline(bl, path=BASE_JSON):
    json.dump(bl, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path


def load_baseline(path=BASE_JSON):
    if not os.path.exists(path):
        raise SystemExit("缺 %s —— 先跑 _align_build.py" % path)
    return json.load(open(path, encoding="utf-8"))


# ============================ 自由函数 ============================

def human_filter_reason(wav, prom, text, asr_words=None):
    """复刻 _anchor_analyze.py 的过滤链。返回 (reason|None, measured)。

    reason 命中即该句被弃；None 表示通过。
    """
    if not os.path.exists(prom):
        return "no prom", None
    try:
        m = P.measure_one(wav, prom, text)
    except Exception as e:
        return "measure " + str(e)[:40], None
    if not m:
        return "empty", None

    if asr_words is not None:
        # ★ 2026-10-27 修正两处历史 bug：
        #   ① 旧代码查 ASR 用相对路径，而 _anchor_asr.json 的键是**绝对路径** ⇒ 永远查不到，
        #      n_asr 恒为 0，`if n_asr and ...` 让整条漏词过滤**从未生效**；
        #   ② 旧代码数原文用 `replace(',',' ').replace('.',' ').split()`，逗号句号之外的
        #      标点（; ! ? — 引号）会被算成词，导致 diff 虚高。
        #   现在两处都按「字母序列」计数，contraction 算一个词。
        n_src = len([x for x in re.split(r"[^A-Za-z']+", text) if x])
        n_asr = len([w for w in asr_words if w and re.search(r"[A-Za-z]", str(w))])
        if n_asr and abs(n_src - n_asr) > 1:
            return "漏词 原文%d/ASR%d" % (n_src, n_asr), None

    if len(m) < MIN_WORDS:
        return "内容词仅 %d" % len(m), None

    sps = [w["sps"] for w in m if w.get("sps")]
    if len(sps) < 3:
        return "sps 异常", None
    med = st.median(sps)
    if med <= 0:
        return "sps 异常", None
    if any(v > SPS_RATIO_MAX * med for v in sps):
        return "sps 异常", None
    return None, m
