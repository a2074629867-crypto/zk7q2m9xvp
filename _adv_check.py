# -*- coding: utf-8 -*-
"""副词「该慢有没有慢」验证器。

判据来源（全部可复算）：
  - 逐词起止时间：wpt 产出的 .prom 第 2/3 列（由 ASR 词级时间戳切分）
  - 句内每音节时长基线：句内所有词 dur/syl 的中位数
  - rel = (副词 dur / 副词音节数) / 句内每音节中位
        rel 大 ⇒ 该词相对同句其它词被拉长 ⇒ 「真的慢了」
  - prom：wpt 的 prominence（已实测 ρ=0.712 由词时长驱动，正是本任务要的信号）

三档：
  MISSING  该词在 prom 里根本不存在（ASR 未识别）→ 需人工/重生
  SKIPPED  rel < SKIP_MAX（时长几乎为零，被吞）
  FAST     SKIP_MAX ≤ rel < SLOW_MIN（读出来了但没慢）
  SLOWED   rel ≥ SLOW_MIN（真的慢了）
"""
import argparse
import json
import os
import re
import statistics
import sys

sys.path.insert(0, "G:/_setup")
import _adv_align
from collections import Counter, defaultdict

ROOT = "G:/_setup"
PLAN = "B:/mt-tts/data/plan/mt_plan3b.json"
PROM_DIR = os.path.join(ROOT, "_wpt_out")

# ★ 主判据改成绝对语速 sps = dur / 音节数（秒/音节），不用 rel。
# 原因：rel 是「相对句内每音节中位」，英语里副词本来就该接近句内平均，
# 所以 rel 中位必然是 1.000，无法区分「正常」与「重读」。
# 实测（98 个副词实例）sps 分布：p10 0.160 / p50 0.240 / p75 0.320 / p90 0.440。
# 端到端验证（同 seed 只改一处）：原文 0.112~0.160 → 破折号版 0.288~0.340。
SPS_FLAT = 0.180     # 低于此值：被压扁 / 该慢没慢
SPS_SLOW = 0.280     # 高于此值：确实慢了
REL_REF = 1.20       # 仅作参考字段，不参与判决

# -ly 里不是「方式副词」的常见词（名词/形容词/动词）
NOT_ADV = set("""
family reply apply supply rely belly jelly fly holy ugly silly lily ally rally
monopoly melancholy assembly anomaly italy july polly nelly billy willy dolly
holly kelly sally tilly emily cecily multiply imply comply deny
body study carry marry worry try dry cry fry pry spy shy sly ply buy guy say
day way may pay lay play stay gray grey they key eye valley alley journey money
honey monkey donkey chimney hockey jockey trolley volley barley bailey parsley
galley early daily weekly monthly yearly hourly friendly lovely lonely likely
unlikely deadly lively elderly orderly cowardly kindlily
""".split())

VOW = set("aeiouy")


_CMU = None


def _cmu():
    """懒加载 CMU 发音词典（126k 词）。装了就用它数音节，没装退回启发式。"""
    global _CMU
    if _CMU is None:
        try:
            import cmudict
            _CMU = cmudict.dict()
        except Exception:
            _CMU = {}
    return _CMU


def syllables(w):
    """音节数：优先 CMU 词典（数带重音数字的音素），否则退回元音组启发式。

    启发式系统性高估：completely 数成 4（真值 3）、carefully 4（真值 3）、
    deliberately 6（真值 5），导致 sps 被低估约 25%。
    """
    key = re.sub(r"[^a-z']", "", w.lower())
    d = _cmu()
    if key and key in d:
        # 取第一个发音，数带重音标记（0/1/2）的音素
        return max(1, sum(1 for p in d[key][0] if p[-1].isdigit()))

    w2 = re.sub(r"[^a-z]", "", w.lower())
    if not w2:
        return 1
    n, prev = 0, False
    for c in w2:
        v = c in VOW
        if v and not prev:
            n += 1
        prev = v
    if w2.endswith("e") and not w2.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    return max(1, n)


