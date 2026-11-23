# -*- coding: utf-8 -*-
"""mt_detectors.py —— 检测器登记表 + 条件化执行器。

★ 为什么要有这个文件
  2026-10-31 用户要求：「把有好结论的加上回环，但**规则和条件有前提限制的都得加上**，
  就像 n8n 一样，有时候有用，有时候没用。有哪些条件的时候可以先用？说出什么结果的时候可以用？」

  所以每个检测器不是一个阈值，而是四段：
    when      什么时候才允许跑（不满足直接 SKIP，不是 PASS）
    rule      怎么判（含 fail / warn 两档）
    valid     这个结论在什么范围内可信
    blind     它看不见什么（防止拿它当万能判据）

★ 三种 SKIP 不是一回事
  SKIP-条件  ：输入不满足前置（太短 / 没 ref / 没有对照）→ 不是缺陷
  SKIP-证据  ：它在当前区间没有分辨力（如 NISQA <2s）→ 记数值不判
  PASS       ：跑了，且通过

★ 置信来源
  每条都标 evidence，格式「样本量 / 效应量」，没有实测支撑的一律标 TODO，不进判定。
"""
import json
import os
import sys

import numpy as np

ROOT = "G:/_setup"
sys.path.insert(0, ROOT)

# ============================ 单条声学量 ============================

def acoustics(path, role="narr", ref=None):
    """一次算完单条所需的全部声学量。role ∈ narr / charles / hooper。"""
    import soundfile as sf
    from mt_rhythm_bands import measure
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    m = measure(x, sr, role, span_voiced=False)
    m.update(spectral(x, sr))
    m["span_st"] = span_st_robust(x, sr)        # 覆盖 f0_metrics 的旧口径
    cd, pdb, tdb = cut_drop_guarded(x, sr)
    m["cut_drop"], m["_cut_prev"], m["_cut_tail"] = cd, pdb, tdb
    m["_x"], m["_sr"] = x, sr
    m["_nframe"] = int(len(x) / sr / 0.02)
    return m


def spectral(x, sr):
    """谱质心 / 倾斜 / 平坦度 / >4k 能量比（能量前 40% 帧的中位）。"""
    import librosa
    S = np.abs(librosa.stft(x, n_fft=1024, hop_length=256))
    fr = librosa.fft_frequencies(sr=sr, n_fft=1024)
    P = np.maximum(S ** 2, 1e-20)
    tot = P.sum(0)
    m = tot >= np.quantile(tot, 0.60)
    P, T = P[:, m], tot[m]
    cen = float(np.median((fr[:, None] * P).sum(0) / T))
    lf = np.log2(np.maximum(fr[1:], 20.0))
    lp = 10 * np.log10(P[1:] + 1e-20)
    tilt = float(np.median(np.linalg.lstsq(
        np.vstack([lf, np.ones_like(lf)]).T, lp, rcond=None)[0][0]))
    flat = float(np.median(np.exp(np.mean(np.log(P), 0)) / np.mean(P, 0)))
    hi = fr >= 4000
    hf = float(np.median(P[hi].sum(0) / (P.sum(0) + 1e-20)))
    return dict(cent=round(cen, 1), tilt=round(tilt, 2),
                flat=round(flat, 4), hf=round(hf, 4))


def crest_db(x, sr=None):
    """峰值因数。**先裁掉首尾静音再算**（2026-10-31 修）。

    ★★ 为什么必须裁：crest = 峰值 / 全段 RMS，而 RMS ∝ 1/√N。
      补零等于给分母加料，判据随「有没有零尾、零尾多长」整体平移。
      实测 N0194 前后各补 0/0.2/0.5/1/2/4s 零：
        旧口径 20.03 → 20.27 → 20.60 → 21.10 → 21.95 → 23.28（漂 +3.25dB）
        本口径 19.92 → 19.95（全程不动）
      后果很具体：削波样本 N0552 补 1s 零就从 15.99 变成 16.63，直接逃过 16.0 的线。
      拼章/插停顿之后成品与 raw 会给出相反判决 —— 而那正是交付链路的下一步。
    """
    if sr is None:
        r = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12)
        return round(float(20 * np.log10(np.max(np.abs(x)) / r + 1e-12)), 2)
    n = max(1, int(0.005 * sr))
    k = len(x) // n
    if k < 10:
        return None
    db = 20 * np.log10(np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(1)) + 1e-12)
    ref = float(np.percentile(db, 95))
    idx = np.where(db > ref - 40)[0]
    if len(idx) < 3:
        return None
    pad = int(0.05 * sr)
    a = max(0, int(idx[0] * n) - pad)
    b = min(len(x), int((idx[-1] + 1) * n) + pad)
    y = x[a:b].astype(np.float64)
    r = float(np.sqrt(np.mean(y ** 2)) + 1e-12)
    return round(float(20 * np.log10(np.max(np.abs(y)) / r + 1e-12)), 2)


