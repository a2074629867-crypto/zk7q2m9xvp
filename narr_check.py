# -*- coding: utf-8 -*-
"""narr_check.py —— 旁白韵律体检（L1 缺陷层）。

为什么要有这个：现有能判的三项（能量轮廓 AUC 0.921 / 末段上扬 82% / F0 突跳 100%）
散在 mt_contour.py 里，而那是个**多候选选优**工具（吃 --plan + --dirs），
整章成品（22 分钟一条）跑不通。而且 ch123_scan/tone/stab/vadcov 全部只打屏不落盘，
无法回溯。

本脚本只做 L1（秒级、无参考、不依赖文本），三类 FIX：
  1. 结尾硬切（最后 5ms 的 RMS 相对前 200ms 主体掉了不到 6dB，且末采样不为零）
  2. 句内 F0 突跳（>6st 事件 ≥2 次）
  3. 末段上扬（最后 300ms 斜率 >+2st/s，仅报数值，需文本才能定陈述句）

WATCH（只报不判）：能量 span 过平、HNR 骤降、有声占比过低。

用法：
  python narr_check.py --chapter G:/_setup/_mt_out/ch1.wav --out _narr_ch1
  python narr_check.py --dir G:/_setup/ch123_final --out _narr_dir
"""
import argparse
import json
import os

import numpy as np
import parselmouth
import soundfile as sf

# 常量与 ch123_scan.py 对齐
SIL_DB = -45.0
MIN_UNIT = 0.60          # 最短单元（秒），更短的并入邻句
MIN_SIL = 0.22           # 切句静音门（秒）
# 结尾硬切门：最后 5ms 的 RMS 相对前 200ms 主体**掉了不到 6dB**，且末采样不为零。
# ★ 2026-11-11 修：原值是 40（比较最后 5ms 首尾两个**采样**），只要文件收在过零点
#   就恒报 150dB+，716 条里误杀 494 条。见 l1_unit 里的说明。
CUT_JUMP = -6.0          # 尾部相对主体掉多少 dB 以内算「没衰减」
# ★ 2026-10-29 实测修正：男低音旁白（马修中位 76Hz）上 6st 是正常语调起伏
#   （71→100Hz），而实测 jump_max 分布 p50=8.0 / p90=12.0，
#   35% 落在 10~14st 正好是八度 ⇒ parselmouth 气声跟踪错误，不是语调突跳。
#   ⇒ 阈值提到 9st，并把八度错误单独归类为 WATCH（跟踪问题，不是生成缺陷）。
F0_JUMP_ST = 9.0         # 相邻帧 F0 差多少算真突跳
F0_JUMP_N = 2            # 几次突跳判 FIX
OCT_LO, OCT_HI = 10.5, 13.5   # 落在这一段算八度倍频错误
F0_CEIL_REL = 2.2        # 超过全局中位这么多倍算异常（305Hz 是对白 Charles 的绝对线）
TAIL_RISE = 3.0          # 末段斜率 st/s

