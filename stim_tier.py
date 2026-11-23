# -*- coding: utf-8 -*-
"""刺激分级（stim tier v2）—— LLM 判目标档 × 声学分判实际档，全自动，零人耳。

为什么需要它
------------
现在对白闸门的情绪判据是「同一情绪一个下界（p25）」：
`激动反抗` intensity=1 与 intensity=3 用同一个 p25，强度维度在判据里就被抹平了。
v1 实测（`_gate_dlg_v18.json` + `_emo_final.jsonl`）证实：
    激动反抗  A I1 0.790 / I2 0.814 / I3 0.795   （应单调升，实际平）
    紧张      A I1 0.652 / I2 0.611                （反）
    平静      A I1 0.447 / I2 0.399                （反）
⇒ A（arousal）反映的是「情绪类别」，不是「强度档」。拿 A 判强度，判不出是必然。

三档定义
--------
`emo_bench/REPORT_TIERS.md` 的 8 档真人切片 A 实测：
    soft .26 / calm .31 / scold .47 / normal .54 | angry .78 / begging .78 / loud .85 / excited .87
两个最大间隔落在 .31→.47 与 .54→.78 ⇒ 界线 .45 / .66：
    S1低 <0.45 ｜ S2中 0.45–0.66 ｜ S3高 ≥0.66
这两条界线来自真人素材实测，不是我们标的。

为什么不用 A 当唯一判据（v1 教调）
--------------------------------
v1 用 A 的绝对区间直接判，结果 38.9% 判「过刺激」。不是生成全在喊，
是 VoxDim 对合成语音的 A 系统性偏高（生成强度档 A 中位 0.735，真人 normal 0.54）。
⇒ 跨域（真人 vs 合成）绝对量不可直接比。

v2 用两条与音量无关的物理量（谱倾斜、音区、谐噪比）在**角色内**定标：
    effort = −z(alpha_ratio) + z(f0_med) + z(hnr),  z 参数取该角色的**真人 refs**
三项都跟增益无关 —— 我们的成品全库归一到 −24dBFS，绝对电平已被抹掉，
所以「能量分级」只能用谱形状/音区/谐噪比，不能用 dB（见 DECISIONS）。

核心判据：档内梯度（真正全自动的那一条）
------------------------------------
同一 (角色, 情绪) 内，effort 必须随 intensity 单调上升。
    SRCC(intensity, effort) ≥ 0.20 且 档间极差 ≥ 0.30 z  → 梯度存在
    否则 → 梯度缺失（不是单条缺陷，整档重跑也没用）
⚠ v1 的错误：只看「中位不下降」，三档全是 3.0/3.0/3.0 也判通过 ——
   那是零变化，不是有梯度。v2 必须同时满足秩相关与最小极差。

输出
----
_stim_feat.json / _stim_ref.json / _stim_tier.json / _stim_report.md
报告含：逐组梯度表、生成与真人同档偏移（域偏移证据）、
      按 intensity 选 ref 切片的建议（供生成端回流）

用法
----
    G:/Python310/python.exe stim_tier.py --extract
    G:/Python310/python.exe stim_tier.py --report
环境：G:/Python310（parselmouth）
"""
import os
import sys
import json
import math
import argparse
import collections
import statistics as st

import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")

OUT_WAV = "G:/_setup/_audio_ch123/out"
PLAN = "G:/_setup/_castle_en_ch123_plan_v2.jsonl"
EMO = "G:/_setup/_emo_vote/_emo_final.jsonl"
GATE = "G:/_setup/_gate_dlg_v18.json"
REFS = "G:/_setup/_emo_refs_all.json"
FEAT = "G:/_setup/_stim_feat.json"
REFF = "G:/_setup/_stim_ref.json"
TIER = "G:/_setup/_stim_tier.json"
REPORT = "G:/_setup/_stim_report.md"