def cut_drop_guarded(x, sr):
    """结尾硬切（带 §7.6 的静音保护）。返回 (drop_db or None, prev_db, tail_db)。

    ★ 为什么必须保护：trim 过的文件末尾是数字零，prev −105dB → tail −234dB，
      算出「掉 128dB」，但那两段都听不见。865 条交付版里 151 条会被误判。
      规则：**跳前 < −50dBFS 一律不判**（那是淡出到零，不是截断）。

    ★★★ 2026-10-31 审计：本链路里这条判据**结构性不可判**，不是调参能救的。
      · `_mt_raw_s42` 80/80 全部落在「跳前 <−50dBFS」分支 —— 模型自己在结尾补了
        约 56ms 的数字零（实测最后非零样本在 304504/307200）。
      · `_mt_pick` 863/865 同样。
      · 也就是说「最后一个音节有没有被切断」这件事，在现有产物上**看不见**：
        有零尾垫时，切没切都长一样。
      另一条路（找最后一个有声帧再看它后面的跌落）也不行：交付版是 trim 出来的，
      末帧本来就落在阈值上，实测 120 条里 26% 会报 >40dB —— 那测的是 trim，不是生成。
      ⇒ 保留代码供「无尾垫的原始 wav」显式调用，但在主链路里它只应产出 SKIP。
    """
    n5, n20 = max(1, int(0.005 * sr)), max(1, int(0.020 * sr))
    if len(x) < n5 + n20:
        return None, None, None
    t = float(np.sqrt((x[-n5:] ** 2).mean()) + 1e-12)
    pv = float(np.sqrt((x[-(n5 + n20):-n5] ** 2).mean()) + 1e-12)
    pdb, tdb = 20 * np.log10(pv), 20 * np.log10(t)
    if pdb < -50.0:
        return None, round(pdb, 1), round(tdb, 1)
    return round(pdb - tdb, 1), round(pdb, 1), round(tdb, 1)


def span_st_robust(x, sr, floor=60.0, ceil=400.0, vt=0.20):
    """音高跨度（st），**复测口径**：60-400 + 迭代剔八度 + p10~p90。

    ★★ 别用 mt_rhythm_bands.f0_metrics 的 span_st：
       那个是 60-250 / p95−p5 / **不剔八度**，压平的信号会被八度错帧撑回去
       （实测 N0194_mono：f0_metrics 13.9st 「正常」，本函数 2.9st 「已压平」）。
       两个同名量的用途不同：本函数判「有没有被压平」（单条），
       f0_metrics 那个只做 n≥20 的形状描述。
    """
    import parselmouth
    s = parselmouth.Sound(np.ascontiguousarray(x), sampling_frequency=sr)
    p = s.to_pitch_ac(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceil,
                      voicing_threshold=vt, silence_threshold=0.03)
    f = np.asarray(p.selected_array["frequency"], dtype=float)
    v = f[f > 0]
    if len(v) < 30:
        return None
    for _ in range(3):
        m = float(np.median(v))
        if m <= 0:
            break
        keep = v[(v > m / 2.2) & (v < m * 2.2)]
        if len(keep) == len(v):
            break
        v = keep
    if len(v) < 20:
        return None
    return round(float(12 * np.log2(np.percentile(v, 90) / np.percentile(v, 10))), 2)


def flat_share(x, sr):
    """谱平坦度中位（只在能量前 40% 帧上算）。"""
    import librosa
    S = np.abs(librosa.stft(x, n_fft=1024, hop_length=256))
    P = np.maximum(S ** 2, 1e-20)
    tot = P.sum(0)
    m = tot >= np.quantile(tot, 0.60)
    return round(float(np.median(np.exp(np.mean(np.log(P[:, m]), 0)) / np.mean(P[:, m], 0))), 4)


