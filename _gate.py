# -*- coding: utf-8 -*-
"""门禁：判断一条候选音频的「主重音落位」是否可信。

    python _gate.py --dir _wpt_out --json _mt_gate.json
    python _gate.py --uid N0001
    python _gate.py --dir _wpt_out --only ARTIFACT

三档输出（不是二分类）：
  PASS      可信，直接用
  ARTIFACT  是测量伪影 / 明显落错，重生
  MANUAL    声学证据不足以判定，交人工

为什么必须有三档：95 候选实测里 8.4% 属于「语义上说得通、声学上分不清」
（句首第 2 词、内容词紧邻停顿），这类交给 LLM 投票也一致错，只能人工。

判据顺序（先硬后软）：
  1. 对齐词数 < 4            → MANUAL(short)      分位统计不成立
  2. sep < SEP_MIN           → ARTIFACT(sep_low)  整体重音落在虚词上
  3. top1 是硬功能词
       pos<=1                → ARTIFACT(func_head) 句首 F0 重置
       紧邻停顿               → ARTIFACT(func_punct) 边界效应
       句中                   → MANUAL(func_mid)   可能是对比焦点
  4. top1 是「可合法承担焦点」的词
       两侧都是标点            → ARTIFACT(isolated)  "insects, too," 模式
       其他                   → PASS(legit_focus)   not / no / that / then
  5. top1 是内容词
       pos<=1                → MANUAL(head_content) 无法分辨抬高还是真重音
       紧邻停顿               → MANUAL(punct_content)
       其他                   → PASS(content)

sep 的定义与 _verify_accent.py 一致（内容词分位均值 − 功能词分位均值），
以保证历史数字可比。
"""
import argparse
import difflib
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, "G:/_setup")
import _predict as P
from _verify_accent import read_prom, pct_rank, align

PROM_DIR = "G:/_setup/_wpt_out"
SEP_MIN = 0.15          # 全库 sep 分布 p6 左右；比它低说明内容词和功能词几乎没分离
GAP_TIE = 0.20          # top1 与最强内容词差 ≤0.2 视为并列，不算落错
GAP_HARD = 0.80         # 虚词 top1 必须比最强内容词高出这么多，才算「明显落错」
COV_MIN = 0.80          # 对齐覆盖率下限：低于此判为吞字 / 漏词
PUNCT = set(".,;:!?-\"'()[]—–")

# 硬功能词：测成 top1 基本是伪影（冠词 / 介词 / 助动词 / 主格代词 / 纯连词 / 存在句 there）
FUNC_HARD = set("""
a an the
and or but nor so yet for if because as than while though although unless whether
i you he she it we they me him her us them
my your his its our their mine yours hers ours theirs
am is are was were be been being do does did done have has had having
will would shall should can could may might must ought
to of in on at by with from into onto about over under between among through
during before after above below across against along around behind beyond
beside besides despite except inside outside since till until upon within without toward towards via per
up down out off
there once
""".split())

# 可合法承担焦点的功能词：否定 / 指示 / 时间 / 程度 / 疑问 / 附加焦点
FOCUS_LEGIT = set("""
no not never none nothing nobody neither
that this these those
then here now today tomorrow yesterday
too only just even still ever always also
all any both each few more most other some such very own same
why how when where who what which
""".split())


def classify_word(w):
    """→ 'hard' | 'focus' | 'content'"""
    w = w.lower().strip(".,;:!?\"'()[]—–")
    if not w:
        return "content"
    if w in FOCUS_LEGIT:
        return "focus"
    if w in FUNC_HARD:
        return "hard"
    return "content"


def _neighbors(pred_words, pi):
    """返回 (前一个 token 是否标点, 后一个 token 是否标点)。用原始文本序列。"""
    prev_p = pi > 0 and pred_words[pi - 1]["punct"]
    next_p = pi + 1 < len(pred_words) and pred_words[pi + 1]["punct"]
    return prev_p, next_p


