# -*- coding: utf-8 -*-
"""mt_seg_drift.py —— 句内音色漂移检测（同一句里音色突变 / 音色消失）。

★★ 为什么必须有这一层（整句口径的盲区）
  mt_voice_gate.measure() 对整条文件只出**一个标量**（F0 / 谱质心 / 谱倾斜的中位）。
  一句里前半是 Charles、后半掉成模型默认音色或气声，**整条中位可能完全正常**，
  整句闸门照样给 PASS。而 edit + 情绪标签恰恰最容易在标签边界断音色 —— 标签是
  局部编辑，模型只改标签覆盖的那一段，边界两侧的声学参数会阶跃。

★★ 判据看「段间跳变」，不看「偏离整句中位」
  正常语调本身就让 F0 变化（declination：陈述句尾可降 3~5 半音），
  但**声道形状（谱质心/谱倾斜）和周期成分（HNR）是稳定的**。
  音色切换是**阶跃**：F0 突变 + 谱质心同时跳，常伴 HNR 塌 / 能量塌。
  所以用相邻窗差分，并要求**多参数同时超阈**才算突变，单参数只记 WARN。

★★ 四类信号
  1 音色阶跃   ΔF0 ≥ ST_HARD 半音 且 谱质心比 ≥ CEN_HARD（或 ≤ 1/CEN_HARD）
  2 气声化     ΔHNR ≤ -HNR_DROP dB（周期成分突然消失 = "音色消失"最常见形态）
  3 基频丢失   浊音帧占比从 ≥0.60 掉到 ≤0.20
  4 能量塌     ΔRMS ≤ -RMS_DROP dB（或突升 ≥ RMS_DROP，爆音/换人）

用法：
  python mt_seg_drift.py --one x.wav
  python mt_seg_drift.py --dir _mt_raw_s42 --out _seg_drift_ch1.json
  python mt_seg_drift.py --list a.wav,b.wav --json out.json
"""
import argparse
import glob
import json
import os
import sys
import wave

import numpy as np
import parselmouth
from parselmouth.praat import call

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

F0_LO, F0_HI = 100.0, 400.0

# 窗参数：0.50s 窗 / 0.25s 步（50% 重叠）。
# 0.50s 在 240Hz 童声上是 120 个基频周期，足够稳；再短（<0.30s）F0 与谱质心都会抖。
WIN, HOP = 0.50, 0.25
MIN_DUR = 1.20          # 短于 1.2s 无法分段，直接判 INSUFFICIENT

# 阈值 —— 由 `_calib_seg.py` 在 180 条已交付旁白（已知干净）上的零分布定，
# 不是拍脑袋。正常句内段间跳变（1893 对）实测：
#   |ΔF0|      p50 0.57  p90 2.51  p95 3.32  p99 5.46  max 9.74  半音
#   |ln cen|   p50 0.25  p90 0.74  p95 0.89  p99 1.20  max 1.98
#   |Δslp|     p50 1.37  p90 3.78  p95 4.78  p99 6.65  max 10.08 dB/kHz
#   HNR 降      p50 -0.21 p90 5.74  p95 8.56  p99 14.62 max 111.9 dB
#   |ΔRMS|     p50 1.26  p90 4.11  p95 5.28  p99 8.38  max 15.05 dB
# ★ 第一版阈值（ST 3.0 / CEN 1.25 / HNR 8 / RMS 10）全部落在正常噪声里，
#   180 条里 101 条被误判 FAIL。**谱质心对元音极敏感**（/i/ 与 /u/ 差 2 倍），
#   所以它不能单独当音色判据，只能做联合条件。
# ★ 多重比较：一句中位 21 窗 = 20 个相邻对，每对 5% 误报 → 句子级 64% 误报。
#   因此单参数只记 WARN，判 FAIL 必须多参数同时超阈，或用极端单事件。
ST_HARD, ST_SOFT = 5.5, 3.4          # 半音（p99 / p95）
CEN_HARD, CEN_SOFT = 1.20, 0.89      # |ln 谱质心比|（p99 / p95）
SLP_HARD, SLP_SOFT = 6.7, 4.8        # dB/kHz（p99 / p95）
HNR_DROP, HNR_DROP_SOFT = 15.0, 9.0  # dB（p99 / p95）
HNR_EXTREME = 25.0                   # 单次即判（周期成分基本消失）
RMS_DROP, RMS_DROP_SOFT = 9.0, 5.5   # dB（p99 / p95）
RMS_EXTREME = 15.0                   # 单次即判
VOICED_DROP = 0.40                   # 浊音占比塌
VOICED_OK, VOICED_BAD = 0.60, 0.20
VOICED_USABLE = 0.30                 # 低于此值的窗谱参数不可信（噪声谱）

