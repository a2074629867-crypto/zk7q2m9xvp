# -*- coding: utf-8 -*-
"""_adv_recal.py —— 用 p75 重算 55 条，量化「峰判据」虚高了多少。

背景：`loc` 原用词内 F0 **max**。词边界来自 ASR，尾随静音/呼吸被包在区间内，
parselmouth 在那种弱段会给出高一个八度的假值，于是 `loc` 被一个 0.04s 的尖峰决定。
N0627 r6 是活证据：max 版 +5.21，p75 版 **−0.45**。

判据对照：
    loc_max  旧定义（历史所有结论都基于它）
    loc_p75  75 分位（要词内 25% 帧都抬高才抬得起来）
    loc_p90  90 分位（更接近"峰"但又不过分敏感）

输出 `_adv_recal.json`，并按 loc_p75 重新分档。
"""
import json
import os
import statistics as S
import sys

sys.path.insert(0, "G:/_setup")
import _adv_prom as P

ROOT = "G:/_setup"
STATE = os.path.join(ROOT, "_mt_adv_state.json")
OUT = os.path.join(ROOT, "_adv_recal.json")
LOC_OK = 2.0


def main():
    st = json.load(open(STATE, encoding="utf-8"))["units"]
    rows = []
    for u, x in sorted(st.items()):
        prom = os.path.join(ROOT, "_wpt_out", "_mt_pick__%s.prom" % u)
        wav = os.path.join(ROOT, "_mt_pick", u + ".wav")
        if not (os.path.exists(prom) and os.path.exists(wav)):
            print("skip", u)
            continue
        cws = P.measure_one(wav, prom, x["text"]) or []
        adv = x["adv"].lower()
        hit = [c for c in cws if c["key"] == adv]
        if not hit:
            rows.append(dict(uid=u, adv=x["adv"], note="未测到"))
            continue
        c = hit[-1]
        # 注意：word_feats 的 peak 已是 p75，所以 c["loc"] 本身就是 p75 版；
        # 另外两档用同一个 base 平移回去。
        loc_p75 = c["loc"]
        rows.append(dict(
            uid=u, adv=x["adv"],
            loc_p75=round(loc_p75, 2),
            loc_max=round(loc_p75 + (c["raw_peak"] - c["peak"]), 2),
            loc_p90=round(loc_p75 + (c["p90"] - c["peak"]), 2),
            raw_peak=c["raw_peak"], p75=c["peak"], p90=c["p90"],
            n_fr=c["n_fr"], voiced=c["voiced"], human=x.get("judge_by") or ""))
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    ok = [r for r in rows if "loc_p75" in r]
    print("=== %d 条（%d 可测）===" % (len(rows), len(ok)))
    print("%-8s %-14s %-8s %-8s %-8s %-7s %s"
          % ("uid", "adv", "loc_max", "loc_p75", "loc_p90", "帧数", "判据变化"))
    flips = []
    for r in ok:
        a = "PASS" if r["loc_max"] >= LOC_OK else "WATCH"
        b = "PASS" if r["loc_p75"] >= LOC_OK else "WATCH"
        mark = "" if a == b else ("%s→%s" % (a, b))
        if a != b:
            flips.append(r)
        print("%-8s %-14s %+7.2f %+8.2f %+8.2f %-7d %s"
              % (r["uid"], r["adv"][:14], r["loc_max"], r["loc_p75"],
                 r["loc_p90"], r["n_fr"], mark))
    print("\n=== 汇总 ===")
    for k in ("loc_max", "loc_p75", "loc_p90"):
        v = [r[k] for r in ok]
        n = sum(1 for x in v if x >= LOC_OK)
        print("  %-8s 中位 %+5.2f  最小 %+6.2f  最大 %+5.2f  ≥%.1f 的 %d/%d"
              % (k, S.median(v), min(v), max(v), LOC_OK, n, len(v)))
    print("\n翻转（旧达标→新不达标）%d 条：%s"
          % (len(flips), ", ".join(r["uid"] for r in flips)))


if __name__ == "__main__":
    main()