def expand(words):
    """把 low-lying / well-known 拆成两个 token 参与对齐。

    _predict 把 'low-lying' 当一个词，ASR 输出 'low' 'lying' 两个，
    difflib 对不上，覆盖率就假性掉到 0.75（N0118 实测）。
    返回 (tokens, back) —— back[i] 是 token i 对应的原词索引。
    """
    toks, back = [], []
    for i, w in enumerate(words):
        parts = [p for p in re.split(r"[-–—]", w) if p]
        if not parts:
            parts = [w]
        for p in parts:
            toks.append(p)
            back.append(i)
    return toks, back


def _norm(s):
    """去撇号、大小写、非字母数字。father's → fathers，Banker's → bankers。"""
    return "".join(c for c in (s or "").lower().replace("\u2019", "").replace("\u2018", "")
                   if c.isalnum())


def fuzzy_find(word, pred_w):
    """top1 没精确对齐上时，找原文里最相似的词。

    实测的 unaligned 全是 ASR 拼写差异，不是发音缺陷：
      Kingshaw → King + Shaw、father's → father、fifty-one → 51、posed → imposed
    这些都是假阳性，必须救回来，否则 3.4% 的候选被误判成待人工。
    """
    t = _norm(word)
    if not t:
        return None
    best, bi = 0.0, None
    for i, x in enumerate(pred_w):
        c = _norm(x["w"])
        if not c:
            continue
        r = difflib.SequenceMatcher(None, t, c).ratio()
        if c.startswith(t) or t.startswith(c):
            r = max(r, 0.85)          # 前缀关系：King ⊂ Kingshaw
        if r > best:
            best, bi = r, i
    return bi if best >= 0.72 else None


def expand_pairs(pred_w, obs_w):
    """展开连字符后对齐，返回 [(pred_idx, obs_idx)]，索引指回原词。"""
    pt, pb = expand([x["w"] for x in pred_w])
    ot, ob = expand([w for w, _p, _b in obs_w])
    out, seen = [], set()
    for pi, oi in align(pt, ot):
        p, o = pb[pi], ob[oi]
        if (p, o) in seen:
            continue
        seen.add((p, o))
        out.append((p, o))
    out.sort()
    return out


def _norm_apos(s):
    """弯引号统一成直引号：can’t / can't 是同一个词，不能因为编码差异判成两个。"""
    return s.replace("\u2019", "'").replace("\u2018", "'")


def _merge_contractions(obs_w):
    """把 ASR 拆开的缩写词合回去。

    Praat 的 word tier 会把 `can't` 切成 `can` + `'t`、`I've` 切成 `I` + `'ve`，
    而参考侧 `_predict` 输出的是整词。不合并的话每个缩写都少一个对齐词，
    覆盖率被系统性压低（N0324 实测 16 词里假性丢 5 词，cov 0.688 -> 判吞字）。
    """
    out = []
    for w, p, b in obs_w:
        if w.startswith("'") and len(w) > 1 and out:
            pw, pp, pb = out[-1]
            out[-1] = (pw + w, pp, pb)
        else:
            out.append((w, p, b))
    return out


def _merge_split_words(pred_w, obs_w):
    """ASR 会把一个词切成两个（Kingshaw -> King Shaw，windowledges -> window ledges）。

    只在「相邻几个 obs 词拼起来正好等于某个 ref 词、且首词单独不等于任何 ref 词」时合并，
    避免把普通的相邻词误并（例如 the + best 不会命中任何 ref 词）。
    """
    ref = {_norm_apos(x["w"]).lower() for x in pred_w}
    out, i = [], 0
    n = len(obs_w)
    while i < n:
        done = False
        for k in (3, 2):
            if i + k <= n:
                # 不要碰 `glass` + `-eyed` 这种：连字符拆分由 expand() 负责，
                # 这里再合并会让两侧的展开粒度不一致（N0170 实测覆盖率反而从 0.833 掉到 0.667）
                if any(obs_w[i + j][0].startswith("-") for j in range(1, k)):
                    continue
                cand = "".join(obs_w[i + j][0] for j in range(k))
                if _norm_apos(cand).lower() in ref and _norm_apos(obs_w[i][0]).lower() not in ref:
                    # prominence 取合并段里的最大值：这个词整体的重读程度，
                    # 用首词的值会系统性低估（N0690/N0322 实测因此误判 sep_low）
                    pr = max(obs_w[i + j][1] for j in range(k))
                    out.append((cand, pr, obs_w[i][2]))
                    i += k
                    done = True
                    break
        if not done:
            out.append(obs_w[i])
            i += 1
    return out


