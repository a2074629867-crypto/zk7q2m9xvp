# -*- coding: utf-8 -*-
"""mt_contour_verify.py —— V2 零假设检验 + V3 合成劣化响应

V2：F0 / 能量两个场的 21 点轮廓，同文本对 vs 异文本对的 AUC。
    AUC ≈ 0.5 说明该指标没有分辨力，只能做相对排序。
V3：对正常候选做三种内存篡改，看判据是否朝正确方向响（不需要人工标签）。

用法：
  G:/Python310/python.exe mt_contour_verify.py --v2 _mt_contour_ch1.json
  G:/Python310/python.exe mt_contour_verify.py --v3 --n 30
"""
import argparse
import json
import os
import random
import sys

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import mt_contour as C          # noqa: E402


def auc(pos, neg):
    """P(pos > neg)，Mann-Whitney。"""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    pos = pos[np.isfinite(pos)]
    neg = neg[np.isfinite(neg)]
    if len(pos) < 5 or len(neg) < 5:
        return float("nan"), len(pos), len(neg)
    allv = np.concatenate([pos, neg])
    r = np.argsort(np.argsort(allv)) + 1.0
    rs = r[:len(pos)].sum()
    return (rs - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)), len(pos), len(neg)


def corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def v2(path):
    d = json.load(open(path, encoding="utf-8"))
    U = d["units"]
    same_e, same_f = [], []
    by = []
    for u in U.values():
        ok = [c for c in u["cands"].values() if c.get("prof") and c.get("e_prof")]
        if len(ok) >= 2:
            for i in range(len(ok)):
                for j in range(i + 1, len(ok)):
                    same_f.append(corr(ok[i]["prof"], ok[j]["prof"]))
                    same_e.append(corr(ok[i]["e_prof"], ok[j]["e_prof"]))
        for c in ok:
            by.append((u["text"], c))
    random.seed(0)
    diff_e, diff_f = [], []
    for _ in range(400):
        a, b = random.sample(by, 2)
        if a[0] == b[0]:
            continue
        diff_f.append(corr(a[1]["prof"], b[1]["prof"]))
        diff_e.append(corr(a[1]["e_prof"], b[1]["e_prof"]))
    print("=" * 68)
    print("V2 零假设检验（同文本对 vs 异文本对，21 点轮廓 Pearson）")
    print("=" * 68)
    print("%-8s %8s %8s %8s %7s %7s %-8s" % ("场", "同文本", "异文本", "净间隔", "AUC", "对数", "判定"))
    rows = []
    for name, s, dd, need in (("能量", same_e, diff_e, 0.70), ("F0", same_f, diff_f, 0.70)):
        s = np.array(s, float); dd = np.array(dd, float)
        s = s[np.isfinite(s)]; dd = dd[np.isfinite(dd)]
        a, n1, n2 = auc(list(s), list(dd))
        gap = float(np.median(s) - np.median(dd)) if len(s) and len(dd) else float("nan")
        verdict = "可用" if a >= need else ("只排序" if a >= 0.60 else "无信号")
        print("%-8s %8.3f %8.3f %+8.3f %7.3f %7d %-8s"
              % (name, np.median(s), np.median(dd), gap, a, n1, verdict))
        rows.append((name, float(np.median(s)), float(np.median(dd)), gap, float(a), verdict))
    print()
    print("参考：AUC 0.5 = 抛硬币；≥0.70 才有条件设绝对阈值；0.60–0.70 只允许相对排序。")
    return rows