# ★ 对白版阈值（profile="dlg"）—— 2026-11-14 实测加
#   旁白是朗读，语调平；对白是表演，句内语调起伏 5~15 半音是常态。
#   实测对白 239 条（干净子集 162 条 / 2014 窗对）：
#     |ΔF0|     p95 8.9  p99 14.4 半音   ← 旁白 p95 3.32，差 2.7 倍
#     |ln cen|  p95 0.51 p99 0.80        ← 旁白 p95 0.89，对白反而更稳
#     |Δslp|    p95 3.84 p99 5.43        ← 旁白 p95 4.78，更稳
#     HNR 降    p95 9.31 p99 14.00       ← 与旁白 8.56/14.62 几乎相同
#   ⇒ 谱质心/谱倾斜/HNR 三个绝对量阈值对白**不用改**（甚至偏松），
#     唯一失效的是「ΔF0 当音色证据」：对白里 ΔF0 大 = 语调，不是换人。
#   所以对白版判据 = 只认「声道形状双维同时变」+ HNR 塌，彻底不看 F0。
CEN_DLG, SLP_DLG = 0.60, 4.0         # |ln 谱质心| 且 |Δ谱倾斜| 同时超（实测对白 p99 附近）
HNR_SOFT_DLG = 14.0                  # 对白 HNR 降 p99（旁白 p95=8.56 太低，气声是表演常态）
# ★ 声道形状判据只在**元音窗**上成立（2026-11-15 04:3x 修，v33 抓到 8 条假 FAIL）
#   症状：同一段音频，只往中间插了停顿（其它一个采样没动），句内漂移从 PASS 掉 MANUAL/FAIL。
#   定位：擦音/塞擦音窗（/s/ /ʃ/ /tʃ/）voiced 0.4~0.6、HNR 测不出、谱质心 2500~3100Hz、
#         谱倾斜≈0（噪声谱本来就平）。元音→擦音必然「谱质心×2 + 谱倾斜+4dB」，
#         这判的是**音段类型**，不是**同一个人声道的形状**。
#   为什么以前没炸：窗口栅格 0.25s；插停顿会平移后半段，让原本只命中 1 窗的事件
#         变成连续命中 2 窗，从「孤立 WARN」升级成「连续 FAIL」——纯栅格巧合。
#   ⇒ 判声道形状时两端都必须是 voiced>=0.65 且 HNR 可测的元音窗。
VOICED_SHAPE = 0.65
HNR_EXTREME_DLG = 20.0               # 对白：HNR 塌到这个量级不用看音段类型，无条件判
JUDGE_VER = 5                        # 判据版本；缓存条目带 ver，不一致即失效重算
#   对白版**不生成能量 soft**：实测重音/换气让 |ΔRMS| 5.5~9dB 反复出现，
#   是表演的基本手段（需求 19-0 明确要求有重音起伏），不是音色问题。


def read_wav(p):
    w = wave.open(p, "rb")
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    w.close()
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def _robust_f0(f0):
    """剔八度错帧（与 mt_voice_gate 同一套规则，保证口径一致）。"""
    if len(f0) < 10:
        return None, 1.0
    n0 = len(f0)
    m = float(np.median(f0))
    for _ in range(3):
        r = f0 / m
        keep = ~(((r > 0.42) & (r < 0.58)) | ((r > 1.72) & (r < 2.28)))
        if keep.sum() < 0.45 * len(f0):
            break
        f2 = f0[keep]
        m2 = float(np.median(f2))
        if abs(m2 - m) < 0.5:
            return m2, 1.0 - len(f2) / n0
        f0, m = f2, m2
    return m, 1.0 - len(f0) / n0