def _split_obs_by_ref(pred_w, obs_w):
    """反向：ASR 把两个词合成一个（all right -> alright），按 ref 的词边界拆开。

    只在「该 obs 词本身不是任何 ref 词、且正好等于两个相邻 ref 词的拼接」时拆，
    不会把普通词拆坏。
    """
    ref = [_norm_apos(x["w"]).lower() for x in pred_w]
    refset = set(ref)
    joint = {ref[i] + ref[i + 1]: i for i in range(len(ref) - 1)}
    out = []
    for w, p, b in obs_w:
        lw = _norm_apos(w).lower()
        if lw not in refset and lw in joint:
            i = joint[lw]
            out.append((pred_w[i]["w"], p, b))
            out.append((pred_w[i + 1]["w"], p, b))
        else:
            out.append((w, p, b))
    return out


# 口语合并拼写 -> 两个词。这类词 ASR 常写成一个 token，参考文本是两个词，
# 不展开就白丢一个对齐位（N0856 实测 all right -> alright，cov 0.778 被判吞字）。
MERGED = {
    "alright": ("all", "right"),
    "gonna": ("going", "to"),
    "gotta": ("got", "to"),
    "wanna": ("want", "to"),
    "kinda": ("kind", "of"),
    "outta": ("out", "of"),
    "lemme": ("let", "me"),
    "gimme": ("give", "me"),
    "dunno": ("don't", "know"),
}


def _expand_merged(obs_w):
    out = []
    for w, p, b in obs_w:
        pair = MERGED.get(_norm_apos(w).lower())
        if pair:
            out.append((pair[0], p, b))
            out.append((pair[1], p, b))
        else:
            out.append((w, p, b))
    return out