# ============================ 登记表 ============================
# scope: item / pair / group / batch
# level: veto（能拒收）/ warn（只报）/ info（只记录）
DETECTORS = [
 # ---------------- 单条：新增（本次复测拿到正结论） ----------------
 dict(id="crest_clip", name="削波", scope="item", level="veto",
  escalate=["FAIL"],
  what="波形被硬削顶（增益过头 / 限幅器误用）",
  when=dict(min_sec=1.0),
  rule="crest < 16.0 dB → FAIL；16.0~17.0 → WARN",
  fail=16.0, warn=17.0, higher_is_better=True,
  valid="865 条交付版实测 p1=16.65 / p50=20.21 / p99=24.68；5 条注入削波 12.2~16.0dB（p50 14.6）。"
        "**先裁首尾静音再算**（补零不变性：同一文件补 0→4s 零，本口径只动 0.03dB，旧口径漂 3.25dB）。"
        "自产 865 条实测 p1=16.36 / p50=20.09 / min=15.53；5 条注入削波 11.75~15.92。"
        "16.0 卡在削波上界 15.92 与好样本 p1 之间 —— 5/5 全拦、误杀 2/865=0.23%",
  blind="看不见「内部失真」—— L053 峰值只有 0.34 却听着炸，crest 抓不到那一类",
  evidence="5 好 vs 5×4 增益硬切：AUC 1.00；差 6.1dB / 抖动 SD 1.3 ≈ SNR 4.7"),

 dict(id="span_flatten", name="音高被压平", scope="item", level="veto",
  escalate=["FAIL", "WARN"],
  what="整句 F0 压成一个音（去语调）",
  when=dict(min_sec=1.5, need="f0"),
  rule="span_st < 3.0 st → FAIL；3.0~4.5 → WARN（60-400 剔八度 p10~p90 口径）",
  fail=3.0, warn=4.5, higher_is_better=True,
  valid="只判「有没有被压平」。3.0 是「好样本最小值 6.63 − 1.6×跨 seed SD(2.264)」算出来的，"
        "但以均值为中心其实是 −2.67σ（单侧 0.38%）—— 两种说法差 14 倍，这条线从来没被真正描述过。"
        "865 条实测 p1=3.19 / p50=7.28；跨 seed 56 条里 2 条落线以下（3.6%，N0755 单独 18%）。"
        "★★ 判决量是 12·log2(p90/p10)，**只读两个分位点**。"
        "而 p10 在「低频杂帧占比跨过 10%」时会**阶跃**：实测 8.3%→span 0.00、"
        "10.7%→span 6.17（0.8 个百分点的增量跳 6.17st，之后 25% 也不再动）。"
        "⇒ 它测的是「杂帧有没有爬过 10%」，不是「压平程度」；5 条同类样本读数 "
        "0.54/0.76/2.95/4.22/5.46，均值 2.79 / SD 2.14 / **类内 CV 77%**。"
        "★ 但**全局是分得开的**：AUC(mono<normal)=**0.958**、d=2.40 —— "
        "**不能**写成「两类不可辨识」，那是错的。真正的毛病是 **ROC 陡起后平台**："
        "3.0→召回 3/5(60%, 95%CI 23~88)、误报 0.23%；4.5→4/5、6.05%；5.46→5/5、15.7%。"
        "**每多抓 1 条真阳性要多误杀 50~83 条正常 take。**"
        "★ **ROC 是单调的（AUC 0.958），3.0 恰好落在拐点上**："
        "2.90→2/5(误报 2)、**3.00→3/5(误报仍 2，多抓 1 条零成本)**、3.20→3/5(误报 9)、"
        "4.00→3/5(29)、4.50→4/5(56)、5.47→5/5(141)。"
        "3.2 之后召回完全不动只涨误报 ⇒ 3.0 不是随手取的数，它已经在最便宜的位置。"
        "⇒ 结论维持「不动 3.0/4.5」：要提召回得先修估计量（±2.2 窗装得下 12st 八度错），"
        "那是换统计量，不是调阈值。"
        "根因比「阈值不对」更深：**这个量在正类内部就不单调**。mono 5 条的 span 读数由"
        "「主峰外残留多少低频杂帧」决定（N0194_mono p10=69/p50=93/p90=94 → 5.46；"
        "N0755_mono 76/78 → 0.76），与压平程度无关（八度帧占比只有 0~2%，与 span 的 "
        "Spearman 仅 0.30）。不单调的量，阈值放到哪都没有单调 ROC。"
        "★ 另：`span_st_robust` 里那个「剔八度」循环的窗口是 (m/2.2, m*2.2) = **±13.7st**，"
        "而整八度只有 12st ⇒ **它从来剔不掉八度错**（12 < 13.7 在窗内），只剔得掉 >2.2 倍的"
        "「比八度还离谱」的帧。真实双音区 60/40 时又是 3.33 倍超窗、整簇删光 → 0.00st。"
        "**不能**判「够不够起伏」——真人个体 4.17~16.99，组间差只有 4.26",
  blind="天然平叙句（列举、低声）会被误判；须配 text 判断是否本该有起伏",
  evidence="5 好 vs 5 整句压单音：AUC 1.00 / SNR 2.96（好 9.65 / 坏 2.95）"),

 dict(id="espan_flat", name="起伏太平/太陡", scope="item", level="warn",
  what="句内 21 点能量轮廓极差（双向）",
  when=dict(min_sec=2.5, min_frames=42),
  rule="读 _rhythm_bands.json 的 p05/p95 带；超 ±2.5dB 才判 FIX",
  valid="2.5s 以上才判；2.5dB 是跨 seed 噪声 p75，低于它是在追噪声",
  blind="★★ 现口径 `db > p90−25` 是相对阈值，**整条被压平会反向判**；"
        "压平检测请用 span_voiced 或 span_flatten",
  evidence="跨 seed |差| p50 1.4 / p75 2.5dB（854 对）；不变性 SNR 14.05",
  escalate=[],
  blocked="★★★ 2026-10-31 审计：指标本身不对口，不是 band 的问题。"
          "5 条慢包络等响退化 vs 好样本：17.1 / 16.8 / 21.1 / 16.0 / 16.9 vs 13.5 / 16.7 / 15.4 / 12.8 / 14.2"
          " —— **压平之后反而更大**，方向错；40 条注入退化里 0/5 报出，AUC 0.64 / SNR 0.05。"
          "另：同一 (take, band, deadzone) 换三个合法 band 来源，FIX 率 0% / 0.63% / 10.2%（12 倍）。"
          "⇒ 在《起伏太平》这个目标上它是零灵敏度 + 任意的误报率。改法只能换指标"
          "（span_voiced 口径 4/5 但方向不稳：1 降 2 升 2 降）。当前只记录数值，不做判定。"),

 dict(id="cut_drop", name="结尾硬切", scope="item", level="veto",
  escalate=["FAIL"],
  what="最后一个音节被切断（dots.tts 通病）",
  when=dict(min_sec=0.5),
  rule="cut_drop > 40 dB → FAIL；**跳前 < −50dBFS 一律 SKIP**",
  valid="只对**未 trim** 的原始生成有意义；trim 过的文件末尾是数字零，必误判",
  blind="自然收尾的爆破音 /t/ 可能擦边；trim 造成的硬切它看不见（也不该看见）",
  evidence="L083 结尾 −18→−92dB 在 5ms 内；6 个 seed 全一样"),

 dict(id="air_breath", name="气声化", scope="item", level="warn",
  escalate=[],
  what="高频气声占比过高（<rate> 拉低后的真实副作用）",
  when=dict(min_sec=1.0, need="hf_abs"),
  rule="hf > 0.25 且 谱平坦度 > 0.06 → WARN（两项同时，单看一项会误报）",
  valid="必须两项同时；实测气声化 hf 0.001→0.159、平坦度 0.000→0.108",
  blind="擦音多的句子（/s/ /f/）天然 hf 高；短词被擦音占满会误报",
  evidence="5 条 × 混 35% 高通白噪：hf ×159 / 平坦度 ×∞（0→0.108）",
  blocked="★★★ 2026-10-31 审计：标定对象错了，判据在真实素材上不可达。"
          "① 865 条交付版 hf 的 p50=0.0008、**max=0.0327**，规则要 >0.25（高 7.6 倍），"
          "p99 也够不着 ⇒ 永远 0 报出；② 99.4% 还被 when 的 hf<0.02 挡掉；"
          "③ 当初的正样本是「混 35% 高通白噪」，那不是气声化 —— 那是把低频整个抽走"
          "（谱质心 248→8822Hz）。真实气声化（F0 还在、HNR 掉）实测平坦度反而**下降**"
          "（0.55→0.51）。要重做：先用 HNR 落差 + 高频绝对量，别用平坦度。"),

 dict(id="oct_err", name="八度跟踪错", scope="group", level="info",
  what="F0 提取把基频锁到 2 倍频",
  when=dict(min_n=20),
  rule="组内 oct_err 中位 > 5% → 该批 F0 类判据全部降级",
  valid="只做组级；单条 44 条里判不出（AUC 0.44）",
  blind="对真正的高八度喊叫无能为力（那本来就是 2 倍频）",
  evidence="单条 AUC 0.44（对 jitter）；组内中位才是稳定量"),

 # ---------------- 单条：已有工具，条件写清 ----------------
 dict(id="nisqa_dis", name="断流/伪影", scope="item", level="warn",
  escalate=["FAIL", "WARN"],
  what="NISQA Discontinuity（唯一可用的断流判据）",
  when=dict(min_sec=2.0, need="nisqa", no_pause=True),
  rule="dis < 2.0 → FAIL；< 3.0 → WARN",
  valid="≥2s 且**已剪掉插入的停顿**；不剪测的是停顿占比（N0824 DIS 1.87→3.45）",
  blind="与时长相关 r=0.42；<2s 一律不定级",
  evidence="合成集 chop 1.00 / hole 0.92；真池 AUC 0.48（标签是「句子短」代理）"),

 dict(id="nisqa_mos", name="整体音质", scope="item", level="warn",
  escalate=["FAIL", "WARN"],
  what="NISQA MOS",
  when=dict(min_sec=2.0, need="nisqa"),
  rule="mos < 2.5 → FAIL；< 3.0 → WARN",
  valid="只当「明显不行」的下限筛，不能排序、不能选最优 take",
  blind="同句换 take 的 |Δ| p50 0.58 ⇒ 效应小于噪声",
  evidence="合成集 0.84；真池 0.49"),

 dict(id="seg_drift", name="句内音色突变", scope="item", level="warn",
  escalate=["FAIL"],
  what="0.5s 窗 / 0.25s 步的 F0/HNR/能量突变（edit 加情绪时音色消失）",
  when=dict(min_sec=1.5, need="path"),
  rule="HNR 塌 ≥15dB 单次即 FAIL；其余孤立事件降 WARN",
  valid="≥1.5s（≥3 窗）才有意义；阈值由 180 条正常旁白 p99 定",
  blind="<0.1s 的拼接点抓不到（窗长 0.5s）；要 16ms 帧级谱通量",
  evidence="正常批次 FAIL 8% / 对白 7%"),

 dict(id="asr_cover", name="吞字", scope="item", level="veto",
  escalate=["FAIL"],
  what="ASR 逐词比对覆盖率",
  when=dict(need="text"),
  rule="cov < 0.80 → FAIL",
  valid="短句更敏感（分母小）；缩写/连字符必须先归一",
  blind="同音替换（ship/sheep）测不出；ASR 对 ≠ 音色对",
  evidence="三类假阳性归一后 10→1；PASS 88.4%→89.6%"),

 dict(id="voice_band", name="音色档", scope="item", level="warn",
  escalate=["WARN"],
  what="F0 中位 / 谱质心 / 谱倾斜 对本档 ref",
  when=dict(need="ref"),
  rule="三取二出带：F0 ±3 半音 / 质心 ×0.78~1.28 / 倾斜 ±3",
  valid="必须用**同一档**的 ref（8 档各自基线），跨档比一律无效",
  blind="跨档比会全判 FAIL（同一句不同情绪声纹只有 0.213）",
  evidence="所谓「对角线 88/83/100/100/100/100/100/75%」= 每档 n_clips 的 in-sample 回代率"
           "（8/6/4/3/3/2/5/4 条），不是验证集准确率。而「三取二」在独立假设下的随机期望就是 "
           "C(3,2)·0.8²·0.2+0.8³=89.6% ⇒ 88/83 不高于随机、75 低于随机。这条只能算装饰"),

 dict(id="spk_cos", name="声纹余弦", scope="item", level="info",
  escalate=[],
  what="CAM++ 余弦 vs 同角色 ref",
  when=dict(min_sec=4.0),
  rule="< 0.15 才拦；其余只记录",
  valid="≥4s 才记；短段噪声底 ±0.5（前半 vs 后半 0.346）",
  blind="**不能否决**。AUC 0.491 = 随机，方差主要来自内容",
  evidence="同 ref 同句不同 seed 0.796 / 同 ref 不同句 0.344"),

 dict(id="rdr", name="接缝语速", scope="pair", level="warn",
  what="拼接处两侧 voiced 语速比",
  when=dict(need="pair", order="before_pause"),
  rule="max(r1/r2, r2/r1) > 1.5 → WARN",
  valid="**必须在插停顿之前**跑；插完再量会把停顿算进语速",
  blind="整章匀速但整体偏慢测不出（那是组级 wpm 的事）",
  evidence="主口径 C（voiced 总和），阈值 1.5×"),

 # ---------------- 组级（n≥20 才采信） ----------------
 dict(id="g_span_st", name="组级音高幅度", scope="group", level="info",
  what="组内 span_st 中位",
  when=dict(min_n=20),
  rule="与真人带比：真人 p50 7.06（p25 5.35 / p75 9.04）",
  valid="n≥20 才能说「这批偏宽/偏窄」；单条差值不可信",
  blind="真人个体 4.17~16.99 ⇒ 组间差 4.26 的可信度本身有限",
  evidence="我们 11.26 vs 真人 7.06；不变性 SNR 5.97"),

 dict(id="g_rev", name="组级方向反转率", scope="group", level="info",
  what="念经感签名之一",
  when=dict(min_n=20),
  rule="真人 15.08（p25 12.71 / p75 17.51）；我们 12.61",
  valid="**只能组级**。单条对 F0 压平 AUC 0.00 —— 这是「符号取反后 100% 可分」，"
        "不是「判不出」：好 4.32 / 坏(mono) 5.88，压平后反转率**升高**（F0 压成单音，"
        "提取抖动变成密集反转）。n=5 时 1.00 是乐观值，SNR 1.6 ⇒ 合理估计 ~0.85",
  blind="过一遍声码器就变（SNR 1.03）",
  evidence="18.29 组级差 2.5 次/秒；18.30 单条 SNR 1.03"),

 dict(id="g_slope", name="组级句首/句尾斜率", scope="group", level="info",
  what="句首句尾都往下掉的「念经」形状",
  when=dict(min_n=20),
  rule="真人 head −2.36 / tail −0.35；我们 −4.48 / −2.52",
  valid="只做形状描述，不做判定",
  blind="SNR 1.42/1.80，过声码器变 7 st/s",
  evidence="18.29 组级表；18.30 不变性"),

 dict(id="g_loc", name="组级音高提升", scope="group", level="info",
  what="词级音高抬了多少（TTSDS2 Pitch 因子的对照量）",
  when=dict(min_n=20, need="prom"),
  rule="真人最高音词 loc +2.71 半音；我们 +2.74（分位 86）",
  valid="组级可以看「寄存器有没有抬起来」；单条与 PMOS 只 r=0.30",
  blind="pitch 只抬寄存器不改轮廓（Prosogram 独立佐证）",
  evidence="18.17 真人锚点；18.20 loc 退役但 Pitch 因子 +7.31"),

 dict(id="g_gliss", name="组级滑音选择性", scope="group", level="info",
  what="句内最长词的滑音率 − 其余词滑音率",
  when=dict(min_n=40, need="prosogram"),
  rule="真人 +20.2 点（70.2% vs 50.0%）；我们 delivered +1.9 / ctl +8.4",
  valid="**不能当闸门**：对照比交付版还高",
  blind="单条 take 只有一个核，二值方差过大",
  evidence="18.19 McNemar 51 对全 50/50"),

 # ---------------- 批次 ----------------
 dict(id="b_proso", name="批次韵律像不像真人", scope="batch", level="info",
  what="TTSDS2 PROSODY 四因子对真人 159 句的分布距离",
  when=dict(min_n=10),
  rule="门槛 80 是**地板不是判别器**（实测两批 83.13 / 84.76）",
  valid="只拦明显坏掉的批次；要真判别需 ≥10 批次标定",
  blind="单条不能拆（MPM 是逐帧 63588×256）；Pitch 因子与人耳相关只有 0.34~0.60",
  evidence="delivered 83.66 / cand 80.79 / ctl 85.06 ⇒ 标签净负收益"),

 dict(id="b_nat", name="批次自然度下限", scope="batch", level="warn",
  what="NISQA-MOS/DIS/COL + SQUIM 的 z 均值（min 融合，不用平均）",
  when=dict(min_n=10),
  rule="残差 < −2.3 → FAIL；< −1.4 → WARN；语音 <0.9s 判 UNKNOWN",
  valid="只当下限筛。长度回归只在 <1.2s 用（全段回归 AUC 0.70→0.56）",
  blind="stutter 全模型失效（0.56）；同句换 take |Δ| p50 0.58",
  evidence="合成集组合 0.90；真池全部覆盖 0.5（标签坏）"),

 dict(id="b_scs", name="批次音色簇", scope="batch", level="info",
  what="角色内音色一致性（簇中心用均值，保持变长输入）",
  when=dict(min_n=10, need="spk"),
  rule="只排尾部，不设验收阈值",
  valid="σ 只有 0.08 ⇒ κ=2 会让 SCS 塌到 0.001",
  blind="固定 3s 窗 + 循环补长会饱和到 0.94+，分辨力归零",
  evidence="12.4 两个实现坑；簇中心中位数会让余弦掉到 0.03"),
]