def series(a, sr):
    """整条算一次 pitch / harmonicity / 逐帧谱参数，返回按时间的数组。

    ★★★ F0 范围必须自适应，不能写死
      旁白（成人男低音）实测基频 **73 Hz**：100-400 范围只测到 1/569 帧。
      对白（9~10 岁童声）173~395 Hz：60-500 会成片锁 2 倍频（240→480）。
      两者不可能共用一个范围。做法：先用 60-500 粗测中位，再按中位选范围重测。
      粗测中位 < 150 → 成人男 (60, 300)；否则按童声 (90, 450)。
    """
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)

    def _pitch(lo, hi):
        p = call(snd, "To Pitch", 0.01, lo, hi)
        return np.array(p.xs(), dtype=float), np.array(p.selected_array["frequency"], dtype=float)

    t_p, f_p = _pitch(60.0, 500.0)
    v = f_p[f_p > 0]
    coarse = float(np.median(v)) if len(v) else 0.0
    if coarse and coarse < 150.0:
        lo, hi = 60.0, 300.0
    else:
        lo, hi = 90.0, 450.0
    if (lo, hi) != (60.0, 500.0):
        t_p, f_p = _pitch(lo, hi)

    harm = call(snd, "To Harmonicity (cc)", 0.01, 75.0, 0.1, 1.0)
    t_h = np.array(harm.xs(), dtype=float)
    h_h = np.array(harm.values[0], dtype=float)

    nfft, hop = 1024, 256
    win = np.hanning(nfft)
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    band = freqs < 4000.0
    t_f, cen, slp, rms = [], [], [], []
    for i in range(0, max(1, len(a) - nfft), hop):
        seg = a[i:i + nfft]
        if len(seg) < nfft:
            break
        r = float(np.sqrt((seg ** 2).mean()))
        t_f.append((i + nfft / 2.0) / sr)
        rms.append(20 * np.log10(r + 1e-12))
        S = np.abs(np.fft.rfft(seg * win))
        if S.sum() <= 0:
            cen.append(np.nan)
            slp.append(np.nan)
            continue
        cen.append(float((freqs * S).sum() / S.sum()))
        L = 20 * np.log10(S + 1e-10)
        slp.append(float(np.polyfit(freqs[band] / 1000.0, L[band], 1)[0]))
    return dict(t_p=t_p, f_p=f_p, t_h=t_h, h_h=h_h,
                t_f=np.array(t_f), cen=np.array(cen), slp=np.array(slp),
                rms=np.array(rms), f0_lo=lo, f0_hi=hi)


def windows(a, sr, S=None):
    """按 WIN/HOP 切窗，每窗取中位。返回 list of dict。"""
    S = S or series(a, sr)
    dur = len(a) / sr
    if dur < MIN_DUR:
        return []
    n = int((dur - WIN) / HOP) + 1
    out = []
    for k in range(n):
        t0 = k * HOP
        t1 = t0 + WIN
        mp = (S["t_p"] >= t0) & (S["t_p"] < t1)
        f0 = S["f_p"][mp]
        f0 = f0[f0 > 0]
        med, oct_skip = _robust_f0(f0) if len(f0) >= 8 else (None, 1.0)
        voiced = float(len(f0) / max(1, mp.sum()))     # 浊音帧占该窗全部帧

        mh = (S["t_h"] >= t0) & (S["t_h"] < t1)
        hnr = float(np.median(S["h_h"][mh])) if mh.sum() else None
        # ★ Praat 的 Harmonicity 在完全无周期时返回哨兵值（实测 N0184 静音段是 −200，
        #   239 条对白里又见到 **−99.9**）。不过滤会造出「HNR −111.5dB」这种假事件。
        # ★★ 2026-11-12 修：原下限 −100 太宽，−99.9 恰好逃过过滤 ⇒ 239 条对白判出 21 条 FAIL，
        #   其中 15 条是 HNR −105~−116dB 的哨兵值，不是气声化。语音 HNR 物理下限约 −20dB，
        #   低于它已经完全没有周期成分，本身就该按「基频丢失」规则处理，不能做差分。
        if hnr is not None and not (-20.0 < hnr < 60.0):
            hnr = None

        mf = (S["t_f"] >= t0) & (S["t_f"] < t1)
        c = S["cen"][mf]
        c = c[np.isfinite(c)]
        s = S["slp"][mf]
        s = s[np.isfinite(s)]
        rr = S["rms"][mf]
        tt = S["t_f"][mf]
        # ★ 能量只取「浊音帧」：正常朗读词间停顿 0.2~0.5s，窗跨过去 RMS 会掉 20dB+，
        #   全帧口径会把正常停顿误报成「能量塌」（实测 N0001 掉 23.7dB）。
        #   气声化导致的能量下降交给 HNR / 浊音占比判据，职责分开。
        if rr.size and S["t_p"].size:
            idx = np.clip(np.searchsorted(S["t_p"], tt), 0, S["t_p"].size - 1)
            vmask = S["f_p"][idx] > 0
            rr2 = rr[vmask]
            rms_db = float(np.median(rr2)) if rr2.size else None
        else:
            rms_db = None

        out.append(dict(t0=round(t0, 3), t1=round(t1, 3),
                        f0=med, voiced=round(voiced, 3), oct=round(oct_skip, 3),
                        cen=float(np.median(c)) if c.size else None,
                        slp=float(np.median(s)) if s.size else None,
                        hnr=round(hnr, 2) if hnr is not None else None,
                        rms=round(rms_db, 2) if rms_db is not None else None))
    return out