def gate_one(text, obs_rows):
    """obs_rows: read_prom 的输出 [(word, prominence, boundary)]。返回 dict 或 None。"""
    # 参考文本里可能存在「连字符被删且未补空格」的粘连数字词（EPUB 预处理副作用，
    # 实测 N0187 为 `thirtyseven`），而 ASR 正常输出 `thirty-seven` 两个词。
    # 不先补空格，对齐必然少一词，覆盖率假性下降 -> 被判吞字并反复重生成。
    try:
        from _asr_norm import fix_text
        text = fix_text(text)
    except Exception:
        pass
    pred = P.predict(text)
    pred_w = [x for x in pred["words"] if not x["punct"]]
    for x in pred_w:
        x["w"] = _norm_apos(x["w"])
    obs_w = [(_norm_apos(w), p, b) for w, p, b in obs_rows if w not in PUNCT]
    obs_w = _merge_contractions(obs_w)
    obs_w = _merge_split_words(pred_w, obs_w)
    obs_w = _split_obs_by_ref(pred_w, obs_w)
    obs_w = _expand_merged(obs_w)
    if not pred_w or not obs_w:
        return None

    pairs = expand_pairs(pred_w, obs_w)
    if not pairs:
        return None
    if len(pairs) < max(3, int(0.5 * len(obs_w))):
        return None

    proms = [p for _w, p, _b in obs_w]

    # ---- sep：沿用 _verify_accent 的口径（prom==0 为功能词）
    ct_q, fn_q = [], []
    for pi, oi in pairs:
        pv = pred_w[pi]["prom"]
        if pv is None:
            continue
        q = pct_rank(proms, obs_w[oi][1])
        (fn_q if pv == 0 else ct_q).append(q)
    sep = (sum(ct_q) / len(ct_q) - sum(fn_q) / len(fn_q)) if (ct_q and fn_q) else None

    # ---- top1（观测）
    ti = max(range(len(obs_w)), key=lambda i: proms[i])
    top_word = obs_w[ti][0]
    top_p = obs_w[ti][1]
    top_pos = ti

    # 映射到原文位置（取最强的对齐候选；同一 obs 词可能对上多个 pred 词）
    cand = [pi for pi, oi in pairs if oi == ti]
    pi = cand[0] if cand else None
    if pi is None:
        pi = fuzzy_find(top_word, pred_w)
        fuzzy = pi is not None

    # top1 与最强内容词的差
    content_p = [obs_w[oi][1] for pi2, oi2 in pairs
                 for oi in [oi2] if classify_word(pred_w[pi2]["w"]) == "content"]
    best_content = max(content_p) if content_p else None
    gap = (top_p - best_content) if best_content is not None else None

    kind = classify_word(top_word)
    n = len(pairs)
    coverage = n / float(max(1, len(pred_w)))
    fuzzy = False

    def out(verdict, code, **kw):
        d = dict(verdict=verdict, code=code, sep=None if sep is None else round(sep, 3),
                 top1=top_word, kind=kind, pos=top_pos, n=n,
                 cov=round(coverage, 3), fuzzy=fuzzy,
                 p=round(top_p, 2),
                 gap=None if gap is None else round(gap, 2))
        d.update(kw)
        return d

    # 覆盖率：ASR 对齐到的词数 / 原文词数。吞字、漏词、念错都会让它掉下来。
    # 这是唯一不依赖韵律测量的硬判据，优先级最高。
    if coverage < COV_MIN:
        return out("ARTIFACT", "miss_words")
    if n < 4:
        # 分位统计在 3 个词上不成立。这是「门禁不适用」，不是「不合格」，
        # 短句的验收归 mt_score.py（声纹 / 语速 / 时长 / 吐字），不归韵律门禁。
        return out("SKIP", "n/a_short")
    if sep is not None and sep < SEP_MIN:
        return out("ARTIFACT", "sep_low")

    if pi is None:
        return out("MANUAL", "unaligned")

    prev_p, next_p = _neighbors(pred["words"], pi)
    # gap 只在 top1 不是内容词时才有判别力：top1 自己是内容词时 gap 恒为 0
    tie = gap is not None and gap <= GAP_TIE

    if kind == "hard":
        if tie:
            return out("PASS", "tie_func")
        if gap is not None and gap < GAP_HARD:
            # 和最强内容词差不多重 —— 不足以判缺陷
            return out("PASS", "weak_func")
        if top_pos <= 1:
            return out("ARTIFACT", "func_head")
        if prev_p or next_p:
            return out("ARTIFACT", "func_punct")
        return out("MANUAL", "func_mid")

    if kind == "focus":
        # 「insects, too,」模式：功能词被两个标点夹住，且明显高于最强内容词
        if prev_p and next_p and gap is not None and gap >= GAP_HARD:
            return out("ARTIFACT", "isolated")
        return out("PASS", "legit_focus")

    # content
    # 2026-10-25 位置基线实测：句首 top1 残差 +2.633、句中 top1 +2.562，
    # 句首并没有“凭空多出来的分”，所以内容词在句首被强调不能算缺陷。
    # 短语末内容词同理（英语默认的 nucleus 位置）。这两类一律放行。
    if top_pos <= 1:
        return out("PASS", "content_head")
    if prev_p or next_p:
        return out("PASS", "content_punct")
    return out("PASS", "content")


def load_plan_texts():
    """uid → text，来自 plan（回环的权威文本）。"""
    out = {}
    for p in ["B:/mt-tts/data/plan/mt_plan3b.json", "G:/_setup/_mt_plan3b.json"]:
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        items = d if isinstance(d, list) else d.get("items", [])
        for it in items:
            out.setdefault(str(it.get("id")), it.get("text", ""))
        break
    return out