def read_prom(p):
    """返回 [(word, t0, t1, prom, bnd)]，跳过标点。"""
    rows = []
    for line in open(p, encoding="utf-8"):
        x = line.rstrip("\n").split("\t")
        if len(x) < 6:
            continue
        try:
            t0, t1 = float(x[1]), float(x[2])
            pr, bd = float(x[4]), float(x[5])
        except ValueError:
            continue
        rows.append((x[3], t0, t1, pr, bd))
    return rows


def norm(w):
    return re.sub(r"[^a-z']", "", w.lower())


def fuzzy_eq(a, b):
    """ASR 拼写差异容忍：前缀一致或编辑距离很小。"""
    if a == b:
        return True
    if not a or not b:
        return False
    if a.startswith(b) or b.startswith(a):
        return True
    # 简单编辑距离（短词）
    if abs(len(a) - len(b)) > 2:
        return False
    la, lb = len(a), len(b)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i]
        for j in range(1, lb + 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (a[i - 1] != b[j - 1])))
        prev = cur
    return prev[lb] <= 1


def find_adv_words(text):
    """从原文找该重读的副词（-ly 方式副词 + 少数焦点副词）。"""
    out = []
    for m in re.finditer(r"[A-Za-z][A-Za-z'-]*", text):
        w = m.group(0)
        lw = w.lower()
        if lw.endswith("ly") and len(lw) > 4 and lw not in NOT_ADV:
            out.append((w, lw))
    return out