BY_ID = {d["id"]: d for d in DETECTORS}


# ============================ 条件检查 ============================

def _need_ok(d, m, ctx):
    """返回 (ok, skip_kind, reason)。skip_kind ∈ cond / evidence / blocked。"""
    w = d.get("when") or {}
    if w.get("min_sec") and m.get("dur", 0) < w["min_sec"]:
        return False, "cond", "时长 %.2fs < %.1fs" % (m.get("dur", 0), w["min_sec"])
    if w.get("min_frames") and m.get("_nframe", 999) < w["min_frames"]:
        return False, "cond", "帧数不足"
    if w.get("need") == "f0" and m.get("span_st") is None:
        # ★ 以前写 `not m.get("span_st")`：span_st 恰好等于 0.0（完全被压平 = 最该抓的那条）
        #   会被当成「F0 不可测」直接 SKIP —— veto 判据把最坏的样本放过去了。
        return False, "cond", "F0 不可测"
    if w.get("no_pause") and ctx.get("paused"):
        # 「已剪掉插入停顿」这条前置以前**从来没被检查过**。NISQA-DIS 在插了停顿的
        # 成品上是把停顿当断流测（N0824 实测 1.87 → 剪掉后 3.45）。现在按 ctx 声明拦。
        return False, "cond", "输入已插停顿：DIS 会把停顿算成断流（N0824 1.87→3.45）"
    if w.get("order") == "before_pause" and ctx.get("paused"):
        return False, "cond", "必须在插停顿之前跑，当前输入已插停顿"
    if w.get("need") == "ref" and not ctx.get("ref"):
        return False, "cond", "无同档 ref"
    if w.get("need") == "text" and not ctx.get("text"):
        return False, "cond", "无参考文本"
    if w.get("need") == "pair" and not ctx.get("pair"):
        return False, "cond", "无对照 take"
    if w.get("need") == "nisqa" and not m.get("nisqa"):
        return False, "cond", "NISQA 未跑"
    if w.get("need") == "hf_abs" and (m.get("hf") or 0) < 0.02:
        return False, "evidence", "高频绝对量 %.3f < 0.02，比值不可用" % (m.get("hf") or 0)
    if w.get("min_n") and ctx.get("n", 0) < w["min_n"]:
        return False, "cond", "组内 n=%d < %d" % (ctx.get("n", 0), w["min_n"])
    # ★ 2026-10-31：path / prom / prosogram / spk 以前没有分支，条件形同虚设
    #   （登记表照样打印「有 wav 路径」「有 .prom」等说明，实现里一句没查）。
    #   现在统一按 ctx 里的键做存在性检查，缺就 SKIP。
    _NEED_KEY = {"path": "path", "prom": "prom", "prosogram": "prosogram", "spk": "spk"}
    need = w.get("need")
    if need in _NEED_KEY and not ctx.get(_NEED_KEY[need]):
        return False, "cond", "缺少 %s" % _NEED_KEY[need]
    if need and need not in ("f0", "ref", "text", "pair", "nisqa", "hf_abs",
                             "path", "prom", "prosogram", "spk"):
        # 未知 need 一律不放行 —— 宁可 SKIP，也不要「条件写了但没人查」
        return False, "cond", "未知前置条件 need=%s" % need
    return True, None, ""