def st(a, b):
    if not a or not b:
        return None
    return float(12.0 * np.log2(a / b))


def _overlap_frac(t0, t1, gaps):
    """[t0,t1] 被允许的停顿区间覆盖的比例（取最大）。"""
    span = max(1e-6, t1 - t0)
    best = 0.0
    for a, b in gaps:
        ov = min(t1, b) - max(t0, a)
        if ov > 0:
            best = max(best, ov / span)
    return best


def _near_gap_end(t, gaps, tol=0.35):
    """t 是否落在某个停顿结束后的 tol 秒内（起音段）。"""
    for _a, b in gaps:
        if -0.05 <= (t - b) <= tol:
            return True
    return False


def _gap_inside(t0, t1, gaps):
    """[t0,t1] 是否有过半落在允许的停顿区间里。"""
    span = max(1e-6, t1 - t0)
    for a, b in gaps:
        ov = min(t1, b) - max(t0, a)
        if ov > 0.5 * span:
            return True
    return False


def judge(ws, profile="narr", allow_gaps=None, silence_tolerant=False):
    """相邻**有效窗**差分。返回 (verdict, events, pairs)。

    profile="narr"（默认，旁白/朗读）：原判据，F0 阶跃是音色证据。
    profile="dlg"（表演对白）：**不看 ΔF0**，只认声道形状双维 + HNR 塌。
      原因见 CEN_DLG 处注释：对白 ΔF0 p95 8.9 半音，F0 大跳就是语调。

    只在 voiced >= VOICED_USABLE 且 F0 可测的窗之间比较 —— 静音/纯气声窗的
    谱质心是噪声谱（实测 3171 Hz），拿它比会造出一堆假跳变。
    气声/失声单独用「基频丢失」规则判：前一个有效窗浊音 >=0.60、
    中间窗掉到 <=0.20，才算事件。
    """
    if len(ws) < 2:
        return "INSUFFICIENT", [], []

    voiced_all = [w["voiced"] for w in ws]
    # ★ 近静音窗不算「有效窗」（2026-11-15 05:0x 修）：文件开头/句尾的 -47dB 窗
    #   底噪是周期性的，voiced 能到 0.82、F0 也能测出 157Hz，但它的谱和电平都不可比。
    #   实测 c2_0308 就靠这个窗被判「能量突变 +22.6dB」（其实是第一个字起播）。
    # ★ 跨停顿边界的窗不能参与差分（2026-11-15 06:1x）
    #   一个 0.5s 窗里半截是插入的静音，HNR/谱质心/能量都是混合值 ——
    #   实测注入停顿后 9 条旁白新增 FAIL 全部落在停顿边界 ±0.3s 内
    #   （c3_0904 @8.5 紧接 8.21 的停顿尾、c2_0208 @6.75 紧接 6.42）。
    #   这和「擦音窗不能做声道形状」是同一条原则：不同类音段的窗不做差。
    _lv = [w["rms"] for w in ws if w["rms"] is not None]
    _loud = max(_lv) if _lv else None
    usable = [i for i, w in enumerate(ws)
              if w["voiced"] >= VOICED_USABLE and w["f0"]
              and (_loud is None or w["rms"] is None or w["rms"] >= _loud - 25.0)]
    if allow_gaps:
        usable = [i for i in usable
                  if _overlap_frac(ws[i]["t0"], ws[i]["t0"] + WIN, allow_gaps) <= 0.30]
    if len(usable) < 2:
        # 整条都没有可测语音 —— 这是素材问题，不是音色问题，不能判 FAIL
        if max(voiced_all) < 0.15:
            return "NO_SPEECH", [], []
        return "INSUFFICIENT", [], []

    pairs, events = [], []
    for a_i, b_i in zip(usable, usable[1:]):
        if b_i - a_i > 2:          # 中间隔了两个以上无效窗，不构成相邻跳变
            continue
        A, B = ws[a_i], ws[b_i]
        d = dict(i=b_i, t=round(B["t0"], 3), gap=b_i - a_i)
        d["dst"] = st(B["f0"], A["f0"])
        d["dcen"] = round(B["cen"] / A["cen"], 3) if A["cen"] and B["cen"] else None
        d["dslp"] = round(B["slp"] - A["slp"], 2) if A["slp"] is not None and B["slp"] is not None else None
        d["dhnr"] = round(B["hnr"] - A["hnr"], 2) if A["hnr"] is not None and B["hnr"] is not None else None
        d["drms"] = round(B["rms"] - A["rms"], 2) if A["rms"] is not None and B["rms"] is not None else None
        d["dvoiced"] = round(B["voiced"] - A["voiced"], 3)
        pairs.append(d)

        hard, soft = [], []
        lncen = abs(np.log(d["dcen"])) if d["dcen"] else None
        hnr_drop = (-d["dhnr"]) if d["dhnr"] is not None else None
        rms_abs = abs(d["drms"]) if d["drms"] is not None else None

        # 1 音色阶跃
        if profile == "dlg":
            # 对白版：只认声道形状（谱质心 + 谱倾斜）同时变，F0 不参与。
            # 元音切换也会让谱质心动，但**不会同时让谱倾斜同向大动**，
            # 而且元音切换是瞬时的（下一个窗就回来），靠「连续 ≥2」过滤。
            slp_abs = abs(d["dslp"]) if d["dslp"] is not None else None
            A_vowel = A["voiced"] >= VOICED_SHAPE and A["hnr"] is not None
            B_vowel = B["voiced"] >= VOICED_SHAPE and B["hnr"] is not None
            if (A_vowel and B_vowel
                    and lncen is not None and slp_abs is not None
                    and lncen >= CEN_DLG and slp_abs >= SLP_DLG):
                hard.append("声道形状 谱质心×%.2f 谱倾斜%+.1fdB" % (d["dcen"], d["dslp"]))
        elif d["dst"] is not None and A["oct"] < 0.25 and B["oct"] < 0.25:
            # 旁白版：F0 跳 **且** 至少一个其他维度同时偏
            #   单看 ΔF0 会被正常语调吃掉（declination 3~5 半音很常见），
            #   所以要求「音高 + 发声状态」同时变。
            other = ((lncen is not None and lncen >= CEN_SOFT)
                     or (hnr_drop is not None and hnr_drop >= HNR_DROP_SOFT)
                     or (rms_abs is not None and rms_abs >= RMS_DROP_SOFT))
            if abs(d["dst"]) >= ST_HARD and other:
                hard.append("音色阶跃 ΔF0%+.1f半音 ×%.2f" % (d["dst"], d["dcen"] or 0))
            elif abs(d["dst"]) >= ST_HARD:
                soft.append("ΔF0%+.1f半音(孤立)" % d["dst"])
            elif abs(d["dst"]) >= ST_SOFT and other:
                soft.append("音高+发声同向偏 ΔF0%+.1f" % d["dst"])

        # 2 气声化：周期成分突然消失（"音色消失"最常见形态）
        # ★ 停顿后的起音段天然更气：1.1s 静音之后第一个音节是软起音，
        #   HNR 掉 15~18dB 是**生理常态**，不是「音色消失」（实测 c3_0904 @8.5 −17.5dB、
        #   c2_0208 @6.75 −16.8dB，都在停顿尾 0.3s 内）。只在有停顿计划时豁免。
        _post_gap = bool(allow_gaps) and _near_gap_end(B["t0"], allow_gaps)
        if hnr_drop is not None and not _post_gap:
            # ★ 对白版：HNR 只在「两端都是元音窗」时可比（2026-11-15 04:4x 修）。
            #   元音→擦音/词尾气声会让 HNR 一次掉 15dB（实测 c2_0264 -15.25dB），
            #   但那不是周期成分消失，是进入非周期音段。只有塌到 20dB 以上才不需要看音段类型。
            _vpair = A["voiced"] >= VOICED_SHAPE and B["voiced"] >= VOICED_SHAPE
            # ★ 气声化也要「同类音段」前提，两个 profile 一致（2026-11-15 06:2x）
            #   旁白侧原先是 profile!=dlg 就放行，结果 HNR 在 15dB 阈值上抖：
            #   c3_0559 −15.7 / c2_0410 −27.1 / c3_0527 −15.3 全是孤立窗，
            #   谱质心几乎不动（0.44 / 0.96 / 1.06）—— 那不是气声化，是窗边界抖动。
            #   真正的气声化（L052 实测）是 HNR −22.4dB **且** 谱质心 657→2156。
            #   ⇒ 两端元音窗才判；否则只有塌到 HNR_EXTREME 级别才无条件判。
            if hnr_drop >= HNR_DROP and (_vpair or hnr_drop >= HNR_EXTREME):
                hard.append("气声化 HNR-%0.1fdB" % hnr_drop)
            elif hnr_drop >= (HNR_DROP_SOFT if profile == "narr" else HNR_SOFT_DLG):
                soft.append("HNR-%0.1fdB" % hnr_drop)

        # 4 能量：极端单次判；中等需伴随 F0 或 HNR 异常
        #   对白版不生成中等能量事件 —— 重音/换气 5~9dB 是表演手段，不是音色。
        if rms_abs is not None:
            # ★ 对白版能量极端值也要在同一段连续语音内比（2026-11-15 04:5x 修）：
            #   句尾衰减窗 rms -33dB 与停顿后新句首 -18dB 相差正好 15dB，
            #   那是「停顿两端的电平差」，不是音色阶跃（c3_0645 实测 +15.01dB）。
            #   整条的电平一致性由七闸里的响度闸负责，这里不重复管。
            if rms_abs >= RMS_EXTREME and (profile != "dlg" or
                                            (A["voiced"] >= VOICED_SHAPE and B["voiced"] >= VOICED_SHAPE)):
                hard.append("能量突变 %+.1fdB" % d["drms"])
            elif profile == "narr" and rms_abs >= RMS_DROP and ((d["dst"] and abs(d["dst"]) >= ST_SOFT)
                                                               or (hnr_drop and hnr_drop >= HNR_DROP_SOFT)):
                hard.append("能量突变 %+.1fdB(伴发声变化)" % d["drms"])
            elif profile == "narr" and rms_abs >= RMS_DROP_SOFT:
                soft.append("能量%+.1fdB" % d["drms"])

        if hard:
            events.append(dict(level="FAIL", t=d["t"], why=hard,
                               m=dict(st=d["dst"], cen=d["dcen"],
                                      hnr=hnr_drop, rms=d["drms"])))
        elif soft:
            events.append(dict(level="WARN", t=d["t"], why=soft,
                               m=dict(st=d["dst"], cen=d["dcen"],
                                      hnr=hnr_drop, rms=d["drms"])))

    # 3 基频丢失：两个有效窗之间夹着失声窗
    #   ★ 正常朗读的词间停顿 0.3~0.6s 就会让中间 1~2 个窗完全失声（实测 180 条里
    #     有 4 条因此被误判）。所以只有失声持续 >=3 窗（>=0.75s）才算 FAIL。
    for a_i, b_i in zip(usable, usable[1:]):
        if b_i - a_i < 2:
            continue
        A, B = ws[a_i], ws[b_i]
        mid = ws[a_i + 1:b_i]
        if not mid:
            continue
        # ★ 左翼必须是**元音窗**（voiced>=VOICED_SHAPE），不是「有个 0.6 就算」
        #   2026-11-15 05:4x：跨静音边界的窗 voiced 天然是 0.5~0.62（半个窗是静音），
        #   旧门槛 0.60 正好落在这里 ⇒ 同一段音频只因窗口栅格错位就从 WARN 变 FAIL
        #   （c1_0001 0.50 vs 0.62、c2_0515 同理）。实测 726 条旁白的左翼分布是
        #   双峰的：0.30~0.46（跨静音）与 >=0.65（真元音），中间几乎为空。
        if A["voiced"] >= VOICED_SHAPE and max(m["voiced"] for m in mid) <= VOICED_BAD:
            # ★ 计划内的停顿不算「失声」（2026-11-15 05:3x）
            #   插停顿后句内会出现 1.135s/1.695s 的**设计停顿**，跨 4~6 窗纯静音，
            #   旧判据一律记「基频丢失 → FAIL」。实测旁白 40 条抽样里 2 条因此从
            #   WARN 变 FAIL（c1_0001 @5.75s、c2_0515 @6.75s），都是 bound 档 1.135s。
            #   ⇒ 由调用方给 allow_gaps=[(t0,t1),...]（来自注入报告），落在里面的静音豁免。
            #   注意：只豁免「基频丢失」这一条，音色/谱判据照旧（停顿不该改音色）。
            if allow_gaps and _gap_inside(mid[0]["t0"], mid[-1]["t0"] + HOP, allow_gaps):
                continue
            why = ("基频丢失 %.0f%%→%.0f%%（%d 窗失声）"
                   % (100 * A["voiced"], 100 * max(m["voiced"] for m in mid), len(mid)))
            # ★ silence_tolerant：旁白专用。旁白在这个文体里的**自然句内停顿**
            #   就是 0.6~1.7s（实测 726 条里 595 处 >=0.75s 的静音，377 个文件有），
            #   「>=3 窗失声」与「合成漏句」在窗级完全不可分 —— 全量 A/B 实测：
            #   注入停顿后 30 条 FAIL 里 14 条是这类自然停顿被栅格错位放大出来的。
            #   所以旁白侧这条只记 WARN（信息保留），判别真截断交给物理闸的
            #   尾部衰减/硬切 + 语速自检；对白侧照旧（对白停顿 <=0.68s，规则有效）。
            _lv = "WARN" if silence_tolerant else ("FAIL" if len(mid) >= 3 else "WARN")
            events.append(dict(level=_lv,
                               t=round(mid[0]["t0"], 3), why=[why]))

    # ★★★ 持续性判定：孤立事件只记 WARN
    #   一句中位 21 窗 = 20 个相邻对，任何一对误报就整句 FAIL（多重比较）。
    #   实测 180 条正常旁白：FAIL 的句子**全部只有 1 个孤立事件**（词尾气声/短停顿），
    #   没有一句出现连续 2 个。而真正的音色切换是**持续**的（切换后后面的窗都变）。
    #   所以：连续 >=2 个 FAIL 事件，或单个极端事件，才判 FAIL。
    fails = [e for e in events if e["level"] == "FAIL"]
    if not fails:
        if events:
            return "WARN", events, pairs
        return "PASS", events, pairs

    def _extreme(e):
        """单次即判 FAIL 的极端事件。

        ★ 气声化不能要求「持续」：实测 L052（edit+disgusted）t=1.25 处 HNR 从 24
          塌到 2.21（-22.4dB）、谱质心 657→2156 翻倍，0.5s 后又恢复。这就是
          「某个词掉成气声」，是用户说的音色消失，但它只占 1 个窗。
          所以 HNR 塌 >= HNR_DROP 单次即判，不做持续性要求。
        ★ 反过来 ΔF0 阶跃必须要求持续/伴随：正常 declination 就能到 5 半音。
        """
        m = e.get("m") or {}
        return ((m.get("hnr") or 0) >= HNR_DROP
                or (m.get("rms") is not None and abs(m["rms"]) >= RMS_EXTREME)
                or any("基频丢失" in w and "3 窗" in w for w in e["why"]))

    consecutive = any(abs(fails[i + 1]["t"] - fails[i]["t"]) <= HOP * 1.5
                      for i in range(len(fails) - 1))
    if consecutive or any(_extreme(e) for e in fails):
        return "FAIL", events, pairs
    # 孤立事件降级为 WARN
    for e in fails:
        e["level"] = "WARN"
        e["why"] = ["孤立:" + w for w in e["why"]]
    return "WARN", events, pairs