def analyse(text, prom_rows, uid, seed):
    """对一句里的每个副词算 rel。"""
    if len(prom_rows) < 4:
        return []
    # 句内每音节时长基线（排除标点、排除时长异常短的碎片）
    base_vals = []
    for w, t0, t1, pr, bd in prom_rows:
        nw = norm(w)
        if not nw:
            continue
        d = t1 - t0
        if d <= 0.02:
            continue
        base_vals.append(d / syllables(nw))
    if len(base_vals) < 3:
        return []
    base = statistics.median(base_vals)

    # 词序列（去标点）与其原始位置索引
    words = [(i, w, t0, t1, pr) for i, (w, t0, t1, pr, bd) in enumerate(prom_rows)
             if norm(w)]
    last_wi = words[-1][0] if words else -1

    # ★ 2026-10-26：改用原文↔ASR 对齐后的区间，而不是在 ASR 词里 fuzzy 查找。
    # 原因：Parakeet 会把 "thought suddenly" 合成 "thoughtly"，该词在 ASR 序列里不存在，
    # 旧逻辑直接判 MISSING（N0807 因此被判不合格，但用户听感是好的）。
    spans = _adv_align.word_spans(text, prom_rows)
    tw = _adv_align.text_words(text)
    res = []
    for orig, lw in find_adv_words(text):
        # 原文里该词的索引（同形取最后一个）
        idxs = [i for i, x in enumerate(tw) if x["is_word"] and x["key"] == lw]
        if not idxs:
            continue
        i = idxs[-1]
        sp = spans[i]
        if sp["t0"] is None:
            res.append(dict(uid=uid, seed=seed, adv=orig, syl=syllables(lw),
                            dur=None, rel=None, prom=None, at_end=False,
                            verdict="UNMEASURED", n_words=len(words), base=round(base, 4)))
            continue
        t0, t1 = sp["t0"], sp["t1"]
        pr = max((r[3] for r in prom_rows if r[1] < t1 and r[2] > t0), default=0.0)
        d = t1 - t0
        nsyl = max(1, syllables(lw))
        sps = d / nsyl
        rel = (d / nsyl) / base if base > 0 else None
        at_end = (i >= len(tw) - 2)
        if sps < SPS_FLAT:
            v = "FLAT"
        elif sps < SPS_SLOW:
            v = "WEAK"
        else:
            v = "SLOWED"
        res.append(dict(uid=uid, seed=seed, adv=orig, syl=nsyl,
                        dur=round(d, 3), sps=round(sps, 3), rel=round(rel, 3) if rel else None,
                        prom=round(pr, 3), at_end=at_end, verdict=v,
                        n_words=len(words), base=round(base, 4)))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--unit", default=None, help="只看某 uid")
    ap.add_argument("--llm", default=None,
                    help="只检查由该文件标记为两模型一致的副词（_adv_final.json）")
    a = ap.parse_args()

    d = json.load(open(PLAN, encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("items", [])
    plan = {str(it["id"]): it for it in items}

    # LLM 一致的 (uid, adv) 白名单
    want = None
    if a.llm:
        want = {}
        for r in json.load(open(a.llm, encoding="utf-8")):
            if r.get("verdict") == "AGREE":
                want.setdefault(r["uid"], set()).add(str(r["ds"]).lower())
        print("LLM 一致标出 %d 个单元 / %d 个词" %
              (len(want), sum(len(v) for v in want.values())))

    rows = []
    files = sorted(os.listdir(PROM_DIR))
    for f in files:
        if not f.endswith(".prom") or "__" not in f:
            continue
        base = f[:-5]
        dpart, uid = base.split("__", 1)
        if a.unit and uid != a.unit:
            continue
        if uid not in plan:
            continue
        if want is not None and uid not in want:
            continue
        seed = dpart.replace("_mt_raw_s", "")
        text = plan[uid].get("text", "")
        if not find_adv_words(text):
            continue
        prom_rows = read_prom(os.path.join(PROM_DIR, f))
        got = analyse(text, prom_rows, uid, seed)
        if want is not None:
            got = [g for g in got if g["adv"].lower() in want[uid]]
        rows.extend(got)

    c = Counter(r["verdict"] for r in rows)
    n = len(rows)
    print("\n=== 副词实例 %d 个 / %d 个单元 ===" % (n, len({r['uid'] for r in rows})))
    for v in ("SLOWED", "WEAK", "FLAT", "MISSING"):
        k = c.get(v, 0)
        print("  %-8s %4d  %5.1f%%  %s" % (v, k, 100.0 * k / max(1, n),
                                           "█" * int(50 * k / max(1, n))))

    sps = sorted(r["sps"] for r in rows if r.get("sps") is not None)
    if sps:
        print("\n=== sps 分布（秒/音节，n=%d）===" % len(sps))
        for f in (0, .05, .25, .5, .75, .9, 1.0):
            print("  p%-4d %.3f" % (int(f * 100), sps[min(len(sps) - 1, int(f * (len(sps) - 1)))]))
        print("  median %.3f" % statistics.median(sps))
        print("  阈值：<%.2f FLAT  /  %.2f~%.2f WEAK  /  ≥%.2f SLOWED"
              % (SPS_FLAT, SPS_FLAT, SPS_SLOW, SPS_SLOW))

    # 单元级：取该单元最好的候选
    byu = defaultdict(list)
    for r in rows:
        byu[r["uid"]].append(r)
    unit_best = {}
    for u, rs in byu.items():
        cand = [r for r in rs if r.get("sps") is not None]
        unit_best[u] = max(cand, key=lambda r: r["sps"]) if cand else None
    ub = Counter()
    for u, r in unit_best.items():
        ub[r["verdict"] if r else "MISSING"] += 1
    print("\n=== 按单元（取最好候选）：%d 个 ===" % len(byu))
    for v in ("SLOWED", "WEAK", "FLAT", "MISSING"):
        k = ub.get(v, 0)
        if k:
            print("  %-8s %4d  %5.1f%%" % (v, k, 100.0 * k / len(byu)))

    if a.show:
        print("\n=== 最该处理（sps 最低）===")
        bad = [r for r in rows if r["verdict"] in ("FLAT", "WEAK", "MISSING")]
        bad.sort(key=lambda r: r.get("sps") if r.get("sps") is not None else -1)
        for r in bad[:a.show]:
            print("  %-8s s%-5s %-13s syl=%d dur=%-6s sps=%-6s rel=%-6s %-8s | %s"
                  % (r["uid"], r["seed"], r["adv"], r["syl"], r["dur"],
                     r.get("sps"), r.get("rel"), r["verdict"],
                     plan[r["uid"]]["text"][:58]))

    if a.json:
        json.dump(rows, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n写出 %s" % a.json)


if __name__ == "__main__":
    main()
