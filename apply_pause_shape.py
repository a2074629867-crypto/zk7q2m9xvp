# -*- coding: utf-8 -*-
"""DEPRECATED（2026-11-11）—— 旁白不要这个脚本，别再跑它。

为什么废弃：它基于一个**误读**。REQUIREMENTS 19-0 的「同一句里每个停顿不一样长」
限定在**对白**（原文依据是「夏尔这个角色的情绪与语言自然度」，例句 Yes./No./Well 是对白）。
旁白由**句法层级**决定长度，同层级同长才是对的 —— skill §18.34 三档定案回测过：
直接用档位 median，MAE 0.292s / R² 0.480；再加 R3 增益为零（r²=0.048）。

本脚本做的两件事都属于「用统计抖动覆盖真实判断」：
  1. 按 why 里的关键词把值钉到档位上缘/下缘 —— why 是描述，不是时长依据；
  2. 同句撞车就 ±0.03 找空位 —— skill §18.24-3 原话「不能用随机量覆盖」。
实测它把 120 条旁白标注从 128.6s 抬到 132.1s，纯粹是噪声。

旁白的正确做法：mark ∈ {inner, bound, clause} → dur 恒为 {0.51, 1.135, 1.695}。
已由 `audit.py` 的 `narr_tier_median` 检查守着。

对白的「逐处不同长」由 `pause_llm.json` 的逐处判定承担（19-0 的四条判据），
也不需要本脚本。

原说明（留档）：
  把同一句里各档位的死值拉开，避免全句同一个数。
  1. 按 why 里的语义关键词定「档位内位置」
  2. 同一句内若仍出现重复值，按出现顺序 ±0.03 递进
"""
import sys as _sys
if '--i-know-this-is-deprecated' not in _sys.argv:
    raise SystemExit(
        'apply_pause_shape.py 已废弃（2026-11-11）。\n'
        '旁白 dur 应恒等于档位 median（inner .51 / bound 1.135 / clause 1.695），\n'
        '用 `audit.py` 检查，不要跑这个脚本。\n'
        '确实要用请加 --i-know-this-is-deprecated。')

_OLD_DOC = """停顿「形状」整形 —— 把同一句里各档位的死值拉开，避免全句同一个数。

（已废弃，原文留档）
  REQUIREMENTS 19-0 写「同一句里每个停顿不一样长」，但那条限定在**对白**。
  实测 L063 两处都变成 0.85 后，句号停顿的 IQR/中位从真人 0.34 压到 0.21。
  做法：按 why 里的语义关键词定档位内位置 + 同句撞车 ±0.03 递进。

用法：
  python apply_pause_shape.py _pause_vote/p_lead_b0.jsonl [...]
  python apply_pause_shape.py --dry _pause_vote/p_lead_b0.jsonl
"""
import argparse
import collections
import json
import sys

# 与 check_pause_batch.py 的 MARKS 一致：(下限, 中位, 上限)
BANDS = {
    "drop":      (0.00, 0.00, 0.00),
    "marker":    (0.25, 0.30, 0.35),
    "list":      (0.35, 0.42, 0.50),
    "short":     (0.60, 0.74, 0.90),
    "clause":    (1.00, 1.16, 1.30),
    "beat":      (1.45, 1.62, 1.90),
    "dot_inner": (0.75, 0.85, 0.95),
}

STRONG = ("长主语", "同位语起", "揭示", "引语框", "落点", "主句起", "判断句")
WEAK = ("从句起", "分词", "短语起", "右段短", "右段两词", "紧接", "插入语后",
        "补语起", "状语起", "并列分词", "定语从句起", "分句起")


def pos(mark, why):
    lo, mid, hi = BANDS[mark]
    if mark in ("drop", "marker", "list", "dot_inner"):
        return mid
    w = why or ""
    s = sum(1 for k in STRONG if k in w)
    k2 = sum(1 for k in WEAK if k in w)
    if s > k2:
        return hi
    if k2 > s:
        return lo
    return mid


def shape(rows):
    """返回新 rows（原地改 dur），并给出改动统计。"""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["bid"].split("#")[0]].append(r)

    changed = 0
    for sid, grp in by.items():
        for r in grp:
            new = pos(r["mark"], r.get("why", ""))
            if abs(float(r["dur"]) - new) > 1e-9:
                r["dur"] = round(new, 2)
                changed += 1
        # 同句内去重：在**档位内**找未被占用的值。
        # 不能简单地「+0.03 递进」—— 撞在档位上限（clause 1.30 / short 0.90 / beat 1.90）
        # 就加不上去了，实测会留下 5 句等长。所以先往上找空位，到顶再往下找。
        used = set()
        for r in grp:
            d = round(float(r["dur"]), 2)
            if d <= 0:
                used.add(d)
                continue
            if d in used:
                lo, mid, hi = BANDS[r["mark"]]
                cand = None
                step = 0.04
                x = round(d + step, 2)
                while x <= hi + 1e-9:
                    if x not in used:
                        cand = x
                        break
                    x = round(x + step, 2)
                if cand is None:
                    x = round(d - step, 2)
                    while x >= lo - 1e-9:
                        if x not in used:
                            cand = x
                            break
                        x = round(x - step, 2)
                if cand is not None:
                    r["dur"] = cand
                    d = cand
                    changed += 1
            used.add(d)
    return rows, changed


def audit(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["bid"].split("#")[0]].append(r)
    tot = same = 0
    for sid, grp in by.items():
        nz = [float(r["dur"]) for r in grp if float(r["dur"]) > 0]
        if len(nz) > 1:
            tot += 1
            if len(set(nz)) < len(nz):
                same += 1
    return same, tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    # 必须**合并后统一整形再写回**：句子可能被切在两批之间
    # （实测 b0 末条 c1_0094#3 与 b1 首条 c1_0094#4 属同一句，分批去重管不到，
    #   合并审计时仍剩 1 句等长）。
    files, rows_of = [], []
    for p in a.files:
        r = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        files.append(p)
        rows_of.append(r)

    grand = [x for r in rows_of for x in r]
    s0, t0 = audit(grand)
    grand, ch = shape(grand)
    s1, t1 = audit(grand)

    # 按原文件切回（长度不变，顺序不变）
    i = 0
    for p, r in zip(files, rows_of):
        seg = grand[i:i + len(r)]
        i += len(r)
        print("%-30s %3d 条 | 合计 %.1fs"
              % (p.split("/")[-1], len(seg), sum(float(x["dur"]) for x in seg)))
        if not a.dry:
            with open(p, "w", encoding="utf-8") as f:
                for x in seg:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")

    print()
    print("改动 %d 条 | 同句等长 %d/%d → %d/%d | 合计停顿 %.1fs"
          % (ch, s0, t0, s1, t1, sum(float(x["dur"]) for x in grand)))
    print("档位分布:", dict(collections.Counter(x["mark"] for x in grand)))
    if a.dry:
        print("（--dry，未写回）")


if __name__ == "__main__":
    main()