def item_check(m, ctx=None):
    """对一条 take 跑所有 scope=item 的检测器。m 来自 acoustics()。"""
    ctx = ctx or {}
    res = []
    for d in DETECTORS:
        if d["scope"] != "item":
            continue
        # ★ 2026-10-31：显式 blocked 的检测器一律 SKIP，且把原因带出来。
        #   以前这些会掉到 _judge 兜底 `return "PASS","（无判定逻辑，仅登记）"`，
        #   在报告里长成「已检查通过」—— 是假证据。
        if d.get("blocked"):
            res.append(dict(id=d["id"], name=d["name"], level=d["level"],
                            escalate=d.get("escalate"),
                            verdict="SKIP", skip="blocked", why=d["blocked"]))
            continue
        ok, kind, why = _need_ok(d, m, ctx)
        if not ok:
            res.append(dict(id=d["id"], name=d["name"], level=d["level"],
                            escalate=d.get("escalate"),
                            verdict="SKIP", skip=kind, why=why))
            continue
        v, detail = _judge(d, m, ctx)
        # ★ 2026-10-31：把「能不能拒收」显式写进结果，而不是让读的人自己去推
        #   level 与 escalate 的组合。**不归一 verdict** —— 一归一，escalate=["FAIL"]
        #   的 warn 级检测器（seg_drift）就永远匹配不上，直接失去判定权。
        can_reject = (d["level"] == "veto")
        if v == "FAIL" and not can_reject:
            detail = "%s（%s 级：只报不拒）" % (detail, d["level"])
        res.append(dict(id=d["id"], name=d["name"], level=d["level"],
                        can_reject=can_reject, escalate=d.get("escalate"),
                        verdict=v, why=detail))
    return res


