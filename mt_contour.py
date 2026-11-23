# -*- coding: utf-8 -*-
"""mt_contour.py —— 句内 F0 轮廓 + 能量轮廓比对（语调 / 重音检测）

必须用 G:/Python310/python.exe 跑（parselmouth 只装在这个环境）。

设计依据（全部为实测，不是推测）：
- 21 点 **F0** 轮廓的跨候选 Pearson 中位只有 **0.245**，与异文本无差别
  ⇒ F0 跨候选相关**没有绝对量纲**，只用于相对排序（W_F0 = 0），不进分数。
- 21 点 **能量**轮廓：同文本 0.913（p10 0.521）vs 异文本 0.668（p10 0.288）
  ⇒ 净间隔 0.245，**唯一有绝对量纲的跨候选判据**。
- DTW 对齐后 F0 相关 0.878、异文本 0.832 ⇒ 天花板效应，禁止进分（只写诊断字段）。
- rubberband 拉伸前后 F0 轮廓相关 0.862、中位偏差 0.46 st（p90 1.02）
  ⇒ 任何 F0 阈值分辨率下限 ≈ 1 半音。
- 母带陈述句 span 4.30 st / tail -1.70；TTS 候选 span 7.13 / tail25 中位 -2.66（p90 +15.1）
  ⇒ 只借「符号」与「量级」，不移植绝对形状。
- contour_bank.json 的 question 原型 n=1 且斜率 -4.88（负，与常识矛盾）⇒ 作废，不引用。
- n_voiced 少 / 句子短 与「坏」的关系是**反向**的（AUC 0.141）⇒ 绝不把短句当坏。

三层判据：
  M1 句内自洽（主力）—— 帧间 F0 突跳 / 浊音覆盖 / 跳变频率
  M2 能量跨候选一致 —— 留一中位相关 + 相对 gap
  M3 标点符号规则 —— 陈述类末段不宜上扬；问句末段不宜强下沉（弱告警）
  M4 重音位置 —— 能量峰位在候选间位移过大则标记（只列不打分）

用法：
  G:/Python310/python.exe mt_contour.py --selftest
  G:/Python310/python.exe mt_contour.py --plan mt_plan3b.json \\
      --dirs _mt_raw_s42,_mt_raw_s1234,_mt_raw_srate --chs ch1 --jobs 8
"""
import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import parselmouth                      # noqa: E402
import soundfile as sf                  # noqa: E402
from prosody_arc import read_f0, clean_f0          # noqa: E402  与 contour_bank 同源尺子
from transplant_prosody import norm_contour        # noqa: E402

# ===== 全局 =====
NPT = 21
F0_FLOOR, F0_CEIL, F0_STEP = 55.0, 420.0, 0.01
F0_MAX_DEV_ST = 7.0
SMOOTH_S = 0.30
MIN_VOICED_FRAMES = 40          # 0.40s；实测 nv<40 占 3%
L2_MIN_VOICED_FRAMES = 60
E_FRAME = 0.05                  # ★ 5 万次对照选定：50ms 帧 AUC 0.934（20ms 只有 0.796）
E_REL_DB = -30.0                # ★ 峰值 −30dB 门；−35 是实测最差的一档（AUC 0.796）
E_ABS_DB = -60.0                # 绝对门：峰值低于此判为全静音（相对门对全零信号会全部放行）
# ===== L1 =====
L1_JUMP_P90_WARN = 1.20         # 实测 p99=1.27
L1_JUMP_MAX_WARN = 6.0
L1_JUMP_RATE_WARN = 4.0         # 实测中位 1.57
L1_JUMP_CNT_ST = 6.0            # 单次跳变幅度门槛（半音）
L1_JUMP_CNT_WARN = 2            # ★ 实测 |jump|>6st 的次数：中位 0 / p95 1 / max 2 / >=2 占 2%
L1_JUMP_CNT_HARD = 3            # 实测真实数据最大只有 2 ⇒ >=3 为零误杀的硬门槛
L1_COV_WARN = 0.30              # 实测 p10=0.36
L1_F0_MED_MAX = 140.0           # 高于此为倍频误判（不是"音高偏高"，那是 mt_score 的活）
# ===== L2 =====
L2_E_CORR_WARN = 0.30           # 同文本能量 p10=0.32（50ms/−30dB 参数下实测）
L2_E_GAP_WARN = 0.20
L2_FEAT_Z_MAX = 3.5
L2_PAIR_STABLE = 0.30
# ===== L3 / M4 =====
L3_TAIL_WARN = 6.0              # 实测陈述候选 25% 超过 +6；用 0 会命中 48%（废）
L3_END_WARN = 1.0
L3_Q_FALL_WARN = -6.0
L3_MIN_DUR = 2.0                # 短句末段帧数不足，不判末段走向
REACCENT_SHIFT = 0.75          # ★ 峰位极差是**连续分布**（中位 0.40 / p90 0.75），没有自然断点
                               #   ⇒ 阈值只能取 p95 作"参考清单"，绝不进分数、不算硬门槛