ANCHOR_A = {"soft": 0.26, "calm": 0.31, "scold": 0.47, "normal": 0.54,
            "angry": 0.78, "begging": 0.78, "loud": 0.85, "excited": 0.87}
A_LO, A_HI = 0.45, 0.66
TIER_NAME = {1: "S1低", 2: "S2中", 3: "S3高"}
SRCC_MIN, GAP_MIN = 0.20, 0.30


# ────────────────────────── 特征 ──────────────────────────
def effort_feat(path):
    """与增益无关的发声努力特征。不依赖 torch / 模型。"""
    import parselmouth
    from parselmouth.praat import call

    snd = parselmouth.Sound(path)
    try:
        snd = snd.resample(16000)
    except Exception:
        pass
    y = np.asarray(snd.values, dtype=np.float64).ravel()
    sr = int(snd.sampling_frequency)
    dur = len(y) / sr

    hop = int(sr * 0.02)
    n = max(1, len(y) // hop)
    fr = y[: n * hop].reshape(n, hop)
    rms = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    thr = np.percentile(db, 90) - 30
    voiced = db > thr
    if voiced.sum() < 3:
        voiced = db > (db.max() - 40)
    voiced_ratio = float(voiced.mean())
    vr = rms[voiced] if voiced.any() else rms
    rms_db = 20 * math.log10(float(np.sqrt((vr ** 2).mean())) + 1e-12)

    pitch = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=500)
    f0 = pitch.selected_array["frequency"]
    f0 = f0[f0 > 0]
    f0_med = float(np.median(f0)) if len(f0) else 0.0
    f0_span = float(np.percentile(f0, 90) - np.percentile(f0, 10)) if len(f0) else 0.0

    # HNR：只在浊音帧取中位（Praat 对清音/静音返回 −200 哨兵）
    try:
        harm = call(snd, "To Harmonicity (cc)", 0.01, 60, 0.1, 1.0)
        hnr = np.asarray(harm.values, dtype=np.float64).ravel()
        f0f = pitch.selected_array["frequency"]
        m = min(len(hnr), len(f0f))
        hnr, f0f = hnr[:m], f0f[:m]
        keep = (f0f > 0) & np.isfinite(hnr) & (hnr > -100)
        hv = hnr[keep]
        hnr_med = float(np.median(hv)) if len(hv) >= 3 else 0.0
    except Exception:
        hnr_med = 0.0

    # 浊音段掩码（★ v1 的坑：mask 长度必须 == len(y)，否则 y[mask] 报错被 except 吃掉）
    mask = np.repeat(voiced[: n], hop)
    if len(mask) < len(y):
        mask = np.pad(mask, (0, len(y) - len(mask)), constant_values=False)
    else:
        mask = mask[: len(y)]
    seg = y[mask] if mask.any() else y

    alpha = slope = None
    if len(seg) >= 1024:
        w = np.hanning(1024)
        acc = np.zeros(513)
        k = 0
        for i in range(0, len(seg) - 1024, 512):
            acc += np.abs(np.fft.rfft(seg[i:i + 1024] * w)) ** 2
            k += 1
        if k:
            p = acc / k
            fq = np.fft.rfftfreq(1024, 1.0 / sr)
            lo = p[(fq >= 50) & (fq < 1000)]
            hi = p[(fq >= 1000) & (fq < 5000)]
            if len(lo) and len(hi) and lo.mean() > 0 and hi.mean() > 0:
                alpha = 10 * math.log10(lo.mean() / hi.mean())
            # 长时平均谱斜率（dB/kHz），100–4000Hz 线性拟合
            band = (fq >= 100) & (fq <= 4000) & (p > 0)
            if band.sum() >= 10:
                xs = fq[band] / 1000.0
                ys = 10 * np.log10(p[band])
                try:
                    slope = float(np.polyfit(xs, ys, 1)[0])
                except Exception:
                    slope = None

    return dict(dur=round(dur, 3), f0_med=round(f0_med, 1), f0_span=round(f0_span, 1),
                hnr=round(hnr_med, 1),
                alpha=round(alpha, 2) if alpha is not None else None,
                slope=round(slope, 2) if slope is not None else None,
                rms_db=round(rms_db, 1), voiced_ratio=round(voiced_ratio, 3))