def run_dir(dirpath, plan=None, only_verdict=None, uids=None):
    plan = plan or load_plan_texts()
    rows = []
    skipped = []
    for f in sorted(os.listdir(dirpath)):
        if not f.endswith(".prom"):
            continue
        base = f[:-5]
        if "__" not in base:
            continue
        seed_dir, uid = base.split("__", 1)
        if uids and uid not in uids:
            continue
        text = plan.get(uid)
        if not text:
            skipped.append((base, "no_text"))
            continue
        r = gate_one(text, read_prom(os.path.join(dirpath, f)))
        if not r:
            skipped.append((base, "align_fail"))
            continue
        # 统一 seed 表示为纯数字（"42" / "1234"）/ "rate"，供回环比对是否用过
        r.update(uid=uid, seed=seed_dir.replace("_mt_raw_s", "").replace("_mt_raw_", ""), file=f)
        if only_verdict and r["verdict"] != only_verdict:
            continue
        rows.append(r)
    return rows, skipped


def summarize(rows):
    if not rows:
        print("无数据")
        return {}
    vc = Counter(r["verdict"] for r in rows)
    n = len(rows)
    print("=== 门禁分档（%d 个候选）===" % n)
    for v in ("PASS", "ARTIFACT", "MANUAL", "SKIP"):
        k = vc.get(v, 0)
        if not k:
            continue
        print("  %-9s %4d  %5.1f%%  %s" % (v, k, 100.0 * k / n, "█" * int(60 * k / n)))
    print("\n=== 判据分布 ===")
    for code, k in Counter(r["code"] for r in rows).most_common():
        vs = Counter(r["verdict"] for r in rows if r["code"] == code)
        print("  %-14s %4d  %5.1f%%   %s"
              % (code, k, 100.0 * k / n, dict(vs)))

    # 按句统计：任一批次不过就算这单元有问题
    by = {}
    for r in rows:
        by.setdefault(r["uid"], []).append(r)
    unit_verdict = {}
    for u, rs in by.items():
        vs = {r["verdict"] for r in rs}
        for v in ("PASS", "SKIP", "MANUAL", "ARTIFACT"):
            if v in vs:
                unit_verdict[u] = v
                break
    uc = Counter(unit_verdict.values())
    print("\n=== 按单元（有任一 PASS 即算该单元可交付）：%d 个单元 ===" % len(by))
    for v in ("PASS", "SKIP", "ARTIFACT", "MANUAL"):
        k = uc.get(v, 0)
        if not k:
            continue
        print("  %-9s %4d  %5.1f%%" % (v, k, 100.0 * k / max(1, len(by))))
    print("\n=== 候选数分布（每单元几个候选）===")
    print("  ", dict(Counter(len(v) for v in by.values())))
    return dict(candidates=n, verdicts=dict(vc), codes=dict(Counter(r["code"] for r in rows)),
                units=dict(uc), unit_of=unit_verdict)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=PROM_DIR)
    ap.add_argument("--uid", default=None)
    ap.add_argument("--only", default=None, help="PASS / ARTIFACT / MANUAL")
    ap.add_argument("--json", default=None)
    ap.add_argument("--show", type=int, default=0, help="打印前 n 条明细")
    a = ap.parse_args()

    uids = {a.uid} if a.uid else None
    rows, skipped = run_dir(a.dir, uids=uids, only_verdict=a.only)
    if skipped:
        print("跳过 %d 个（%s）" % (len(skipped), Counter(x[1] for x in skipped)))
    summarize(rows)

    if a.show:
        print("\n=== 明细（前 %d 条）===" % a.show)
        for r in rows[:a.show]:
            print("  %s/%s  %-8s %-14s top1=%-10s pos=%2d n=%2d sep=%+.2f gap=%s"
                  % (r["uid"], r["seed"], r["verdict"], r["code"], r["top1"],
                     r["pos"], r["n"], r["sep"] if r["sep"] is not None else 0,
                     r["gap"]))

    if a.json:
        json.dump(rows, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n写入 %s" % a.json)


if __name__ == "__main__":
    main()