# ===== 汇总权重 =====
W_L1, W_E, W_L3, W_F0 = 0.50, 0.30, 0.20, 0.0


# ---------------------------------------------------------------- 帧级提取
def read_f0_arr(y, sr):
    """数组版 F0（供自测用）。参数与 prosody_arc.read_f0 完全一致。"""
    snd = parselmouth.Sound(np.asarray(y, dtype=np.float64), sampling_frequency=float(sr))
    pitch = snd.to_pitch_ac(time_step=F0_STEP, pitch_floor=F0_FLOOR, pitch_ceiling=F0_CEIL,
                            voicing_threshold=0.35, octave_jump_cost=1.0, octave_cost=0.01)
    f0 = np.asarray(pitch.selected_array["frequency"], dtype=np.float64)
    t = np.asarray(pitch.xs(), dtype=np.float64)
    return f0, t, float(snd.duration)


def unit_profile(f0, t, npt=NPT, smooth_s=SMOOTH_S):
    """整句 21 点半音轮廓。时间用**墙钟**归一化，跨停顿线性桥接。

    返回 (dict, None) 或 (None, 原因串)。
    """
    v = f0 > 0
    nv = int(v.sum())
    if nv < MIN_VOICED_FRAMES:
        return None, "NAN-FEW-FRAMES(%d)" % nv
    tv, fv = t[v], f0[v]
    med = float(np.median(fv))
    if med <= 0:
        return None, "NAN-NO-MED"
    if med > L1_F0_MED_MAX:
        # 整句中位偏高 ⇒ 多半是倍频误判，轮廓不可信。不要当成"音高偏高"去判坏。
        return None, "NAN-OCTAVE(%.0fHz)" % med
    u, st, med = norm_contour(tv, fv)
    span = float(tv[-1] - tv[0])
    if span <= 1e-3:
        return None, "NAN-SPAN"
    grid = np.linspace(0.0, 1.0, npt)
    prof_raw = np.interp(grid, u, st)
    # 平滑：重采样 200 点 → 展宽 = smooth_s/span*200 的滑动平均（边缘复制，避免边界衰减）
    dense = np.interp(np.linspace(0.0, 1.0, 200), u, st)
    win = int(round(smooth_s / max(span, 1e-3) * 200)) | 1
    if win < 3:
        win = 3
    if win < 200:
        kern = np.ones(win) / float(win)
        sm = np.convolve(np.pad(dense, (win // 2, win // 2), mode="edge"), kern, mode="valid")
    else:
        sm = dense
    prof = np.interp(grid, np.linspace(0.0, 1.0, 200), sm)
    # 句末 25%（斜率只用未平滑，平滑会把缓降削掉一半）
    tm = u >= 0.75
    tail25 = 0.0
    if int(tm.sum()) >= 4:
        A = np.vstack([u[tm], np.ones(int(tm.sum()))]).T
        tail25 = float(np.linalg.lstsq(A, st[tm], rcond=None)[0][0])
    tm3 = tv >= (tv[-1] - 0.30)
    tail300 = 0.0
    if int(tm3.sum()) >= 4 and (tv[-1] - tv[tm3][0]) > 0.05:
        A = np.vstack([tv[tm3], np.ones(int(tm3.sum()))]).T
        tail300 = float(np.linalg.lstsq(A, st[tm3], rcond=None)[0][0])
    n_breaks = int((np.diff(tv) > 0.22).sum())
    cov = nv * F0_STEP / span
    return dict(
        prof=prof, prof_raw=prof_raw, f0_med=med,
        voiced_s=float(nv * F0_STEP), span_s=span, cov=float(cov),
        n_voiced=nv, n_breaks=n_breaks,
        span_st=float(np.percentile(st, 95) - np.percentile(st, 5)),
        arc_st=float(prof_raw[-1] - prof_raw[0]),
        start_st=float(prof_raw[0]), end_st=float(prof_raw[-1]),
        peak_pos=float(int(np.argmax(prof_raw)) / float(npt - 1)),
        tail25=tail25, tail300=tail300,
    ), None


def energy_profile(y, sr, npt=NPT, frame=E_FRAME, rel_db=E_REL_DB):
    """21 点能量轮廓（20ms 不重叠帧 RMS-dB，减去自身中位以消除整体电平差）。"""
    w = int(round(frame * sr))
    n = len(y) // w
    if n < 5:
        return None
    db = 20.0 * np.log10(np.sqrt((y[:n * w].reshape(n, w) ** 2).mean(1)) + 1e-12)
    if float(db.max()) < E_ABS_DB:
        return None
    thr = float(db.max() + rel_db)
    m = db > thr
    if int(m.sum()) < 5:
        return None
    idx = np.where(m)[0]
    seg = db[int(idx[0]):int(idx[-1]) + 1]
    prof = np.interp(np.linspace(0.0, 1.0, npt), np.linspace(0.0, 1.0, len(seg)), seg)
    prof = prof - float(np.median(prof))
    return dict(e_prof=prof, e_std=float(np.std(prof)),
                e_peak_pos=float(int(np.argmax(prof)) / float(npt - 1)),
                e_head=float(np.mean(prof[:4])), e_tail=float(np.mean(prof[-4:])),
                e_range=float(prof.max() - prof.min()))


# ---------------------------------------------------------------- L1 句内自洽
def l1_checks(f0, t, ps):
    v = f0 > 0
    idx = np.where(v)[0]
    jumps = []
    for k in range(len(idx) - 1):
        i, j = int(idx[k]), int(idx[k + 1])
        if t[j] - t[i] <= 0.03 and f0[i] > 0 and f0[j] > 0:
            jumps.append(abs(12.0 * math.log2(f0[j] / f0[i])))
    J = np.asarray(jumps, dtype=np.float64)
    jp90 = float(np.percentile(J, 90)) if len(J) else 0.0
    jmax = float(J.max()) if len(J) else 0.0
    # ★ p90 是抗离群统计量，抓不到"少数几处突跳"（实测 4 个极端值 / 200 个跳变值不改变 p90）。
    #   "F0 突跳"本质就是少量事件 ⇒ 必须数**次数**，不能用分位数。
    jcnt6 = int((J > L1_JUMP_CNT_ST).sum()) if len(J) else 0
    span = max(ps["span_s"], 1e-3)
    jrate = float((J > 1.5).sum() / span) if len(J) else 0.0
    cov, nv = ps["cov"], ps["n_voiced"]
    pen = (0.40 * max(0.0, (jp90 - 0.80) / 0.40)
           + 0.25 * max(0.0, (0.35 - cov) / 0.15)
           + 0.25 * min(1.0, jcnt6 / 2.0)
           + 0.10 * max(0.0, (jrate - 2.0) / 2.0))
    flags = []
    if jp90 > L1_JUMP_P90_WARN:
        flags.append("JUMP")
    if cov < L1_COV_WARN:
        flags.append("LOWCOV")
    if jrate > L1_JUMP_RATE_WARN:
        flags.append("JUMPRATE")
    if jcnt6 >= L1_JUMP_CNT_WARN:
        flags.append("JUMPCNT(%d)" % jcnt6)
    hard = (nv < MIN_VOICED_FRAMES) or (jcnt6 >= L1_JUMP_CNT_HARD)
    return dict(jump_p90=jp90, jump_max=jmax, jump_rate=jrate, jump_cnt6=jcnt6,
                l1_pen=float(min(1.0, max(0.0, pen))), l1_flags=flags, l1_hard=bool(hard))


# ---------------------------------------------------------------- L3 标点规则
def punct_class(text):
    """与 build_contour_bank.py 完全相同的尾巴处理，保证与 contour_bank 可比。"""
    tail = (text or "").rstrip("\"') ").rstrip()
    if tail.endswith(","):
        return "comma"
    if tail.endswith("?"):
        return "question"
    if tail.endswith("!"):
        return "exclam"
    if tail.endswith("."):
        return "period"
    return "none"


def l3_check(cls, ps, dur=99.0):
    """末段走向的符号规则。

    ★ comma / none 类**不做**「末段应下降」判据：逗号处本来就该轻扬或持平
      （`his father said, nervously,` 这种归属尾巴后面还要接对白，上扬是对的）。
      全库 170 条逗号结尾，套陈述句规则会成片误杀。
    ★ dur < L3_MIN_DUR 的短句末段帧数不足，一律不判，只标 SHORT。
    """
    t25, end = ps["tail25"], ps["end_st"]
    if dur < L3_MIN_DUR:
        return dict(expect="none", violated=False, l3_pen=0.0, l3_msg="")
    if cls == "period":
        bad = (t25 > L3_TAIL_WARN) and (end > L3_END_WARN)
        pen = min(1.0, max(0.0, (t25 - L3_TAIL_WARN) / 8.0)) if bad else 0.0
        return dict(expect="fall", violated=bool(bad), l3_pen=float(pen),
                    l3_msg=("END-RISE(%.1f/%.1f)" % (t25, end)) if bad else "")
    if cls in ("comma", "none"):
        return dict(expect="weak", violated=False, l3_pen=0.0, l3_msg="")
    # question / exclam：样本量 5+1，统计无法标定 ⇒ 只做弱告警，l3_pen 恒 0
    bad = t25 < L3_Q_FALL_WARN
    tag = "Q-FALL" if cls == "question" else "X-FALL"
    return dict(expect="rise", violated=bool(bad), l3_pen=0.0,
                l3_msg=("%s(%.1f)" % (tag, t25)) if bad else "")


# ---------------------------------------------------------------- L2 跨候选
def corr_matrix(seqs):
    n = len(seqs)
    cm = np.full((n, n), np.nan)
    for i in range(n):
        a = np.asarray(seqs[i], dtype=np.float64)
        if np.std(a) < 1e-9:
            continue
        for j in range(i + 1, n):
            b = np.asarray(seqs[j], dtype=np.float64)
            if len(a) != len(b) or np.std(b) < 1e-9:
                continue
            r = float(np.corrcoef(a, b)[0, 1])
            if np.isfinite(r):
                cm[i, j] = cm[j, i] = r
    return cm


def consensus(cm):
    """留一中位相关 + 相对 gap。n=2 只给 stable 标记，绝不判离群。"""
    n = int(cm.shape[0])
    if n < 2:
        return dict(loo=np.full(n, np.nan), c_star=float("nan"),
                    gap=np.full(n, np.nan), outlier=None, stable=False, n=n)
    R = cm.copy()
    np.fill_diagonal(R, np.nan)
    with np.errstate(all="ignore"):
        loo = np.nanmedian(R, axis=1)
    if n == 2:
        r = float(cm[0, 1])
        return dict(loo=np.array([r, r]), c_star=r, gap=np.zeros(2),
                    outlier=None, stable=bool(np.isfinite(r) and r >= L2_PAIR_STABLE), n=2)
    c_star = float(np.nanmedian(loo))
    gap = loo - c_star
    j = int(np.nanargmin(loo)) if np.isfinite(loo).any() else None
    return dict(loo=loo, c_star=c_star, gap=gap, outlier=j, stable=True, n=n)


def _robust_z(x):
    x = np.asarray(x, dtype=np.float64)
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    if mad < 1e-9:
        return np.zeros_like(x)
    return 0.6745 * (x - med) / mad


# ---------------------------------------------------------------- 候选 / 单元
def analyze_candidate(job):
    """worker：单个 (单元, 种子) 的轮廓提取。必须模块级，供 ProcessPool 调用。"""
    uid, seed, path, text = job
    try:
        stt = os.stat(path)
    except OSError as e:
        return dict(uid=uid, seed=seed, path=path, nan_reason="ERR-STAT:%s" % e)
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=True)
        y = y.mean(1)
        f0, t, dur = read_f0(path)
        f0, _ = clean_f0(f0, F0_MAX_DEV_ST)
        ps, reason = unit_profile(f0, t)
        if ps is None:
            return dict(uid=uid, seed=seed, path=path, size=int(stt.st_size),
                        mtime=int(stt.st_mtime), dur=float(dur),
                        nan_reason=reason, cls=punct_class(text))
        ep = energy_profile(y, sr)
        l1 = l1_checks(f0, t, ps)
        l3 = l3_check(punct_class(text), ps, dur)
        rec = dict(uid=uid, seed=seed, path=path, size=int(stt.st_size),
                   mtime=int(stt.st_mtime), dur=float(dur), cls=punct_class(text),
                   nan_reason=None)
        rec.update({k: (v if not isinstance(v, np.ndarray) else [round(float(x), 3) for x in v])
                    for k, v in ps.items()})
        rec.update(l1)
        rec.update(l3)
        if ep:
            rec.update({k: ([round(float(x), 3) for x in v] if isinstance(v, np.ndarray)
                            else float(v)) for k, v in ep.items()})
        return rec
    except Exception as e:                                  # noqa: BLE001
        return dict(uid=uid, seed=seed, path=path, nan_reason="ERR:%s" % e,
                    cls=punct_class(text))


def analyze_unit(uid, text, recs):
    """单元级：算 L2（能量 / F0 两个场）+ M4，汇总 ct_pen 与 flag。"""
    cls = punct_class(text)
    ok = [r for r in recs if r.get("prof")]
    for r in recs:
        if not r.get("prof"):
            r["ct_pen"] = None
            r["ct_flag"] = "NAN"
    e_cm = corr_matrix([r["e_prof"] for r in ok if r.get("e_prof")]) if len(ok) >= 2 else None
    f_cm = corr_matrix([r["prof"] for r in ok]) if len(ok) >= 2 else None
    e_cs = consensus(e_cm) if e_cm is not None else None
    f_cs = consensus(f_cm) if f_cm is not None else None
    # M4 重音位置
    pps = [r["e_peak_pos"] for r in ok if r.get("e_peak_pos") is not None]
    peak_rng = float(max(pps) - min(pps)) if len(pps) >= 3 else None
    reaccent = bool(peak_rng is not None and peak_rng > REACCENT_SHIFT)
    zs = {}
    if len(ok) >= 4:
        for k in ("span_st", "arc_st", "tail25", "e_peak_pos"):
            vals = [r.get(k) for r in ok]
            if all(isinstance(v, float) for v in vals):
                zs[k] = _robust_z(vals)

    has_e = [i for i, r in enumerate(ok) if r.get("e_prof")]
    for i, r in enumerate(ok):
        n = len(ok)
        pen_e = 0.0
        r_e = float("nan")
        gap_e = float("nan")
        if e_cs is not None and i in has_e and r["n_voiced"] >= L2_MIN_VOICED_FRAMES:
            j = has_e.index(i) if i in has_e else -1
            if j >= 0:
                r_e = float(e_cs["loo"][j])
                gap_e = float(e_cs["gap"][j])
                if np.isfinite(r_e):
                    if n >= 3:
                        pen_e = min(1.0, max(0.0, (L2_E_CORR_WARN - r_e) / 0.30)
                                    * max(0.0, -gap_e / L2_E_GAP_WARN))
                    else:
                        pen_e = min(1.0, max(0.0, (L2_E_CORR_WARN - r_e) / 0.30) * 0.5)
        # F0 跨候选：只写排序信息，权重 0
        r_f0 = gap_f0 = float("nan")
        if f_cs is not None:
            r_f0 = float(f_cs["loo"][i])
            gap_f0 = float(f_cs["gap"][i])
        r["ct_re"] = None if not np.isfinite(r_e) else round(r_e, 3)
        r["ct_ge"] = None if not np.isfinite(gap_e) else round(gap_e, 3)
        r["ct_rf0"] = None if not np.isfinite(r_f0) else round(r_f0, 3)
        r["ct_gf0"] = None if not np.isfinite(gap_f0) else round(gap_f0, 3)
        r["pen_e"] = round(pen_e, 3)
        zflag = [k for k, z in zs.items() if abs(z[i]) > L2_FEAT_Z_MAX] if zs else []
        ct = W_L1 * r["l1_pen"] + W_E * pen_e + W_L3 * r["l3_pen"] + W_F0 * 0.0
        flags = list(r["l1_flags"])
        if r["l3_msg"]:
            flags.append(r["l3_msg"])
        if pen_e > 0.5:
            flags.append("E-OUT")
        if reaccent:
            flags.append("REACCENT")
        if zflag:
            flags.append("Z:" + ",".join(zflag))
        r["ct_pen"] = round(float(min(1.0, max(0.0, ct))), 3)
        r["ct_flag"] = ";".join(flags)
    unit = dict(text=text, cls=cls, n_cand=len(recs), n_ok=len(ok),
                e_peak_rng=None if peak_rng is None else round(peak_rng, 3),
                reaccent=reaccent, cands={str(r["seed"]): r for r in recs})
    if e_cs is not None:
        unit["l2_e"] = dict(c_star=round(float(e_cs["c_star"]), 3),
                            loo=[round(float(x), 3) for x in e_cs["loo"]],
                            gap=[round(float(x), 3) for x in e_cs["gap"]],
                            outlier=e_cs["outlier"], stable=bool(e_cs["stable"]))
    if f_cs is not None:
        unit["l2_f0"] = dict(c_star=round(float(f_cs["c_star"]), 3),
                             loo=[round(float(x), 3) for x in f_cs["loo"]],
                             gap=[round(float(x), 3) for x in f_cs["gap"]],
                             outlier=f_cs["outlier"], stable=bool(f_cs["stable"]))
    return unit


# ---------------------------------------------------------------- 批量
def batch(plan_path, dirs, chs, out_prefix, jobs=8, limit=0, ids=None):
    plan = json.load(open(plan_path, encoding="utf-8"))
    units = [p for p in plan if p["ch"] in chs and (not ids or p["id"] in ids)]
    if limit:
        units = units[:limit]
    jobs_list, meta = [], {}
    for p in units:
        meta[p["id"]] = p
        for d in dirs:
            fp = os.path.join(d, p["id"] + ".wav")
            if os.path.exists(fp):
                seed = os.path.basename(d).replace("_mt_raw_s", "")
                jobs_list.append((p["id"], seed, fp, p["text"]))
    print("单元 %d | 候选文件 %d | 进程 %d" % (len(units), len(jobs_list), jobs))
    t0 = time.time()
    out = []
    if jobs <= 1:
        for k, j in enumerate(jobs_list, 1):
            out.append(analyze_candidate(j))
            if k % 50 == 0:
                print("  %d/%d  %.0fs" % (k, len(jobs_list), time.time() - t0))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for k, r in enumerate(ex.map(analyze_candidate, jobs_list, chunksize=8), 1):
                out.append(r)
                if k % 100 == 0:
                    print("  %d/%d  %.0fs" % (k, len(jobs_list), time.time() - t0))
    by = {}
    for r in out:
        by.setdefault(r["uid"], []).append(r)
    result = {"meta": {"plan": plan_path, "dirs": list(dirs), "chs": list(chs),
                       "npt": NPT, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "consts": {k: v for k, v in globals().items()
                                  if k.isupper() and isinstance(v, (int, float))}},
              "units": {}}
    for ch in chs:
        us = {uid: analyze_unit(uid, meta[uid]["text"], recs)
              for uid, recs in by.items() if meta[uid]["ch"] == ch}
        result["units"].update(us)
        dst = "%s_%s.json" % (out_prefix, ch) if len(chs) > 1 else "%s.json" % out_prefix
        if len(chs) > 1:
            sub = dict(result)
            sub["units"] = us
            json.dump(sub, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            print("  → %s（%d 单元）" % (dst, len(us)))
    if len(chs) == 1:
        dst = "%s.json" % out_prefix
        json.dump(result, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        print("  → %s（%d 单元）" % (dst, len(result["units"])))
    nan = sum(1 for r in out if r.get("nan_reason"))
    print("完成 %.1fs | 候选 %d（不可测 %d，%.1f%%）"
          % (time.time() - t0, len(out), nan, 100.0 * nan / max(len(out), 1)))
    return result


# ---------------------------------------------------------------- 自测
def _mk(track):
    """把半音序列做成 (f0, t)：100Hz 基准。"""
    n = len(track)
    t = np.arange(n) * 0.01
    f0 = 100.0 * (2.0 ** (np.asarray(track, dtype=np.float64) / 12.0))
    return f0, t


def selftest():
    ok = True

    def chk(name, cond, extra=""):
        nonlocal ok
        print(("  PASS  " if cond else "  FAIL  ") + name + (("  " + extra) if extra else ""))
        ok = ok and bool(cond)

    print("== 1. 轮廓极性 ==")
    fall = np.linspace(0, -8, 120)
    rise = np.linspace(0, +8, 120)
    p1, e1 = unit_profile(*_mk(fall))
    p2, e2 = unit_profile(*_mk(rise))
    chk("fall/rise 都能提取", p1 is not None and p2 is not None, str(e1 or "") + str(e2 or ""))
    if p1 and p2:
        c_same = float(np.corrcoef(p1["prof"], p2["prof"])[0, 1])
        p1b, _ = unit_profile(*_mk(fall))
        c_self = float(np.corrcoef(p1["prof"], p1b["prof"])[0, 1])
        chk("同向自相关 ≈ 1", c_self > 0.999, "%.4f" % c_self)
        chk("反向相关 ≈ −1", c_same < -0.95, "%.3f" % c_same)
        chk("tail25 fall < 0", p1["tail25"] < 0, "%.2f" % p1["tail25"])
        chk("tail25 rise > 0", p2["tail25"] > 0, "%.2f" % p2["tail25"])
        chk("arc_st 符号正确", p1["arc_st"] < 0 < p2["arc_st"])

    print("== 2. 有洞仍可插值 ==")
    f0, t = _mk(fall)
    f0[40:70] = 0.0
    p3, e3 = unit_profile(f0, t)
    chk("丢 30 帧后仍能提取", p3 is not None, str(e3 or ""))
    if p3:
        chk("轮廓全为有限值", bool(np.all(np.isfinite(p3["prof"]))))
        chk("检测到停顿 n_breaks>=1", p3["n_breaks"] >= 1, "%d" % p3["n_breaks"])

    print("== 3. 拒绝条件 ==")
    f0z = np.zeros(120)
    pz, rz = unit_profile(f0z, np.arange(120) * 0.01)
    chk("全静音 → None + FEW-FRAMES", pz is None and "FEW-FRAMES" in rz, rz or "")
    fx, tx = _mk(fall)
    fx = fx * 2.0                      # 抬一个八度 → 中位 200Hz
    po, ro = unit_profile(fx, tx)
    chk("中位 >140Hz → NAN-OCTAVE", po is None and "OCTAVE" in ro, ro or "")

    print("== 4. 能量轮廓 ==")
    chk("纯静音 → None", energy_profile(np.zeros(48000), 48000) is None)
    tt = np.arange(48000) / 48000.0
    sine = (0.3 * np.sin(2 * np.pi * 120 * tt)).astype(np.float32)
    ep = energy_profile(sine, 48000)
    chk("恒定正弦 → e_std 很小", ep is not None and ep["e_std"] < 0.5,
        "%.3f" % (ep["e_std"] if ep else -1))
    fade = (0.3 * np.sin(2 * np.pi * 120 * tt) * np.linspace(1, 0.05, 48000)).astype(np.float32)
    ef = energy_profile(fade, 48000)
    chk("渐弱 → e_tail < e_head", ef is not None and ef["e_tail"] < ef["e_head"] - 6,
        "%.1f/%.1f" % (ef["e_tail"], ef["e_head"]) if ef else "")

    print("== 5. 标点分类 ==")
    for s, want in [("He went home.", "period"), ("What is it?", "question"),
                    ("Oh no!", "exclam"), ("he said,", "comma"),
                    ("his father said", "none"), ("'Come here.'", "period"),
                    ("well, ", "comma")]:
        got = punct_class(s)
        chk("punct_class(%r)=%s" % (s, want), got == want, "got " + got)

    print("== 6. consensus 退化 ==")
    a = np.linspace(0, 1, 21)
    cm2 = corr_matrix([a, a * 1.0 + 0.01])
    c2 = consensus(cm2)
    chk("n=2 不判离群", c2["outlier"] is None and c2["stable"] is True)
    cm3 = corr_matrix([a, a + 0.02, -a])
    c3 = consensus(cm3)
    chk("n=3 指出反向那个", c3["outlier"] == 2, str(c3["outlier"]))
    chk("n=3 gap 最小在离群项", int(np.nanargmin(c3["loo"])) == 2)

    print("== 7. L1 / L3 ==")
    f0, t = _mk(np.zeros(120))
    pj, _ = unit_profile(f0, t)
    lj = l1_checks(f0, t, pj)
    chk("平稳信号 jump_p90 很小", lj["jump_p90"] < 0.2, "%.3f" % lj["jump_p90"])
    bad = np.zeros(120)
    f0b, tb = _mk(bad)
    f0b[50] *= 1.9      # 插入一个突跳
    f0b[51] *= 0.5
    pb, _ = unit_profile(f0b, tb)
    lb = l1_checks(f0b, tb, pb)
    chk("插突跳后 jump_max > 6 st", lb["jump_max"] > 6.0, "%.1f" % lb["jump_max"])
    chk("插突跳后 jump_cnt6 >= 1", lb["jump_cnt6"] >= 1, "%d" % lb["jump_cnt6"])
    l3 = l3_check("period", dict(tail25=+9.0, end_st=+2.0), 3.0)
    chk("陈述句末段上扬 → violated", l3["violated"] is True and l3["l3_pen"] > 0)
    l3b = l3_check("question", dict(tail25=-9.0, end_st=-1.0), 3.0)
    chk("问句强下沉 → 弱告警", l3b["violated"] is True and l3b["l3_pen"] == 0.0)

    print("\n%s" % ("全部通过" if ok else "有失败项"))
    return 0 if ok else 1


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--plan", default="mt_plan3b.json")
    ap.add_argument("--dirs", default="_mt_raw_s42,_mt_raw_s1234,_mt_raw_srate")
    ap.add_argument("--chs", default="ch1")
    ap.add_argument("--out", default=os.path.join(ROOT, "_mt_contour"))
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default=None, help="只跑指定单元 id（逗号分隔）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    dirs = [d.strip() for d in a.dirs.split(",") if d.strip()]
    chs = [c.strip() for c in a.chs.split(",") if c.strip()]
    ids = {x.strip() for x in a.ids.split(",") if x.strip()} if a.ids else None
    batch(os.path.join(ROOT, a.plan), dirs, chs, a.out, jobs=a.jobs, limit=a.limit, ids=ids)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