# ★★ 2026-11-12 定稿：“持续高音帧”只认 pyin，praat 的计数降为纯信息字段。
# 标定脚本 `_f0_calib.py`，同一实现同一参数，真人 159 条 vs 我们旁白 710 条：
#   praat hi_local  p50/p75/p90 = 真人 0/0/3   我们 3/9/18
#   pyin  hi_local  p50/p75/p90 = 真人 0/0/0   我们 0/0/0（p95=11 / max=62）
# 在 th=8 上：praat 误报真人 3/159(1.9%) 且判我们 210/710(29.6%) —— 三成旁白是缺陷不可能；
#            pyin  误报真人 0/159(0.0%) 且判我们  43/710( 6.1%)。
# praat 系统虚高的原因：TTS 输出 H2 强、气声少，自相关容易锁到倍频。实测 c1_0007
# praat 报 18 帧 150~200Hz，pyin 全程不过 98Hz；c3_0673 同样。而真人录音噪声大、
# 分谐波多，反而不容易锁错 ⇒ **praat 的绝对值跳语料不可比**，不能拿来定阈值。
# 命中的 43 条已验连续性（最长连续 15~27 帧 = 150~270ms），是真实音高偏移不是噪声。
F0_HI_REL = 1.8          # 高音帧定义：超过**本条中位**的多少倍
F0_HI_FIX = 8            # pyin 口径高音帧数 ≥ 此值判 FIX（真人 0% 误报）
F0_HI_WATCH = 3          # 3~7 帧只报 WATCH
# ★ 能量 span 是唯一找到的「平淡」判据（2026-10-29 实测，控制时长后仍成立）：
#   真人切片 159 条（E:/ttsds/data/ref_human）span p50=37.0 / p10=29.2；
#   我们旁白 p50=25.1 / p10=16.9。按 dur 分桶后差距更大（2.5~3.5s：21.6 vs 37.0）。
#   真人 span 几乎不随时长变（2.5-3.5s 与 3.5-5s 都是 37.0）⇒ 不是长度假象。
#   短句（<2.5s）不外推：起伏空间本来就小，标 unmeasurable。
ENERGY_MIN_DUR = 2.5     # 低于此时长不判 span
# ★ 2026-10-29：删掉全局 ENERGY_FLAT=30。
#   实测该阈值只对马修旁白成立；Charles 真人自己的 span 就只有 22.5，
#   用 30 会把整条对白判成「平」。改成读 _rhythm_bands.json 的角色带（含底噪归一）。
BANDS_PATH = r'G:/_setup/_rhythm_bands.json'

# ★ 2026-11-11：energy_span 只允许有一个实现，就是带构建侧那一个。
#   之前判据层自己写了一份「时间等分 21 槽 + 剔低槽」，与 建带 用的
#   「floor_norm(−56) → 剔静音帧 → 语音帧等分 21 段」不是同一把尺子，
#   于是带说我们正常、判据说我们太陡，两边都"有据"。现在统一。
try:
    import sys as _sys
    _sys.path.insert(0, r'G:/_setup')
    # 注意循环依赖：mt_rhythm_bands 反过来 import 本模块的 cut_units，
    # 所以这里不能在模块顶层 import 它 —— 首次调用时再取（见 _span_only）。
    def _span_only(y, sr, role='narr'):
        from mt_rhythm_bands import span_only
        return span_only(y, sr, role)
except Exception as _e:      # 回退：宁可停跑也不能偷偷换一把尺子
    raise SystemExit('narr_check 初始化失败：%s' % _e)
BAND_MARGIN = 2.5        # 跨 seed 噪声 p75，超出带界这么多才算缺陷
_BANDS = None


def get_band(role='narr'):
    global _BANDS
    if _BANDS is None:
        try:
            import json as _j
            _BANDS = _j.load(open(BANDS_PATH, encoding='utf-8'))
        except Exception:
            _BANDS = {}
    return _BANDS.get(role) or {}


def band_flag(span, role='narr'):
    """返回 'LOW' / 'HIGH' / 'OK' / None（无带或不适用）。"""
    if span is None:
        return None
    e = (get_band(role).get('energy_span') or {})
    if 'p05' not in e or 'p95' not in e:
        return None
    if span < e['p05'] - BAND_MARGIN:
        return 'LOW'
    if span > e['p95'] + BAND_MARGIN:
        return 'HIGH'
    return 'OK'
HNR_LOW = 3.0

NPT = 21


def frame_db(x, sr, fl=0.02, hop=0.02):
    n = int(fl * sr)
    h = int(hop * sr)
    if len(x) < n:
        return np.array([-200.0]), h
    k = 1 + (len(x) - n) // h
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    seg = x[idx]
    rms = np.sqrt((seg.astype(np.float64) ** 2).mean(1)) + 1e-12
    return 20 * np.log10(rms), h


