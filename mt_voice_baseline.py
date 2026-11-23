# -*- coding: utf-8 -*-
"""mt_voice_baseline.py —— 每一档音色**各自**建一条基线（四把尺子，互不相干）。

★★★ 为什么必须分档建基线（2026-10-31 用户纠正）
  四种情绪 = 四种不同的音色，它们是**四个独立的档**，不是一个档的四个样本。
  所以验收时每一档只跟**它自己**的参考音比，容差也只取**它自己**切片的自然波动。
  一旦把八档放进同一个度量空间做「最近档」「AUC」，就是在用一把尺子量四种音色，
  必然得出「分不清」这种伪结论 —— 那个问题我们根本不需要回答：
  档是生成时指定的，不需要事后识别。

  本脚本只做一件事：对每一档，用它自己的切片算出
    中心 = 该档切片的中位（这一档真实的发声习惯）
    带   = 该档切片的 p10~p90，再按样本量放宽
  并检查**参考音自己是否落在它这一档的带内**（不在 = 这条 ref 不纯，要换）。

产出 `_voice_baseline.json`，供 mt_voice_gate.py 逐档取用。

用法：
  python mt_voice_baseline.py
  python mt_voice_baseline.py --min-dur 0.6 --json _voice_baseline.json
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mt_voice_gate as G

ROOT = os.path.dirname(os.path.abspath(__file__))
CLEAN = os.path.join(ROOT, "castle_fr_clean")

# 档 -> (切片目录, 参考音文件名, 角色, 情绪中文)
GROUPS = {
    "C_normal":  ("1_charles_normal",  "1_charles_normal",   "C", "平常"),
    "C_soft":    ("2_charles_soft",    "2_charles_soft",     "C", "轻声"),
    "C_excited": ("3_charles_excited", "3_charles_excited_v2", "C", "激动"),
    "C_angry":   ("4_charles_angry",   "4_charles_angry_v2", "C", "愤怒"),
    "E_loud":    ("5_hooper_loud",     "5_hooper_loud",      "E", "大声"),
    "E_calm":    ("6_hooper_calm",     "6_hooper_calm",      "E", "平静"),
    "E_scold":   ("6b_hooper_scold",   "6b_hooper_scold",    "E", "斥骂"),
    "E_begging": ("7_hooper_begging",  "7_hooper_begging",   "E", "求饶"),
}

# 已确认误标：c21 是 Hooper 的道歉句，被切进 Charles 生气组
EXCLUDE = {"4_charles_angry": ["c21"]}

# 样本量少时 p10/p90 不可靠 -> 用中位 ± k*MAD，k 随样本量放宽
MIN_CLIPS = 6


def clips_of(group):
    d = os.path.join(CLEAN, group)
    fs = [f for f in sorted(glob.glob(os.path.join(d, "*.wav"))) if "_bed" not in f]
    for bad in EXCLUDE.get(group, []):
        fs = [f for f in fs if bad not in os.path.basename(f)]
    return fs


def band(vals, n, lo_pad=1.0, hi_pad=1.0):
    """从切片分布取带。样本够用 p10~p90；不够用中位 ± 2.5*MAD。"""
    v = np.array([x for x in vals if x is not None and np.isfinite(x)], dtype=float)
    if len(v) == 0:
        return None, None, None, 0, "无数据"
    med = float(np.median(v))
    if len(v) >= MIN_CLIPS:
        lo, hi = float(np.percentile(v, 10)), float(np.percentile(v, 90))
        method = "p10-p90"
    else:
        mad = float(np.median(np.abs(v - med))) or float(np.std(v))
        lo, hi = med - 2.5 * mad, med + 2.5 * mad
        method = "median±2.5MAD(n小)"
    # 外扩：产物是 TTS，不是真人切片，留余量
    span = max(hi - lo, 1e-9)
    lo2, hi2 = lo - span * (lo_pad - 1.0) * 0.5, hi + span * (hi_pad - 1.0) * 0.5
    return med, lo2, hi2, len(v), method


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-dur", type=float, default=0.6,
                    help="短于此的切片跳过（F0 不可靠）")
    ap.add_argument("--json", default=os.path.join(ROOT, "_voice_baseline.json"))
    a = ap.parse_args()

    out = {}
    print("%-11s %-9s %5s %8s %8s %8s  %s"
          % ("档", "情绪", "n", "F0中位", "F0带", "谱质心带", "方法"))
    for key, (grp, refname, who, zh) in GROUPS.items():
        fs = clips_of(grp)
        rows, skipped = [], 0
        for f in fs:
            try:
                m = G.measure(f)
            except Exception:
                skipped += 1
                continue
            if m["dur"] < a.min_dur or not m["f0"] or not m["cen"]:
                skipped += 1
                continue
            rows.append(m)

        if not rows:
            print("%-11s %-9s  ** 无可用切片 **" % (key, zh))
            continue

        f0_med, f0_lo, f0_hi, n_f0, meth_f0 = band([r["f0"] for r in rows], len(rows))
        cen_med, cen_lo, cen_hi, n_cen, meth_cen = band([r["cen"] for r in rows], len(rows))
        slp_med, slp_lo, slp_hi, n_slp, meth_slp = band([r["slp"] for r in rows], len(rows))

        # ★ 最小带宽：样本少时 p10-p90 会窄到 1 个半音（C_angry 只有 3 条 → 241~258），
        #   而 TTS 产物本身就有 seed 波动 0.9 半音 + 文本语调 3.3 半音跨度。
        #   带比噪声还窄 ⇒ 任何正常产物都出带，判据失效。
        f0_lo = min(f0_lo, f0_med * 2 ** (-2.5 / 12))
        f0_hi = max(f0_hi, f0_med * 2 ** (2.5 / 12))
        cen_lo, cen_hi = min(cen_lo, cen_med * 0.78), max(cen_hi, cen_med * 1.28)
        slp_lo, slp_hi = min(slp_lo, slp_med - 3.0), max(slp_hi, slp_med + 3.0)

        # 参考音自检：它落在自己这一档的带里吗
        refp = os.path.join(ROOT, "castle_fr_ref", refname + ".wav")
        rm = G.measure(refp) if os.path.exists(refp) else None
        inband = {}
        if rm and rm["f0"]:
            inband["f0"] = bool(f0_lo <= rm["f0"] <= f0_hi)
            inband["f0_st_from_med"] = round(12 * np.log2(rm["f0"] / f0_med), 2)
        if rm and rm["cen"]:
            inband["cen"] = bool(cen_lo <= rm["cen"] <= cen_hi)
        if rm and rm["slp"] is not None:
            inband["slp"] = bool(slp_lo <= rm["slp"] <= slp_hi)

        out[key] = dict(
            group=grp, ref=refname, who=who, zh=zh,
            n_clips=len(rows), n_skipped=skipped, method=meth_f0,
            f0=dict(med=round(f0_med, 1), lo=round(f0_lo, 1), hi=round(f0_hi, 1)),
            cen=dict(med=round(cen_med), lo=round(cen_lo), hi=round(cen_hi)),
            slp=dict(med=round(slp_med, 2), lo=round(slp_lo, 2), hi=round(slp_hi, 2)),
            ref_measure=None if not rm else dict(
                f0=round(rm["f0"], 1) if rm["f0"] else None,
                cen=round(rm["cen"]) if rm["cen"] else None,
                slp=round(rm["slp"], 2) if rm["slp"] is not None else None),
            ref_in_band=inband,
        )
        flag = "" if all(inband.get(k, True) for k in ("f0", "cen", "slp")) else "  ← ref 出带"
        print("%-11s %-9s %5d %8.1f %8s %8s  %s%s"
              % (key, zh, len(rows), f0_med,
                 "%.0f~%.0f" % (f0_lo, f0_hi),
                 "%.0f~%.0f" % (cen_lo, cen_hi), meth_f0, flag))

    json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n写出", a.json, "（%d 档）" % len(out))

    bad = [k for k, v in out.items()
           if not all(v["ref_in_band"].get(x, True) for x in ("f0", "cen", "slp"))]
    if bad:
        print("!! 参考音落在自己档的带外：", ", ".join(bad))
        print("   ⇒ 这条 ref 不具代表性（混了别的语域/别的情绪），生成时会带偏。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
