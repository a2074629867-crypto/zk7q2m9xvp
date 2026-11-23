# -*- coding: utf-8 -*-
"""_calib_nat_dlg.py —— 建**对白专属**自然度参照分布（替代旁白口径）。

为什么必须分开：
  现有 `_nat_stat.json` 是 55 条**旁白**标定的（MOS 均值 3.81 / sd 0.38）。
  搬到对白上系统性误报 —— r5 把 21 条 MOS 平均拉高 +1.74，仍有 19 条判 FAIL(-2.3σ)，
  分项显示是 COL（音色染色）在拖：模型把「更像电影真人原声」判成染色。
  ⇒ 参照分布必须来自**对白自身**，且关键项要按实测判别力筛掉。

锚集（anchor）定义 —— 不参与自然度判定的独立证据：
  tech PASS（无削波/非静音）+ speaker PASS（声纹对上人）
  + intra != MANUAL（句内无突变）+ scs != MANUAL（档内不离群）
  + 语音时长 >= 1.0s（短于此测量本身不稳）
  自然度闸本身**不参与**锚集筛选，否则自我循环。

统计量用 median / MAD（1.4826*MAD≈σ），不用 mean/sd：
  对白里有明确的坏尾（0.49~1.67 MOS 那一批），mean/sd 会被它们拉歪。

验证：
  ① 每项在 r5 的 21 组配对（旧音频=坏 / 新音频=好）上的 AUC
  ② 组合分在配对上的一致率
  ③ 锚集自身 FPR（阈值下应≈5%）
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")

import _nat_guard as NG

HERE = "G:/_setup"
OUT_DIR = os.path.join(HERE, "_audio_ch123/out")
KEYS_ALL = ["nq_mos", "nq_dis", "nq_col", "squim"]
STAT_OUT = os.path.join(HERE, "_nat_stat_dlg.json")


def load():
    plan = {}
    for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l); plan[o["id"]] = o
    gate = {x["id"]: x for x in json.load(open(os.path.join(HERE, "_gate_dlg_v19.json"), encoding="utf-8"))}
    nat = json.load(open(os.path.join(HERE, "_nat_dlg.json"), encoding="utf-8"))
    return plan, gate, nat


def robust(v):
    v = np.asarray([x for x in v if x is not None], dtype=float)
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med))) * 1.4826
    if mad < 1e-6:                       # 退化：退回 sd
        mad = float(np.std(v))
    return med, max(mad, 1e-3), len(v)


def zscores(sc, st, keys):
    out = {}
    for k in keys:
        v = sc.get(k)
        if v is None:
            continue
        out[k] = (v - st[k]["med"]) / st[k]["sd"]
    return out


def score(sc, st, keys, sp_reg=1.20):
    z = zscores(sc, st, keys)
    if not z:
        return None, None
    e = float(np.mean(list(z.values())))
    sp = max(sc.get("sp") or 0.0, 0.05)
    if sp < sp_reg:
        reg = st.get("_reg") or {}
        return e, e - (reg.get("a", 0.0) + reg.get("b", 0.0) * np.log(sp))
    return e, e


def main():
    plan, gate, nat = load()

    # ---------- 1. 锚集 ----------
    anchor = []
    for i, o in plan.items():
        g = gate.get(i) or {}
        gt = g.get("gates") or {}
        sc = (nat.get(i) or {}).get("raw")
        if not sc:
            continue
        if gt.get("tech") != "PASS":
            continue
        if gt.get("speaker") != "PASS":
            continue
        if gt.get("intra") == "MANUAL" or gt.get("scs") == "MANUAL":
            continue
        if (sc.get("sp") or 0) < 1.0:
            continue
        anchor.append((i, sc))

    print("锚集 %d / %d 条（tech+speaker PASS, intra/scs 非 MANUAL, 语音≥1.0s）" % (len(anchor), len(plan)))
    sp = np.array([s["sp"] for _, s in anchor])
    print("  语音时长 p10 %.2f p50 %.2f p90 %.2f" % tuple(np.percentile(sp, [10, 50, 90])))

    st = {}
    print("\n锚集分项（median / MAD-sigma）：")
    for k in KEYS_ALL:
        med, sd, n = robust([s.get(k) for _, s in anchor])
        st[k] = dict(med=med, sd=sd, n=n)
        print("  %-8s med %6.3f  sd %5.3f  n %d" % (k, med, sd, n))

    # ---------- 2. 每项在 r5 配对上的判别力 ----------
    pairs = json.load(open(os.path.join(HERE, "_backfill_r5_log.json"), encoding="utf-8"))
    seen, uniq = set(), []
    for p in pairs:
        if p["id"] in seen:
            continue
        seen.add(p["id"]); uniq.append(p)
    print("\nr5 配对 %d 组（旧=坏 / 新=好）" % len(uniq))

    def auc(pos, neg):
        pos = [x for x in pos if x is not None]
        neg = [x for x in neg if x is not None]
        if not pos or not neg:
            return None
        s = 0.0
        for a in pos:
            for b in neg:
                s += 1.0 if a > b else 0.5 if a == b else 0.0
        return s / (len(pos) * len(neg))

    old_sc, new_sc = [], []
    for p in uniq:
        i = p["id"]
        bk = p.get("backup")
        if not bk or not os.path.exists(bk):
            continue
        old_sc.append(NG.raw(bk))
        new_sc.append(NG.raw(os.path.join(OUT_DIR, i + ".wav")))

    print("\n%-8s %8s  %s" % ("分项", "AUC", "旧中位 → 新中位"))
    keep = []
    for k in KEYS_ALL:
        a = auc([s.get(k) for s in new_sc], [s.get(k) for s in old_sc])
        om = np.median([s.get(k) for s in old_sc if s.get(k) is not None])
        nm = np.median([s.get(k) for s in new_sc if s.get(k) is not None])
        flag = "  ← 无判别力，剔除" if (a is not None and a < 0.60) else ""
        print("  %-6s %8.3f  %6.2f → %6.2f%s" % (k, a or 0, om, nm, flag))
        if a is not None and a >= 0.60:
            keep.append(k)
    print("保留分项:", keep)

    # ---------- 3. 长度回归（用锚集） ----------
    xs, ys = [], []
    for _, s in anchor:
        e, _ = score(s, st, keep)
        if e is None or (s.get("sp") or 0) < 0.2:
            continue
        xs.append(np.log(s["sp"])); ys.append(e)
    b, a = np.polyfit(np.array(xs), np.array(ys), 1)
    r = float(np.corrcoef(xs, ys)[0, 1])
    st["_reg"] = dict(a=float(a), b=float(b), r=r, n=len(xs))
    print("\n长度回归: ens = %.3f + %.3f*ln(sp)   r=%.3f  n=%d" % (a, b, r, len(xs)))

    # ---------- 4. 配对上的组合分 ----------
    so = [score(s, st, keep)[1] for s in old_sc]
    sn = [score(s, st, keep)[1] for s in new_sc]
    a2 = auc(sn, so)
    ok = sum(1 for x, y in zip(sn, so) if x is not None and y is not None and x > y)
    n2 = sum(1 for x, y in zip(sn, so) if x is not None and y is not None)
    print("组合分 AUC %.3f | 配对排序正确 %d/%d" % (a2 or 0, ok, n2))

    # ---------- 5. 阈值：锚集分位 + 配对的分离度 ----------
    an = np.array([score(s, st, keep)[1] for _, s in anchor if score(s, st, keep)[1] is not None])
    print("\n锚集组合分 p1 %.2f p5 %.2f p10 %.2f p50 %.2f" % tuple(np.percentile(an, [1, 5, 10, 50])))
    print("旧音频组合分 p50 %.2f / 新音频 p50 %.2f" % (np.median([x for x in so if x is not None]),
                                                     np.median([x for x in sn if x is not None])))
    for th in (-2.0, -2.3, -2.6, -3.0):
        fpr = float(np.mean(an < th)) * 100
        tpr = float(np.mean([x < th for x in so if x is not None])) * 100   # 旧音频应被抓出
        keepn = float(np.mean([x >= th for x in sn if x is not None])) * 100
        print("  阈值 %5.1fσ  锚集误报 %4.1f%%  旧音频抓出 %4.1f%%  新音频保住 %4.1f%%" % (th, fpr, tpr, keepn))

    st["_meta"] = dict(keys=keep, anchor_n=len(anchor), built_at="2026-11-12",
                       note="对白专属；锚集=tech+speaker PASS 且 intra/scs 非 MANUAL 且语音≥1.0s")
    json.dump(st, open(STAT_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写出 %s" % STAT_OUT)


if __name__ == "__main__":
    main()