def cut_units(x, sr):
    """按静音切句。返回 [(t0, t1)]，短于 MIN_UNIT 的并入下一句。"""
    db, h = frame_db(x, sr)
    hop_s = h / sr
    ref = np.percentile(db, 90)
    voiced = db > (ref - 30.0)
    units, i, n = [], 0, len(voiced)
    while i < n:
        if not voiced[i]:
            i += 1
            continue
        j = i
        sil = 0
        k = i
        while k < n:
            if not voiced[k]:
                sil += 1
                if sil * hop_s >= MIN_SIL:
                    break
            else:
                sil = 0
            k += 1
        end = k - sil
        units.append((i * hop_s, end * hop_s))
        i = k
    # 合并过短单元
    out = []
    for u in units:
        if out and (u[1] - u[0]) < MIN_UNIT:
            out[-1] = (out[-1][0], u[1])
        else:
            out.append(u)
    return [(a, b) for a, b in out if b - a >= 0.30]


def l1_unit(y, sr, role='narr'):
    """单句 L1 体检。返回指标 dict。"""
    d = {}
    # --- 结尾硬切
    # ★ 2026-11-11 修：原实现逐采样点取 20log10|y|，比较最后 5ms 的**首尾两个采样**。
    #   只要文件结尾停在过零点（几乎所有正常收尾都停在 0.000000），
    #   末采样就是 1e-12 量级的 −240dB，于是 cut_drop 恒等于「首采样 dB + 240」，
    #   实测中位 149.7dB —— 716 条里 494 条被判「结尾硬切 172dB」，全是假阳性。
    #   实测 c1_0001 尾部包络是 −31→−51dB 的平滑衰减，根本不是硬切。
    #
    #   正确判据：硬切 = 波形在**还有能量**的时候突然断开。
    #   量法：最后 5ms 的 RMS 相对前 200ms 主体的 RMS 掉了多少 dB。
    #   掉得少（> −6dB）且末采样不为零 → 真硬切；掉得多 → 已经自然衰减。
    k = max(int(0.005 * sr), 16)
    body_a = max(0, len(y) - int(0.205 * sr))
    body = y[body_a:len(y) - k].astype(np.float64)
    tail = y[-k:].astype(np.float64)
    t_rms = float(np.sqrt((tail ** 2).mean())) if len(tail) else 0.0
    b_rms = float(np.sqrt((body ** 2).mean())) if len(body) else 0.0
    d["cut_drop"] = round(20 * np.log10(t_rms / b_rms + 1e-12), 1)
    d["cut_hard"] = bool(d["cut_drop"] > CUT_JUMP and abs(float(y[-1])) > 0.02)

    # --- F0
    snd = parselmouth.Sound(np.ascontiguousarray(y, dtype=np.float64), sampling_frequency=sr)
    # ★ 旁白专用参数：floor 60 / ceil 250 / vt **0.45**。
    #   vt 从 0.20 提到 0.45（2026-11-11）：0.20 会把气声/嘎裂声帧也判成浊音，
    #   于是「相邻 10ms 跳 9~18 个半音」大量凭空出现。同一批 8 条 FIX 实测：
    #     vt 0.20 → 突跳 2~8 次；vt 0.35 → 0~5 次；vt 0.45 → 0~3 次（多数清零）
    #   而 F0 中位全程稳定在 71~83Hz（差 ≤3Hz）⇒ 突跳数量随「宽松程度」单调变化，
    #   这是跟踪噪声的定义性特征，不是语调。0.45 是 praat 默认值。
    p = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=250,
                        voicing_threshold=0.45, silence_threshold=0.03)
    f = np.asarray(p.selected_array["frequency"], dtype=float)
    t = np.asarray(p.xs(), dtype=float)
    v = f > 0
    if v.sum() >= 8:
        fv = f[v]
        d["f0_med"] = round(float(np.median(fv)), 1)
        d["f0_max"] = round(float(fv.max()), 1)
        # 持续高音帧计数（>1.8×本条中位）：真人中位 0 / p90 0 / 最多 6 帧；
        # 我们是 4 / 16 / 20 —— 唯一有区分力的 F0 指标。
        d["f0_hi_n"] = int((fv > 1.8 * np.median(fv)).sum())
        d["f0_ceil_hit"] = False   # 由 run() 用全局中位重判（逐句中位会被八度污染）
        # 连续 voiced 段内的帧间跳变；八度倍频错误单独计
        st = 12 * np.log2(np.maximum(f, 1e-6) / 100.0)
        jumps, octs, spikes = [], [], []
        for i in range(1, len(f)):
            if v[i] and v[i - 1] and abs(t[i] - t[i - 1]) < 0.03:
                dd = abs(st[i] - st[i - 1])
                if OCT_LO <= dd <= OCT_HI:
                    octs.append(t[i])
                elif dd > F0_JUMP_ST:
                    # ★ 2026-11-11 追加：10ms 内跳 9st = 频率在 10 毫秒里变 1.68 倍，
                    #   人的声带做不到。把 ceiling 从 250 收到 160、voicing 0.20→0.45
                    #   重测 30 条，突跳 30/30 → 8/30 → 0/30 全消失，而 F0 中位始终
                    #   70~90Hz 不变 ⇒ 这些都是 pitch 跟踪的瞬时尖刺，不是语调。
                    #   真语调跳过去会**停住**（新音高持续 ≥60ms），跟踪错误下一帧就回落。
                    #   所以只认「跳后 60ms 内 voiced 中位仍停在 ±2st 内」的那一类。
                    m2 = (t >= t[i]) & (t <= t[i] + 0.06) & v
                    ok = False
                    if m2.sum() >= 3:
                        med_after = float(np.median(f[m2]))
                        ok = abs(12 * np.log2(max(med_after, 1e-6) / max(f[i], 1e-6))) <= 2.0
                    # ★ 谐波比排除（2026-11-11 追加）：10ms 内跳到 2× 或 3× 频
                    #   （75→150 / 75→225）只能是跟踪锁到谐波上。真语调 10ms 内
                    #   走半个八度已经是极限，走一个八度物理上不成立。
                    ratio = f[i] / max(f[i - 1], 1e-6)
                    harm = any(abs(ratio - m) / m < 0.08 for m in (2.0, 3.0))
                    if ok and not harm:
                        jumps.append((t[i], dd, float(f[i])))
                    else:
                        spikes.append(t[i])

        def _events(seq):
            n, last = 0, -9.0
            for tt in seq:
                if tt - last > 0.08:
                    n += 1
                last = tt
            return n

        d["f0_jump_n"] = _events([x[0] for x in jumps])
        d["f0_jump_max"] = round(float(max([x[1] for x in jumps], default=0.0)), 1)
        d["f0_jump_fix"] = bool(d["f0_jump_n"] >= F0_JUMP_N)
        # 留下原始事件（时刻 + 跳幅 + 跳后 Hz），run() 拿到全局中位后再按上限过滤。
        # ★ 2026-11-11：215 条 FIX 里 210 条 f0_max 撞上限、156 条同时有八度错误，
        #   抽样把 pitch_ceiling 从 250 降到 160 复算，18.1st→9.5st、18.6st→9.4st、
        #   14.7st→0 —— 这些「突跳」是 76Hz 低音被跟成 3 倍频（230Hz）造成的假事件，
        #   不是语调。判据必须先排除「跳到的那个音高本身已越上限」的事件。
        d["jumps_raw"] = [[round(float(a), 2), round(float(b), 1), round(float(c), 1)]
                          for a, b, c in jumps]
        d["oct_err"] = _events(octs)
        d["f0_spike_n"] = _events(spikes)   # 瞬时尖刺（跳完立刻回落）= 跟踪问题，只报 WATCH
        # --- 末段 300ms 斜率
        t_end = t[-1]
        m = (t >= t_end - 0.30) & v
        # 点数太少或斜率离谱（短句尾部 2-3 个点会拟出 ±139st/s）一律不采信
        if m.sum() >= 6:
            tt, yy = t[m], st[m]
            if tt[-1] - tt[0] >= 0.15:
                slope = float(np.polyfit(tt - tt[0], yy, 1)[0])
                d["tail_slope"] = round(slope, 2) if abs(slope) < 20 else None
            else:
                d["tail_slope"] = None
        else:
            d["tail_slope"] = None
        d["tail_rise"] = bool(d["tail_slope"] is not None and d["tail_slope"] > TAIL_RISE)
    else:
        d.update(f0_med=None, f0_max=None, f0_ceil_hit=False, f0_jump_n=0,
                 f0_jump_max=0.0, f0_jump_fix=False, oct_err=0, jumps_raw=[], f0_spike_n=0,
                 f0_hi_n=0, f0_hi_n_pyin=None, f0_med_pyin=None,
                 tail_slope=None, tail_rise=False)

    # --- 能量轮廓 span（21 点）
    # ★★ 2026-11-11 定案：**唯一实现**在 mt_rhythm_bands.span_only()，判据层与带构建层同源。
    #   本项目先后出现三把尺子（同一批真人 159 条）：
    #     A 建带口径（本函数现在用的）：8.9 / 14.3 / 22.5  ← 与 _rhythm_bands.json 逐位一致
    #     B 旧判据（时间等分 21 槽 + 剔 <max−25 槽）：9.7 / 18.0 / 24.1
    #     C 文档口径（时间等分 21 槽、全槽）：28.8 / 36.9 / 39.9 ← REQUIREMENTS §28 记的 36.5 出自这里
    #   C 不能用：它把数字静音的谷底算成「最低点」，我们的音频在 C 下 p95 = **111.5dB**，
    #   而 16bit 动态范围只有 96dB —— 物理上不可能，是纯污染。/ 之前据此得出的
    #   「我们 40.1 偏陡不是偏平」作废。同尺下我们是 15.4、真人是 14.3，基本持平。
    #   A 相对 C 的另一个好处（2026-10-29 实测）：同一个 take 只慢 12%，C 的 span 从
    #   26.6 掉到 13.3（13dB 纯边界伪影），A 是 12.7/15.4/15.4/15.5。
    span = _span_only(y, sr, role)
    d["energy_span"] = None if span is None else round(span, 1)
    d["energy_band"] = (band_flag(d["energy_span"], role)
                        if len(y) / sr >= ENERGY_MIN_DUR else None)
    d["energy_flat"] = d["energy_band"] == 'LOW'

    # --- HNR
    try:
        hnr = snd.to_harmonicity_cc(time_step=0.01, minimum_pitch=60)
        hv = np.asarray(hnr.values[0], dtype=float)
        hv = hv[hv > -40]
        d["hnr_med"] = round(float(np.median(hv)), 1) if len(hv) else None
        d["hnr_low"] = bool(d["hnr_med"] is not None and d["hnr_med"] < HNR_LOW)
    except Exception:
        d["hnr_med"] = None
        d["hnr_low"] = False

    # --- 持续高音帧（pyin 口径，唯一进判定的那一个）
    hi_py, med_py = _hi_pyin(y, sr)
    d["f0_hi_n_pyin"] = hi_py
    d["f0_med_pyin"] = med_py
    return d