def v3(n=30):
    plan = json.load(open(os.path.join(ROOT, "mt_plan3b.json"), encoding="utf-8"))
    dirs = ["_mt_raw_s42", "_mt_raw_s1234", "_mt_raw_srate"]
    pool = []
    for p in plan:
        if p["ch"] != "ch1":
            continue
        for dd in dirs:
            fp = os.path.join(ROOT, dd, p["id"] + ".wav")
            if os.path.exists(fp):
                pool.append((p["id"], p["text"], fp))
    random.seed(7)
    random.shuffle(pool)
    print("=" * 68)
    print("V3 合成劣化响应（篡改后判据是否朝正确方向动）")
    print("=" * 68)
    base_span, base_l3, base_jump = [], [], []
    hit_l3 = hit_flat = hit_jump = tried = n_period = 0
    for uid, text, fp in pool:
        if tried >= n:
            break
        cls = C.punct_class(text)
        try:
            f0, t, dur = C.read_f0(fp)
            f0, _ = C.clean_f0(f0, C.F0_MAX_DEV_ST)
            ps, why = C.unit_profile(f0, t)
        except Exception:
            continue
        if ps is None or dur < C.L3_MIN_DUR:
            continue
        tried += 1
        base_span.append(ps["span_st"])
        # 篡改 1：末 25% **渐次上扬**（0→+6 半音斜坡）→ 陈述句应判 END-RISE
        # 注意：整体平移不改变斜率，只有斜坡才能造出"上扬"的听感，别用平移。
        f1 = f0.copy()
        v = np.where(f1 > 0)[0]
        if len(v) >= 8:
            cut = int(len(v) * 0.75)
            ramp = np.linspace(0.0, 6.0, len(v) - cut)
            f1[v[cut:]] *= 2.0 ** (ramp / 12.0)
            p1, _ = C.unit_profile(f1, t)
            if p1:
                l3 = C.l3_check(cls, p1, dur)
                base_l3.append(l3["violated"])
                if cls == "period":
                    n_period += 1
                    if l3["violated"]:
                        hit_l3 += 1
        # 篡改 2：压平到 40%（围绕自身中位）
        if ps["f0_med"] > 0:
            f2 = f0.copy()
            vv = f2 > 0
            f2[vv] = ps["f0_med"] * (f2[vv] / ps["f0_med"]) ** 0.4
            p2, _ = C.unit_profile(f2, t)
            if p2 and p2["span_st"] < 5.17:      # 语料 p10
                hit_flat += 1
        # 篡改 3：插 2 处 ±12 半音单帧跳变
        f3 = f0.copy()
        v3i = np.where(f3 > 0)[0]
        if len(v3i) >= 20:
            for pos, mul in ((int(len(v3i) * 0.35), 2.0), (int(len(v3i) * 0.60), 0.5)):
                f3[v3i[pos]] *= mul
            p3, _ = C.unit_profile(f3, t)
            if p3:
                l1 = C.l1_checks(f3, t, p3)
                if l1["jump_cnt6"] >= C.L1_JUMP_CNT_WARN:
                    hit_jump += 1
    span = np.array(base_span) if base_span else np.array([0])
    print("%-28s %6s %6s %8s" % ("篡改", "命中", "样本", "命中率"))
    print(f"{'①':<6} {hit_l3:6d} {n_period:6d} {100.0 * hit_l3 / max(n_period, 1):6.0f}%  陈述句末段渐次上扬 0→+6st → END-RISE")
    print(f"{'②':<6} {hit_flat:6d} {tried:6d} {100.0 * hit_flat / max(tried, 1):6.0f}%  压平到 40% → span < p10(5.17)")
    print(f"{'③':<6} {hit_jump:6d} {tried:6d} {100.0 * hit_jump / max(tried, 1):6.0f}%  插 ±12st 单帧 → jump_cnt6 >= 2")
    print()
    print(f"原样本 span_st 中位 {np.median(span):.2f}（语料 p10=5.17）；验收线：三项命中率均 ≥80%。")

    # 反向：未篡改的假阳性率
    fp_l3 = fp_flat = fp_jump = 0
    for uid, text, fp in pool[:max(n * 3, 60)]:
        cls = C.punct_class(text)
        try:
            f0, t, dur = C.read_f0(fp)
            f0, _ = C.clean_f0(f0, C.F0_MAX_DEV_ST)
            ps, _ = C.unit_profile(f0, t)
        except Exception:
            continue
        if ps is None or dur < C.L3_MIN_DUR:
            continue
        if cls == "period" and C.l3_check(cls, ps, dur)["violated"]:
            fp_l3 += 1
        if ps["span_st"] < 5.17:
            fp_flat += 1
        if C.l1_checks(f0, t, ps)["jump_cnt6"] >= C.L1_JUMP_CNT_WARN:
            fp_jump += 1
    tot = max(len(pool[:max(n * 3, 60)]), 1)
    print(f"反向对照（未篡改样本，越低越好）：END-RISE {fp_l3} / span<p10 {fp_flat} / JUMP {fp_jump}")
    return hit_l3, hit_flat, hit_jump, tried


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2", default=None)
    ap.add_argument("--v3", action="store_true")
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    if a.v2:
        v2(a.v2 if os.path.isabs(a.v2) else os.path.join(ROOT, a.v2))
    if a.v3:
        v3(a.n)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