def _judge(d, m, ctx):
    i = d["id"]
    if i == "crest_clip":
        c = crest_db(m["_x"], m.get("_sr"))
        if c is None:
            return "SKIP", "无可测语音段"
        if c < d["fail"]:
            return "FAIL", "crest %.1fdB < %.1f（削波）" % (c, d["fail"])
        if c < d["warn"]:
            return "WARN", "crest %.1fdB 偏低" % c
        return "PASS", "crest %.1fdB" % c
    if i == "span_flatten":
        s = m["span_st"]
        if s < d["fail"]:
            return "FAIL", "span_st %.1fst < %.1f（音高被压平）" % (s, d["fail"])
        if s < d["warn"]:
            return "WARN", "span_st %.1fst 偏窄" % s
        return "PASS", "span_st %.1fst" % s
    if i == "espan_flat":
        s = m.get("energy_span")
        if s is None:
            return "SKIP", "span 不可测"
        # ★★★ 2026-10-31 修：原来取的是 ctx["band"]（= bands[role]，顶层是
        #   {"n","energy_span","span_st",...}），b.get("p05") 恒为 None →
        #   拿默认 −99 / 99 去比，**任何值都 PASS**（实测 5/16/60/99dB 全过）。
        #   正确层级是 band["energy_span"]["p05"]。
        b = ctx.get("band") or {}
        be = b.get("energy_span") if isinstance(b.get("energy_span"), dict) else b
        lo, hi = be.get("p05"), be.get("p95")
        if lo is None or hi is None:
            return "SKIP", "带缺失（需 p05/p95）"
        if s < lo - 2.5:
            return "FIX_LOW", "%.1f < p05−2.5（%.1f）" % (s, lo - 2.5)
        if s > hi + 2.5:
            return "FIX_HIGH", "%.1f > p95+2.5（%.1f）" % (s, hi + 2.5)
        return "PASS", "%.1f ∈ 带内 [%.1f, %.1f]" % (s, lo - 2.5, hi + 2.5)
    if i == "cut_drop":
        c = m.get("cut_drop")
        if c is None:
            return "SKIP", "跳前 %.0fdBFS < −50：模型自带零尾垫，切断与否不可分辨" % (m.get("_cut_prev") or -99)
        if c > 40:
            return "FAIL", "结尾 5ms 掉 %.0fdB（跳前 %.0fdBFS）" % (c, m.get("_cut_prev") or 0)
        return "PASS", "结尾掉 %.0fdB" % c
    if i == "air_breath":
        f = m.get("flat") or 0.0
        hf = m.get("hf") or 0
        if hf > 0.25 and f > 0.06:
            return "WARN", "hf %.3f / 平坦度 %.3f（气声）" % (hf, f)
        return "PASS", "hf %.3f / 平坦度 %.3f" % (hf, f)
    if i == "seg_drift":
        # ★ 2026-10-31 真接上。以前这里是空壳（落到兜底 return PASS "仅登记"），
        #   而它恰恰是「同一句里某段音色没了」唯一的单条判据。真实现是 mt_seg_drift.one()。
        p = ctx.get("path")
        if not p:
            return "SKIP", "无 wav 路径"
        r = ctx.get("seg")          # 复用调用方已经算好的结果，避免同一条跑两遍
        try:
            if not r:
                import mt_seg_drift as SD
                r = SD.one(p)
        except Exception as e:  # noqa: BLE001
            return "SKIP", "调用 mt_seg_drift 失败：%s" % str(e)[:60]
        v = r.get("verdict")
        ev = r.get("events") or []
        nf = len([e for e in ev if e.get("level") == "FAIL"])
        nw = len([e for e in ev if e.get("level") == "WARN"])
        if v == "FAIL":
            return "FAIL", "句内 %d 处突变（窗 %d）" % (nf, r.get("n_win", 0))
        if v == "WARN":
            return "WARN", "句内 %d 处待复核" % nw
        if v in ("INSUFFICIENT", "NO_SPEECH"):
            return "SKIP", "可测窗不足（%d）" % r.get("n_win", 0)
        return "PASS", "句内平稳（窗 %d）" % r.get("n_win", 0)
    if i == "asr_cover":
        return "SKIP", "本执行器不跑 ASR；吞字由 _gate.gate_one（COV_MIN=0.80）判"
    if i == "oct_err":
        o = m.get("oct_err")
        if o is None:                       # ★ 0 是「没有八度错」= 最好，不是「无测量」
            return "SKIP", "无测量"
        return ("WARN", "八度错 %d 处" % o) if o > 5 else ("PASS", "八度错 %d" % o)
    if i in ("nisqa_dis", "nisqa_mos"):
        n = m["nisqa"]
        k = "dis" if i == "nisqa_dis" else "mos"
        fail = 2.0 if k == "dis" else 2.5
        if n[k] < fail:
            return "FAIL", "%s %.2f" % (k, n[k])
        if n[k] < 3.0:
            return "WARN", "%s %.2f" % (k, n[k])
        return "PASS", "%s %.2f" % (k, n[k])
    # ★ 兜底不再是 PASS。以前是 `return "PASS","（无判定逻辑，仅登记）"`，
    #   于是 seg_drift / spk_cos / voice_band / asr_cover 在报告里长成「已通过」，
    #   实际一行判定都没执行 —— 假证据。现在明确标 SKIP + 指向真实实现。
    _REAL = {"seg_drift": "mt_seg_drift.judge()",
             "asr_cover": "_gate.gate_one（COV_MIN=0.80）",
             "voice_band": "mt_voice_gate.judge()",
             "spk_cos": "mt_spk_audit + spk_embed"}
    if i in _REAL:
        return "SKIP", "本执行器未实现，真判据在 %s" % _REAL[i]
    return "SKIP", "无判定逻辑"