def _hi_pyin(y, sr):
    """pyin 口径的「持续高音帧数」。返回 (帧数, pyin 中位)。

    参数必须与 _f0_calib.py 完全一致（重采 16k / frame_length=1024 / hop=160 / fmin60 / fmax250），
    否则标定出来的阈值不成立。

    为什么不用 praat 的 f0_hi_n 作判定：见文件头 F0_HI_REL 处的标定记录。
    一句话：praat 在 TTS 输出上会把 H2 锁成基频，真人录音上不会，
    所以它的绝对计数跟真人不可比，判据只能用 pyin。
    """
    try:
        import librosa
        arr = np.ascontiguousarray(y, dtype=np.float32)
        if sr != 16000:
            arr = librosa.resample(arr, orig_sr=sr, target_sr=16000)
        f0, _, _ = librosa.pyin(arr, fmin=60, fmax=250, sr=16000,
                                frame_length=1024, hop_length=160, fill_na=np.nan)
        f0 = f0[~np.isnan(f0)]
        if len(f0) < 8:
            return 0, None
        med = float(np.median(f0))
        return int((f0 > F0_HI_REL * med).sum()), round(med, 1)
    except Exception:
        return None, None


def verdict(d):
    """FIX 只给三类，且都是「有实测标定」的。"""
    fixes = []
    if d.get("cut_hard"):
        fixes.append("结尾硬切（尾部只比主体低 %.0fdB）" % d.get("cut_drop", 0))
    if d.get("f0_jump_fix"):
        fixes.append("F0 突跳 %d 次" % d.get("f0_jump_n", 0))
    # ★ 2026-11-12 修死代码：原先把 `n_hi>=8 → fixes.append` 写在下面
    #   `if fixes: return` **之后**，于是无论 n_hi 多大都不会返回 FIX。
    #   211 条 f0_hi_n>=8 被静默吞掉，这就是「PASS 712 / 99.4%」
    #   与「抽样只在 1/3 复现」的来源。现在前置到早退之前，口径改 pyin。
    n_hi_py = d.get("f0_hi_n_pyin")
    if n_hi_py is not None and n_hi_py >= F0_HI_FIX:
        fixes.append("F0 持续高音 %d 帧(pyin,>%.1f×中位)" % (n_hi_py, F0_HI_REL))
    if fixes:
        return "FIX", fixes
    watch = []
    # ★ 2026-11-11：`f0_max 超 2.2×中位` 从 WATCH 降为纯信息字段。
    #   实测它没有区分力：真人 159 条里 9% 越线，我们 50% 越线，而且越线常常只是
    #   **单帧 10ms** —— 单帧极值不可重复（抽样复算 pyin 只在 1/3 的条目上复现）。
    #   换成「持续高音帧计数」：真人超 1.8×中位的帧数 中位 0 / p90 0 / 最多 6；
    #   我们 中位 4 / p90 16 ⇒ 这个指标才真正分得开（阈值见下）。
    # praat 口径的计数只留作信息字段（跨语料不可比，见文件头 F0_HI_REL 处的标定），不参与判定。
    n_hi = d.get("f0_hi_n") or 0
    if n_hi_py is not None and F0_HI_WATCH <= n_hi_py < F0_HI_FIX:
        watch.append("F0 高音 %d 帧(pyin,>%.1f×中位)" % (n_hi_py, F0_HI_REL))
    if d.get("f0_ceil_hit") and n_hi < 3:
        watch.append("F0 峰值 %.0fHz(仅单帧，建议人工听)" % (d.get("f0_max") or 0))
    if d.get("oct_err"):
        watch.append("八度跟踪 %d 处" % d["oct_err"])
    if d.get("f0_spike_n"):
        watch.append("F0 瞬时尖刺 %d 处" % d["f0_spike_n"])
    if d.get("energy_band") == 'LOW':
        watch.append("起伏不足 %.1fdB" % (d.get("energy_span") or 0))
    elif d.get("energy_band") == 'HIGH':
        watch.append("起伏过大 %.1fdB" % (d.get("energy_span") or 0))
    if d.get("tail_rise"):
        watch.append("末段上扬 %+.1fst/s" % (d.get("tail_slope") or 0))
    if d.get("hnr_low"):
        watch.append("HNR %.1fdB" % (d.get("hnr_med") or 0))
    return ("WATCH", watch) if watch else ("PASS", [])