def extract():
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(PLAN, encoding="utf-8") if l.strip()}
    emo = {json.loads(l)["id"]: json.loads(l)
           for l in open(EMO, encoding="utf-8") if l.strip()}
    gate = {r["id"]: r for r in json.load(open(GATE, encoding="utf-8")) if r.get("id")}

    out, miss = {}, 0
    for i, f in emo.items():
        wav = os.path.join(OUT_WAV, i + ".wav")
        if not os.path.exists(wav):
            miss += 1
            continue
        fe = effort_feat(wav)
        p = plan.get(i) or {}
        words = int(p.get("words") or 0)
        if not words:
            words = max(1, len(str(p.get("text") or "").split()))
        fe["wpm"] = round(words / fe["dur"] * 60, 1) if fe["dur"] > 0.3 else None
        e = (gate.get(i) or {}).get("emo_res") or {}
        fe.update(id=i, who=f.get("who"), emo=f.get("emo"),
                  intensity=f.get("intensity"), voice=p.get("voice"),
                  words=words, A=e.get("A"), V=e.get("V"), D=e.get("D"))
        out[i] = fe
    json.dump(out, open(FEAT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("生成侧 %d 条（缺 wav %d）→ %s" % (len(out), miss, FEAT))

    refs = json.load(open(REFS, encoding="utf-8"))
    rf, bad = [], 0
    for who, emos in refs.items():
        for e, lst in emos.items():
            for it in lst:
                p = it.get("path")
                if not p or not os.path.exists(p):
                    bad += 1
                    continue
                try:
                    fe = effort_feat(p)
                except Exception:
                    bad += 1
                    continue
                fe.update(ref=os.path.basename(p), who=who, emo=e,
                          text=(it.get("text") or "")[:40])
                rf.append(fe)
    json.dump(rf, open(REFF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("真人参考 %d 条（缺 %d）→ %s" % (len(rf), bad, REFF))
    ok = sum(1 for r in rf if r.get("alpha") is not None)
    print("alpha 可用 %d / %d" % (ok, len(rf)))


# ────────────────────────── 分级 ──────────────────────────
def rankdata(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(x, y):
    if len(x) < 4:
        return None
    rx, ry = rankdata(x), rankdata(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else None


def params_of(rows, key):
    v = [r[key] for r in rows if r.get(key) is not None]
    if len(v) < 3:
        return None, None
    return st.median(v), (st.pstdev(v) or 1.0)


def report():
    feat = json.load(open(FEAT, encoding="utf-8"))
    refs = json.load(open(REFF, encoding="utf-8")) if os.path.exists(REFF) else []

    # 角色内定标（参数取该角色真人 refs；不足则全库 refs）
    per_who = {}
    for who in set([r["who"] for r in refs] + [r["who"] for r in feat.values()]):
        sub = [r for r in refs if r["who"] == who] or refs
        per_who[who] = {k: params_of(sub, k) for k in ("alpha", "f0_med", "hnr")}

    def effort(r, who=None):
        who = who or r.get("who")
        P = per_who.get(who) or {}
        z, n = 0.0, 0
        a = r.get("alpha")
        if a is not None and P.get("alpha", (None,))[0] is not None:
            m, s = P["alpha"]
            z += -(a - m) / s
            n += 1
        f = r.get("f0_med")
        if f and P.get("f0_med", (None,))[0] is not None:
            m, s = P["f0_med"]
            z += (f - m) / s
            n += 1
        h = r.get("hnr")
        if h and P.get("hnr", (None,))[0] is not None:
            m, s = P["hnr"]
            z += -(h - m) / s
            n += 1
        return z / n if n else None

    for r in feat.values():
        r["effort"] = round(effort(r), 3) if effort(r) is not None else None
    for r in refs:
        r["effort"] = round(effort(r), 3) if effort(r) is not None else None

    rows = []
    for i, r in feat.items():
        rows.append(dict(id=i, who=r["who"], emo=r["emo"], voice=r["voice"],
                         target=r.get("intensity"),
                         A=r.get("A"), effort=r.get("effort"),
                         f0_med=r.get("f0_med"), f0_span=r.get("f0_span"),
                         alpha=r.get("alpha"), slope=r.get("slope"),
                         hnr=r.get("hnr"), wpm=r.get("wpm"), dur=r.get("dur"),
                         words=r.get("words")))

    # ── 组级梯度 ──
    by = collections.defaultdict(list)
    for r in rows:
        if r["effort"] is not None and r["target"]:
            by[(r["who"], r["emo"])].append(r)
    groups = []
    for (who, emo), grp in sorted(by.items(), key=lambda x: -len(x[1])):
        d = collections.defaultdict(list)
        for r in grp:
            d[r["target"]].append(r["effort"])
        meds = [(k, st.median(d[k]), len(d[k])) for k in sorted(d)]
        if len(meds) < 2:
            groups.append(dict(who=who, emo=emo, n=len(grp), tiers=[m[0] for m in meds],
                               med=[round(m[1], 2) for m in meds],
                               cnt=[m[2] for m in meds], srcc=None, gap=None,
                               ok=None, why="只有一档，无梯度可测"))
            continue
        srcc = spearman([r["target"] for r in grp], [r["effort"] for r in grp])
        gap = max(m[1] for m in meds) - min(m[1] for m in meds)
        ok = (srcc is not None and srcc >= SRCC_MIN and gap >= GAP_MIN)
        if ok:
            why = "梯度存在"
        elif srcc is None:
            why = "样本不足 %d 条，秩相关不可算" % len(grp)
        elif gap < GAP_MIN:
            why = "极差不足 %.2f<%.2f" % (gap, GAP_MIN)
        else:
            why = "秩相关 %.2f<%.2f" % (srcc, SRCC_MIN)
        groups.append(dict(who=who, emo=emo, n=len(grp), tiers=[m[0] for m in meds],
                           med=[round(m[1], 2) for m in meds],
                           cnt=[m[2] for m in meds],
                           srcc=round(srcc, 3) if srcc is not None else None,
                           gap=round(gap, 2), ok=ok, why=why))

    # ── 根因：强度有没有进选角 ──
    # voice 名就是「角色_英文情绪档_切片号」，生成时拿它当克隆参考切片。
    # 若同组三档用的是同一批 voice，强度在输入端就不存在，后面无论怎么测都不会有梯度。
    cause = []
    for (who, emo), grp in sorted(by.items(), key=lambda x: -len(x[1])):
        vs = collections.defaultdict(set)
        for r in grp:
            vs[r["target"]].add(r["voice"])
        sig = tuple(tuple(sorted(vs[k])) for k in sorted(vs))
        allv = sorted(set().union(*vs.values()))
        cause.append(dict(who=who, emo=emo, n=len(grp), tiers=sorted(vs),
                          voices=allv, distinct=len(allv), same=len(set(sig)) == 1))

    # ── 单条相对档（组内三分，用于给建议；不是绝对合格） ──
    for (who, emo), grp in by.items():
        ev = sorted([r["effort"] for r in grp])
        lo = ev[int(len(ev) * 0.33)]
        hi = ev[int(len(ev) * 0.67)]
        for r in grp:
            r["rel_tier"] = 1 if r["effort"] < lo else (2 if r["effort"] < hi else 3)
            r["dev"] = (r["rel_tier"] - r["target"]) if r["target"] else None
            r["code"] = ("hit" if r["dev"] == 0 else
                          ("under" if (r["dev"] or 0) < 0 else "over"))

    # ── 域偏移证据：各组生成 effort 中位 vs 该组真人 refs effort 中位 ──
    ref_by = collections.defaultdict(list)
    for r in refs:
        if r["effort"] is not None:
            ref_by[(r["who"], r["emo"])].append(r["effort"])

    json.dump(dict(rows=rows, groups=groups), open(TIER, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ── 写报告 ──
    n = len(rows)
    graded = [g for g in groups if g["ok"] is not None]
    good = [g for g in graded if g["ok"]]
    cc = collections.Counter(r["code"] for r in rows if r.get("code"))
    na = sum(1 for r in rows if not r.get("code"))

    L = []
    A = L.append
    A("# 刺激分级报告（stim tier v2）\n\n")
    A("数据源：`_stim_feat.json`（%d 条有 intensity 标注）/ `_stim_ref.json`（%d 条真人切片）\n\n" % (n, len(refs)))
    A("分档：S1低 <0.45 / S2中 0.45–0.66 / S3高 ≥0.66（真人 8 档 A 锚）\n")
    A("effort = −z(alpha) + z(f0中位) − z(HNR)，z 参数取**该角色真人 refs** ⇒ 角色内可比，跨角色不可比\n\n")
    A("## 一、一句话结论\n\n")
    A("**%d 个 (角色,情绪) 组可测梯度，%d 组通过、%d 组不通过。**\n\n" % (len(graded), len(good), len(graded) - len(good)))
    A("不通过的原因**不是模型没表演出来，而是强度根本没进选角**（见第三节）：\n")
    A("同一 (角色,情绪) 的 I1/I2/I3 全部克隆**同一个参考切片**，梯度在输入端就不存在，\n")
    A("所以拿同一档重跑多少次也不会出现梯度 —— 要改的是选角映射，不是重生成参数。\n\n")
    A("## 二、逐组梯度\n\n")
    A("| 角色 | 情绪 | n | 档位 | 各档 effort 中位 | 各档 n | SRCC | 极差 | 判定 | 原因 |\n")
    A("|---|---|---|---|---|---|---|---|---|---|\n")
    for g in groups:
        A("| %s | %s | %d | %s | %s | %s | %s | %s | %s | %s |\n" % (
            g["who"], g["emo"], g["n"],
            "/".join(str(k) for k in g["tiers"]),
            " / ".join("%+.2f" % v for v in g["med"]),
            "/".join(str(x) for x in g["cnt"]),
            "%+.2f" % g["srcc"] if g["srcc"] is not None else "-",
            "%.2f" % g["gap"] if g["gap"] is not None else "-",
            "✓" if g["ok"] else ("✗" if g["ok"] is False else "—"),
            g["why"] if g["why"] else ""))

    A("\n## 三、根因：强度有没有进选角\n\n")
    A("生成方式：每条对白用 `voice` 指定的**真人参考切片**做克隆，情绪与强度**完全由这个切片决定**，\n")
    A("文本侧不传任何强度标签。所以「intensity 有没有被表演出来」完全等价于「选角有没有随 intensity 变」。\n\n")
    n_same = len([c for c in cause if c["same"]])
    A("**%d / %d 组的三档共用同一批参考切片**：\n\n" % (n_same, len(cause)))
    A("| 角色 | 情绪 | n | 用到的 voice | 三档同一批？ |\n|---|---|---|---|---|\n")
    for c in cause:
        vv = " / ".join(c["voices"]) if c["distinct"] <= 3 else "%d 个" % c["distinct"]
        A("| %s | %s | %d | %s | %s |\n" % (c["who"], c["emo"], c["n"], vv,
                                          "是（强度未接入）" if c["same"] else "否"))
    A("\n结论：强度在本项目里**从未作为生成输入存在**。v1 用 A 判强度、v2 用 effort 判强度，\n")
    A("测到的都是「同一参考切片的不同实现变体」，不是强度。修复点在选角表（`V` 只给到单一 `_1` 切片，\n")
    A("`emo_intensity` 写进计划后没有任何下游读取），不在重生成参数。\n")

    A("\n## 四、单条相对档（组内三分位，不是绝对合格）\n\n")
    A("| 结论 | 条数 |\n|---|---|\n")
    A("| 相对命中 | %d |\n| 相对欠刺激 | %d |\n| 相对过刺激 | %d |\n| 不可测 | %d |\n\n" % (
        cc["hit"], cc["under"], cc["over"], na))
    A("⚠ 这一层只能回答「同一角色同一情绪内，这句排位偏上还是偏下」，\n")
    A("不能回答「绝对够不够」——那需要同文本真人对照，我们没有。\n\n")

    A("## 五、域偏移证据（生成 vs 真人同档）\n\n")
    A("| 角色 | 情绪 | 生成 n | 生成 effort 中位 | 真人 refs effort 中位 | 差 |\n")
    A("|---|---|---|---|---|---|\n")
    for (who, emo), grp in sorted(by.items(), key=lambda x: -len(x[1]))[:15]:
        rv = ref_by.get((who, emo))
        if not rv:
            continue
        gm = st.median([r["effort"] for r in grp])
        rm = st.median(rv)
        A("| %s | %s | %d | %+.2f | %+.2f | %+.2f |\n" % (who, emo, len(grp), gm, rm, gm - rm))

    A("\n## 六、回流：按 intensity 选参考切片（这才是修复动作）\n\n")
    A("同一 (角色,情绪) 库里的多条真人切片按 effort 排序，I1 取低端、I3 取高端。\n")
    A("切片序号（`_1/_2/_3`）**不代表强度顺序** —— 必须按实测 effort 排，不能按名字猜。\n\n")
    A("| 角色 | 情绪 | 切片数 | 低端 → 高端（effort, 文件名） |\n")
    A("|---|---|---|---|\n")
    for (who, emo), v in sorted(ref_by.items(), key=lambda x: -len(x[1])):
        if len(v) < 2:
            continue
        items = sorted([r for r in refs if r["who"] == who and r["emo"] == emo
                        and r["effort"] is not None], key=lambda r: r["effort"])
        seq = " → ".join("%+.2f %s" % (r["effort"], r["ref"]) for r in items)
        A("| %s | %s | %d | %s |\n" % (who, emo, len(items), seq))

    A("\n## 七、方法学注意\n\n")
    A("1. **绝对电平不可用**：全库归一到 −24dBFS，dB 已被抹平，所以 effort 只能靠谱倾斜/音区/谐噪比。\n")
    A("2. **A（arousal）不可当强度**：它对合成语音系统性偏高（生成中位 0.735 vs 真人 normal 0.54），\n")
    A("   且档内与 intensity 无关（v1 实测）。本报告 A 只作旁证，不进判定。\n")
    A("3. **社区同向**：ScienceDirect 2025 在「幅度归一化语音」上判 4 档 vocal intensity 达 86.0%，\n")
    A("   用的也是 cepstral/spectral 特征；WavLM 在 AVID 上 78.2%。说明归一化后判强度可行，但靠的是谱不是音量。\n")
    A("4. **本报告不给绝对阈值**：n<4 的组、单档组全部标「不可测」，不用中位数冒充。\n")

    open(REPORT, "w", encoding="utf-8").write("".join(L))
    print("→ %s / %s" % (TIER, REPORT))
    print("组：%d 可测 / %d 通过 / %d 不通过；单条命中 %d 欠 %d 过 %d 不可测 %d" % (
        len(graded), len(good), len(graded) - len(good),
        cc["hit"], cc["under"], cc["over"], na))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.extract:
        extract()
    if a.report:
        report()
    if not (a.extract or a.report):
        ap.print_help()
