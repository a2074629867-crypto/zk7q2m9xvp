# -*- coding: utf-8 -*-
"""wl_align.py —— 词级 L1（wlevel_flags）与现有起伏闸门（mt_rhythm_gate）逐条对齐。

要回答的问题只有一个：**L1 是否比现有闸门多看见东西**。
  现有闸门判的是 energy_span 落带（能量起伏，FIX_LOW=太平 / FIX_HIGH=太陡）；
  L1 判的是词级 F0 起伏（FLAT_TAKE/FLAT_RUN）+ ASR 内容（NO_TARGET/TRUNC/LEAD_REF）。
  两者物理量不同，不是二选一，必须先量重合度再谈要不要上新引擎。

口径：
  · 统一按 clip id join（闸门 --dir 模式的 unit 就是文件名）。
  · 「L1 有旗标」分两组统计：韵律组（FLAT_TAKE/FLAT_RUN）/ 内容组（NO_TARGET/TRUNC/LEAD_REF/PACE）。
  · 不把 LOW_PROB 算进韵律判定（专名误报已知）。
"""
import argparse
import io
import json
import os
from collections import Counter

ROOT = "G:/_setup"


def load_rows(p):
    d = json.load(io.open(p, encoding="utf-8"))
    if isinstance(d, dict):
        return d.get("rows") or [], d
    return d, {}