def span_metrics(ws):
    """句级指标：F0 跨度 + 双音区（拆句后各段音色不同 = 两个音区）。

    ★ 为什么需要句级：窗间差分抓的是「阶跃」（拼接点），抓不到「渐变」。
      实测 L088（拆句生成，四段 304/218/179/145Hz）合并成成品后，窗间差分
      一个事件都不报 —— 因为段与段之间有停顿，相邻窗跨不过去，而且每段内部稳定。
      但它的**句内 F0 跨度**是 5.6~5.9 半音，双音区 gap 也明显。
      用户此前的判据正是「F0 跨度 >40Hz 就单独重生成那一句」。
    """
    f = [w["f0"] for w in ws if w["f0"] and w["voiced"] >= VOICED_USABLE]
    if len(f) < 4:
        return {}
    f = np.array(sorted(f), dtype=float)
    p5, p95 = float(np.percentile(f, 5)), float(np.percentile(f, 95))
    out = dict(f0_med=float(np.median(f)), f0_p5=round(p5, 1), f0_p95=round(p95, 1),
               span_st=round(float(12 * np.log2(p95 / p5)), 2) if p5 > 0 else None,
               span_hz=round(p95 - p5, 1), n_f0=len(f))
    # 最大间隙切成两簇（比 kmeans 稳，且能给出每簇大小）
    d = np.diff(f)
    if len(d):
        i = int(np.argmax(d))
        if 2 <= i <= len(f) - 3:            # 两簇各至少 3 个窗
            lo, hi = float(np.median(f[:i + 1])), float(np.median(f[i + 1:]))
            out.update(gap_st=round(float(12 * np.log2(hi / lo)), 2),
                       gap_lo=round(lo, 1), gap_hi=round(hi, 1),
                       gap_n=[i + 1, len(f) - i - 1])
    return out