def summarize(res, order=("FAIL", "FIX_HIGH", "FIX_LOW", "WARN", "PASS", "SKIP")):
    """汇总一条 take 的检测结论。

    ★ 2026-10-31：空列表以前返回 "PASS" —— 而调用方（mt_loop）先做
      `[x for x in _d if x["verdict"] != "SKIP"]`，全 SKIP 时正好传进来 []，
      「全部测不了」就被写成了「全部通过」。现在空列表返回 "SKIP"。
    """
    if not res:
        return "SKIP"
    for v in order:
        if any(r["verdict"] == v for r in res):
            return v
    return "SKIP"


def coverage(res):
    """一条 take 的检测覆盖情况：各自跑了几项、跳了几项、为什么跳。

    ★ 2026-10-31 补：`warn` 分两个数。
      `warn`        = 判定上真出了告警的
      `warn_muted`  = 出了告警、但 escalate 没声明这一档 ⇒ 外层仍是 PASS
      以前只有一个 `warn`，于是会出现「cov.warn=1 + 外层 PASS」——
      读起来是「检查过、有告警、判定通过」，实际是告警被 escalate 静默丢掉了。
      现在 mute 掉的那部分单独计数，不再混进有效告警。
    """
    from collections import Counter
    c = Counter(r["verdict"] for r in res)
    sk = Counter((r.get("skip") or "other") for r in res if r["verdict"] == "SKIP")
    ran = c.get("PASS", 0) + c.get("WARN", 0) + c.get("FAIL", 0) \
        + c.get("FIX_LOW", 0) + c.get("FIX_HIGH", 0)
    warn_v = ("WARN", "FIX_LOW", "FIX_HIGH")
    muted = [r for r in res if r["verdict"] in warn_v
             and r["verdict"] not in (r.get("escalate") or [])]
    eff = [r for r in res if r["verdict"] in warn_v and r not in muted]
    return dict(ran=ran, total=len(res),
                pass_=c.get("PASS", 0), fail=c.get("FAIL", 0),
                warn=len(eff), warn_muted=len(muted),
                skip=c.get("SKIP", 0), skip_kind=dict(sk))