def kappa(a, b):
    """两个 bool 列表的 Cohen's kappa。"""
    n = len(a)
    if not n:
        return 0.0
    po = sum(1 for x, y in zip(a, b) if x == y) / float(n)
    pa = sum(a) / float(n)
    pb = sum(b) / float(n)
    pe = pa * pb + (1 - pa) * (1 - pb)
    return 0.0 if pe >= 1 else (po - pe) / (1 - pe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flags", default=os.path.join(ROOT, "_wl_flags_all.jsonl"))
    ap.add_argument("--rhythm", default=os.path.join(ROOT, "_rhythm_gate_all.json"))
    ap.add_argument("--md", default=os.path.join(ROOT, "_wl_align.md"))
    ap.add_argument("--json", default=os.path.join(ROOT, "_wl_align.json"))
    a = ap.parse_args()

    R, meta = load_rows(a.rhythm)
    G = {r["unit"].replace(".wav", ""): r for r in R}
    F = {}
    for line in io.open(a.flags, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            F[r["tid"]] = r

    ids = [i for i in F if i in G]
    if not ids:
        print("!! 没有可 join 的 id，检查 unit 与 tid 是否同一命名")
        return

    FLAT = ("FLAT_TAKE", "FLAT_RUN")
    CONT = ("NO_TARGET", "TRUNC", "LEAD_REF", "PACE")
    LOWF = ("FIX_LOW", "WATCH_LOW")
    HIGHF = ("FIX_HIGH", "WATCH_HIGH")

    g_v = Counter(G[i]["verdict"] for i in ids)
    l_ok = sum(1 for i in ids if not F[i]["flags"])

    def has(i, keys):
        return any(k in F[i]["flags"] for k in keys)

    # --- 1. 韵律组：L1 平 vs 闸门低带
    gflat = [G[i]["verdict"] in LOWF for i in ids]
    lflat = [has(i, FLAT) for i in ids]
    tp = sum(1 for i in ids if has(i, FLAT) and G[i]["verdict"] in LOWF)
    fp = sum(1 for i in ids if has(i, FLAT) and G[i]["verdict"] not in LOWF)
    fn = sum(1 for i in ids if not has(i, FLAT) and G[i]["verdict"] in LOWF)
    n = len(ids)
    prec = tp / float(tp + fp) if tp + fp else 0.0
    rec = tp / float(tp + fn) if tp + fn else 0.0
    kap = kappa(gflat, lflat)

    # --- 2. 闸门 FIX 的构成（L1 结构性看不见哪一类）
    fix_ids = [i for i in ids if G[i]["verdict"].startswith("FIX")]
    fix_low = [i for i in fix_ids if G[i]["verdict"] == "FIX_LOW"]
    fix_high = [i for i in fix_ids if G[i]["verdict"] == "FIX_HIGH"]
    fix_shape = Counter(s for i in fix_ids for s in (G[i].get("shape") or []))

    # --- 3. 内容组：闸门完全看不到的一类（应占 L1 独有旗标的主体）
    cont_ids = [i for i in ids if has(i, CONT)]
    cont_in_pass = [i for i in cont_ids if G[i]["verdict"] == "PASS"]

    L = []
    L.append("# L1 词级旗标 vs 起伏闸门：逐条对齐\n")
    L.append("样本 %d 条（L1 %d / 闸门 %d，按 clip id join）**干净 %d (%.1f%%)**\n"
             % (n, len(F), len(G), l_ok, 100.0 * l_ok / n))
    L.append("闸门判定分布：%s\n" % dict(g_v.most_common()))

    L.append("## 1. 韵律组：L1 词级塔平 vs 闸门低带（FIX_LOW+WATCH_LOW）\n")
    L.append("| | 闸门低带 | 闸门其余 |")
    L.append("|---|---|---|")
    L.append("| **L1 有 FLAT** | %d（命中） | %d（L1 独家） |" % (tp, fp))
    L.append("| **L1 无 FLAT** | %d（漏） | %d |" % (fn, n - tp - fp - fn))
    L.append("\nprecision %.1f%% · recall %.1f%% · Cohen κ **%.2f**\n" % (100 * prec, 100 * rec, kap))
    if tp + fp:
        L.append("L1 报的 %d 条里，闸门落在低带的只有 %d 条 —— 说明两把尺子测的不是同一个量。\n" % (tp + fp, tp))

    L.append("## 2. 闸门 FIX 的构成（看 L1 结构化盲区）\n")
    L.append("| 类别 | 条数 | L1 有 FLAT | 说明 |")
    L.append("|---|---|---|---|")
    for tag, sub in [("FIX_LOW 太平", fix_low), ("FIX_HIGH 太陡", fix_high)]:
        hit = sum(1 for i in sub if has(i, FLAT))
        L.append("| %s | %d | %d | %s |" % (tag, len(sub), hit,
                 "L1 有对应判据" if "LOW" in tag else "L1 **没有**『太陡』判据"))
    if fix_shape:
        L.append("\nFIX 条目里的形状旗：%s（SHAPE_RISE 末段上扬 / SHAPE_CUT 硬切 / SHAPE_OCT 八度伪影 / SHAPE_REV 抖动 —— L1 全部不看）\n"
                 % dict(fix_shape.most_common()))

    L.append("## 3. 内容组：闸门结构性看不见\n")
    L.append("L1 报内容问题 %d 条，其中闸门判 PASS 的有 **%d 条**（%.0f%%）。\n"
             % (len(cont_ids), len(cont_in_pass),
                100.0 * len(cont_in_pass) / len(cont_ids) if cont_ids else 0))
    c = Counter(k for i in cont_ids for k in F[i]["flags"] if k in CONT)
    L.append("分类：%s\n" % dict(c.most_common()))
    for i in cont_in_pass[:12]:
        L.append("- `%s` cov=%.0f%% said=%r" % (i, 100 * F[i]["cov"], F[i]["said"][:60]))

    L.append("\n## 4. L1 独家报的塔平（闸门 PASS/WATCH_HIGH）前 10 条\n")
    ex = [i for i in ids if has(i, FLAT) and G[i]["verdict"] not in LOWF]
    ex.sort(key=lambda i: -len(F[i]["flat_run"]))
    L.append("| tid | 闸门 | span | L1 flat_run | 文本 |")
    L.append("|---|---|---|---|---|")
    for i in ex[:10]:
        L.append("| %s | %s | %s | %s | %s |" % (
            i, G[i]["verdict"], G[i].get("energy_span"),
            "/".join(F[i]["flat_run"][:4]), F[i]["text"][:36].replace("|", "/")))

    out = "\n".join(L) + "\n"
    io.open(a.md, "w", encoding="utf-8").write(out)
    json.dump(dict(n=n, kappa=round(kap, 3), prec=round(prec, 3), rec=round(rec, 3),
                   tp=tp, fp=fp, fn=fn, gate=dict(g_v)),
              io.open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(out[:2600])
    print("→ %s\n→ %s" % (a.md, a.json))


if __name__ == "__main__":
    main()