def one(p, profile="narr", gaps=None, silence_tolerant=False):
    a, sr = read_wav(p)
    dur = len(a) / sr
    S = series(a, sr)
    ws = windows(a, sr, S)
    v, ev, pairs = judge(ws, profile=profile, allow_gaps=gaps,
                         silence_tolerant=silence_tolerant)
    sm = span_metrics(ws)
    return dict(file=p, dur=round(dur, 2), n_win=len(ws), verdict=v, profile=profile,
                ver=JUDGE_VER,
                f0_range=[S["f0_lo"], S["f0_hi"]], span=sm,
                events=ev, windows=ws, pairs=pairs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--one", default="")
    ap.add_argument("--dir", default="")
    ap.add_argument("--list", default="")
    ap.add_argument("--glob", default="*.wav")
    ap.add_argument("--out", default="")
    ap.add_argument("--quiet", action="store_true", help="只出汇总，不逐条打印")
    ap.add_argument("--profile", default="narr", choices=["narr", "dlg"],
                    help="narr=朗读/旁白（F0 阶跃算音色证据）；dlg=表演对白（只看声道形状）")
    a = ap.parse_args()

    files = []
    if a.one:
        files = [a.one]
    elif a.dir:
        files = sorted(glob.glob(os.path.join(a.dir, a.glob)))
    elif a.list:
        files = [x.strip() for x in a.list.split(",") if x.strip()]
    if not files:
        print("没有输入（--one / --dir / --list）", file=sys.stderr)
        return 2

    res = []
    for p in files:
        try:
            r = one(p, profile=a.profile)
        except Exception as e:  # noqa: BLE001
            r = dict(file=p, verdict="ERROR", error=str(e))
        res.append(r)
        if not a.quiet:
            ev = r.get("events") or []
            tag = r["verdict"]
            print("%-34s %6.2fs %-13s %s"
                  % (os.path.basename(p), r.get("dur", 0), tag,
                     ("| " + " ; ".join("%s@%.2fs %s" % (e["level"], e["t"], "/".join(e["why"]))
                                        for e in ev[:3])) if ev else ""))

    from collections import Counter
    cnt = Counter(r["verdict"] for r in res)
    print("\n汇总 %s（共 %d 条）" % (dict(cnt), len(res)))
    if a.out:
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("->", a.out)
    return 0 if cnt.get("FAIL", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