IMPL_EXTERNAL = {"asr_cover", "voice_band", "spk_cos"}   # 真实现不在本执行器


def status_of(d):
    """登记表的一行到底是「在跑」「没接」还是「下线」。"""
    if d["scope"] != "item":
        return "已登记未接入"      # group/pair/batch：全仓库没有执行路径
    if d.get("blocked"):
        return "已下线"
    if d["id"] in IMPL_EXTERNAL:
        return "已登记未实现"
    return "在跑"


def capability():
    """一句话说清真实覆盖度：登记 N / 接入 M / 生效 K。"""
    n_all = len(DETECTORS)
    item = [d for d in DETECTORS if d["scope"] == "item"]
    live = [d for d in item if status_of(d) == "在跑"]
    from collections import Counter
    return dict(registered=n_all, wired=len(item), live=len(live),
                by_status=dict(Counter(status_of(d) for d in DETECTORS)),
                live_ids=[d["id"] for d in live])


def matrix():
    """给报告用：把登记表摊平。"""
    out = []
    for d in DETECTORS:
        out.append(dict(id=d["id"], name=d["name"], scope=d["scope"],
                        level=d["level"], what=d["what"], rule=d["rule"],
                        when=_when_text(d.get("when") or {}),
                        valid=d["valid"], blind=d["blind"], evidence=d["evidence"],
                        blocked=d.get("blocked"), status=status_of(d)))
    return out


def _when_text(w):
    p = []
    if w.get("min_sec"):
        p.append("时长 ≥ %.1fs" % w["min_sec"])
    if w.get("min_frames"):
        p.append("≥ %d 帧" % w["min_frames"])
    if w.get("min_n"):
        p.append("组内 n ≥ %d" % w["min_n"])
    if w.get("need"):
        p.append({"f0": "F0 可测", "ref": "有同档 ref", "text": "有参考文本",
                  "pair": "有同句对照", "nisqa": "NISQA 已跑",
                  "hf_abs": "高频绝对量 ≥ 0.02", "path": "有 wav 路径",
                  "prom": "有 .prom", "prosogram": "有 Prosogram",
                  "spk": "有声纹模型"}.get(w["need"], w["need"]))
    if w.get("order"):
        p.append("须在%s之前" % ("插停顿" if w["order"] == "before_pause" else w["order"]))
    if w.get("trimmed"):
        p.append("已剪插入停顿")
    return " 且 ".join(p) or "无"


if __name__ == "__main__":
    for r in matrix():
        print("%-14s %-6s %-4s %-22s %s" % (r["id"], r["scope"], r["level"],
                                            r["name"], r["when"]))
    c = capability()
    print("\n登记 %d / 接入 %d / 生效 %d：%s"
          % (c["registered"], c["wired"], c["live"], "、".join(c["live_ids"])))
    print("状态分布：%s" % c["by_status"])