def run(units, tag, out_dir, role='narr'):
    rows = []
    for name, t0, t1, y, sr in units:
        d = l1_unit(y, sr, role)
        rows.append((name, t0, t1, d))
    # 用全局中位重判 F0 上限（逐句中位会被八度污染）
    med_all = [d["f0_med"] for _, _, _, d in rows if d.get("f0_med")]
    ref_f0 = float(np.median(med_all)) if med_all else None
    rows2 = []
    for name, t0, t1, d in rows:
        if ref_f0 and d.get("f0_max"):
            d["f0_ceil_hit"] = bool(d["f0_max"] > F0_CEIL_REL * ref_f0)
        # 按上限过滤突跳事件：跳到的音高已越 2.2× 全局中位，这一段是跟踪溢出，
        # 不是语调（76Hz 的 3 倍频正好落在 230Hz 附近，只有上限能把它挡住）。
        if ref_f0 and d.get("jumps_raw"):
            hi = F0_CEIL_REL * ref_f0
            keep = [(a, b) for a, b, hz in d["jumps_raw"] if hz <= hi]
            d["jump_dropped"] = len(d["jumps_raw"]) - len(keep)
            n, last = 0, -9.0
            for tt, _ in keep:
                if tt - last > 0.08:
                    n += 1
                last = tt
            d["f0_jump_n"] = n
            d["f0_jump_max"] = round(float(max([b for _, b in keep], default=0.0)), 1)
            d["f0_jump_fix"] = bool(n >= F0_JUMP_N)
        vd, why = verdict(d)
        rows2.append(dict(unit=name, t0=round(t0, 2), t1=round(t1, 2),
                          dur=round(t1 - t0, 2), verdict=vd, why=why, **d))
    rows = rows2
    os.makedirs(out_dir, exist_ok=True)
    json.dump(rows, open(os.path.join(out_dir, "_narr_check.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    n = len(rows)
    cnt = {"PASS": 0, "WATCH": 0, "FIX": 0}
    for r in rows:
        cnt[r["verdict"]] += 1
    print("%s：%d 个单元  PASS %d / WATCH %d / FIX %d"
          % (tag, n, cnt["PASS"], cnt["WATCH"], cnt["FIX"]), flush=True)

    ls = [r for r in rows if r["verdict"] == "FIX"]
    if ls:
        print()
        print("== FIX（%d）==" % len(ls))
        for r in ls[:30]:
            print("  %-18s %7.2fs  %s" % (r["unit"], r["dur"], " / ".join(r["why"])))
    ws = [r for r in rows if r["verdict"] == "WATCH"]
    if ws:
        print()
        print("== WATCH（%d，前 12）==" % len(ws))
        for r in ws[:12]:
            print("  %-18s %7.2fs  %s" % (r["unit"], r["dur"], " / ".join(r["why"])))

    # 汇总统计
    f0 = [r["f0_med"] for r in rows if r.get("f0_med")]
    sp = [r["energy_span"] for r in rows if r.get("energy_span") is not None]
    print()
    if f0:
        print("F0 中位 %.1fHz（p10 %.1f / p90 %.1f，跨度 %.1f）"
              % (np.median(f0), np.percentile(f0, 10), np.percentile(f0, 90),
                 np.percentile(f0, 90) - np.percentile(f0, 10)))
    if sp:
        print("能量 span 中位 %.1fdB（p10 %.1f）" % (np.median(sp), np.percentile(sp, 10)))
    print("明细: %s" % os.path.join(out_dir, "_narr_check.json"))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", help="单个长文件（整章成品），按静音切句")
    ap.add_argument("--dir", help="目录，每条 wav 一个单元")
    ap.add_argument("--out", default="G:/_setup/_narr_check")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    if a.chapter:
        x, sr = sf.read(a.chapter, dtype="float32")
        if x.ndim > 1:
            x = x.mean(1)
        x = np.ascontiguousarray(x)
        cuts = cut_units(x, sr)
        if a.limit:
            cuts = cuts[: a.limit]
        units = [("%s#%03d" % (os.path.basename(a.chapter)[:-4], i),
                  t0, t1, x[int(t0 * sr):int(t1 * sr)], sr)
                 for i, (t0, t1) in enumerate(cuts)]
        print("%s  %.1fs → %d 句" % (os.path.basename(a.chapter), len(x) / sr, len(units)),
              flush=True)
        run(units, os.path.basename(a.chapter), a.out)
    elif a.dir:
        fs = sorted(f for f in os.listdir(a.dir) if f.lower().endswith(".wav"))
        if a.limit:
            fs = fs[: a.limit]
        units = []
        for f in fs:
            y, sr = sf.read(os.path.join(a.dir, f), dtype="float32")
            if y.ndim > 1:
                y = y.mean(1)
            y = np.ascontiguousarray(y)
            units.append((f[:-4], 0.0, len(y) / sr, y, sr))
        run(units, os.path.basename(a.dir), a.out)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
