# -*- coding: utf-8 -*-
"""对白链路统一闸门：技术 / 声纹 / 情绪 三道，输出三档判定。

为什么需要它
------------
之前链路是散的：`chain_check.py` 只判声纹、`emo_bench/verdict.py` 只判情绪、
`final_report.py` 是离线批处理要两个上游 json。**没有一个入口能「给一条音频就出结论」。**
这个脚本把三道闸门串成一条，并且给出可执行的下一步动作，而不是只报分数。

三档而不是二分类（沿用 _gate.py 的哲学）
--------------------------------------
  PASS     直接可用
  REGEN    明确不合格，重生成（附具体原因）
  MANUAL   证据不足 / 贴线，交人工听

二分类的问题：贴线样本被判「过」会混进交付，被判「不过」会被无谓重生成。
实测里「情绪贴 P10-P25」这类正好是人工该听的那一批。

用法
----
  python dialog_gate.py --wav I05.wav --who C --emo 兴奋
  python dialog_gate.py --dir ch123_final --manifest _ch123_final.json --out out/gate.json
  python dialog_gate.py --probe --dir ch123_final --manifest _ch123_final.json
  python dialog_gate.py --dir ch123_final --manifest _ch123_final.json --emo-auto
  python dialog_gate.py --dir ch123_final --identify          # 剪辑场景：判归属不判对错

默认 = soft 档角色/情绪分离 + z_target ≤ 0 判 MANUAL + 两视角冲突判 MANUAL。
`--no-split-soft` 回到旧基线，`--loose-role` 复现「删 soft 档」的老方案。

环境
----
**必须用 G:/Python310**（唯一同时有 onnxruntime 与 torch 的解释器）。
默认 env 缺 parselmouth / torch，跑不了情绪闸门。

判据来源
--------
声纹：1-NN + Z-norm（REPORT_SPEAKER_EMOTION_REF.md §3）
情绪：六类定档（REPORT_EMOTION_JUDGE.md §15）
角色/情绪分离 + 绝对下限 + 两视角冲突：REPORT_DIALOG_GATE.md §10（默认口径）

一句话：**soft 档只做情绪参考、不参与角色归属**。Charles/soft 那 3 条低声素材
会把 Thomas 的低声句全吸过去，但整档删掉又丢了委屈的情绪参照，所以按用途拆成两份视角。
"""
import os
import sys
import json
import argparse
import collections

import numpy as np

# 路径集中到 _paths.py：本机保持 G:/_setup 原值，云上按 MR_ROOT 解析
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P

for _p in (P.ROOT, os.path.join(P.ROOT, "emo_bench"), "G:/voice_lib"):
    if _p and os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from chain_check import EmoVoice
import verdict as V

# 台账角色码 → 声纹库角色名。C=Charles，E=Edmund（书里名，电影里对应 Thomas）
ROLE_MAP = {"C": "Charles", "E": "Thomas", "Charles": "Charles", "Thomas": "Thomas",
            "Edmund": "Thomas", "Hooper": "Thomas"}

# 声纹闸门阈值 —— 按 59 条成品实测标定（out/gate_probe.json），不是拍脑袋：
#   role_gap（目标角色 z − 另一角色 z）在真值上分离很干净：
#     判对组 中位 +0.76 / p10 −0.11 / min −0.32
#     判错组 中位 −0.77 / max +0.39
#   扫阈值结果（精度 = 放行样本中判对的比例）：
#     >=0.0 → 44 放行 95% | >=0.3 → 38 放行 95% | >=0.4 → 32 放行 **100%**
#   取 0.4 作 PASS 线：宁可 46% 进人工，也不让串人的混进交付。
# 下界 −0.4：判对组 min 只有 −0.32，取 −0.4 不会误杀；低于它的是「明确判成另一人」。
GAP_PASS = 0.4
GAP_REGEN = -0.4
# z1 只作提示不作判据：成品 z1 中位 1.50、p75 1.81，用建库线 1.8 会拦掉 75%。
# 建库要「纯净」所以严；验收要「少误杀」所以只看相对优势（role_gap）。
Z_NOTE = 1.0

# 绝对下限：目标角色的最高 z 连背景均值都不到，说明「领先」只是两个都很差的模板
# 在互相比较，相对优势没有意义。实测 L064（真错，判成 Charles）z_target = −0.02，
# role_gap 却是 +0.41 的 PASS 值 —— 单看 gap 拦不住，必须补这一条。
Z_TARGET_MIN = 0.0

# 情绪判据的 P25 / P10 从 ref_stats.json 现读，不写死
TIER = {"到位": "p25", "勉强": "p10"}

# 只有这四类有稳定判据；紧张有 0.25 数学硬顶、平静判据退化（V 测的是能量）
STABLE = {"兴奋", "激动反抗", "委屈", "警惕"}
HARD_CAP = {"兴奋": 0.32}   # 生成层 D≈A 导致 A(1−D) 上限；紧张 2026-11-20 起不再测强度

# 低唤醒情绪：声学上「不必更亮、不必更高」，用 arousal p10 卡它们只会逼出更喊的 take。
# 2026-11-20 用户裁定（原话见下面 紧张 分支注释）后，这四类一律走 _calm_gate 韵律闸。
LOW_AROUS_EMO = {"紧张", "警惕", "委屈", "平静"}
# ★ 2026-11-12 加「兴奋」：实测 n=6，p25 0.175 / 中位 0.295 / max 0.312，
#   而参考音 p10 = 0.2470、p25 = 0.3745 —— 生成层 max 连参考音的 p25 都够不到。
#   判 REGEN 等于让人反复重跑一个数学上到不了的目标（c3_0803 0.177 / c3_0942 0.113
#   重生成后字节级无改善就是证据）。改判 MANUAL + hard_cap，交人耳。
#   样本只有 6 条，阈值取实测 max 0.312 上浮一点；将来样本变多要重标。
BIMODAL = {"警惕"}              # 输出双峰，必须 2 seed 取一


def _parse_bg_map(s):
    """'Charles=a.json,Joseph=b.json' 或 '@_bg_map.json' -> {'角色': '背景集'}"""
    s = (s or "").strip()
    if s.startswith("@"):
        try:
            d = json.load(open(s[1:], encoding="utf-8"))
            return {k: v for k, v in d.items() if v} or None
        except Exception as e:
            print("⚠ 读不动 bg-map 文件 %s：%s" % (s[1:], e))
            return None
    out = {}
    for part in s.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k.strip() and v.strip():
            out[k.strip()] = v.strip()
    return out or None


def load_ref_stats():    return json.load(open(P.REF_STATS, encoding="utf-8"))


def audio_stats(path):
    """纯信号指标：不需要模型，毫秒级。"""
    import soundfile as sf
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    if len(x) == 0:
        return {"dur": 0.0, "rms_db": -99.0, "peak": 0.0, "silent": 1.0, "tail_db": 0.0}
    peak = float(np.abs(x).max())
    rms = float(np.sqrt((x ** 2).mean()) + 1e-9)
    # 10ms 帧判静音（-45dBFS 以下）
    w = max(1, int(0.01 * sr))
    n = len(x) // w
    if n:
        fr = np.array([np.sqrt((x[i * w:(i + 1) * w] ** 2).mean()) for i in range(n)])
        silent = float((fr < 10 ** (-45 / 20)).mean())
    else:
        silent = 1.0
    # 结尾 50ms 相对语音主体掉多少 dB（旧判据，保留兼容）
    tail_n = max(1, int(0.05 * sr))
    body = x[:-tail_n] if len(x) > tail_n else x
    body_rms = float(np.sqrt((body ** 2).mean()) + 1e-9)
    tail_rms = float(np.sqrt((x[-tail_n:] ** 2).mean()) + 1e-9)

    # ★ 2026-11-11 修：tail_db 不能用来判硬切。
    #   tail_db 是「最后 50ms 的绝对能量」，只要 wav 结尾带一点静音（正常收尾几乎都带），
    #   它必然掉到 −80 dB 以下。45 条候选里 38 条（84%）被判「疑似硬切」，
    #   实测无一条是真截断 —— 这是判据选错，不是素材坏了。
    #   硬切的真实特征是「语音在满幅处被直接掐断」：尾部没有静音、且最后一帧仍是主体音量。
    #   改成两段判：
    #     tail_gap   = 语音结束后还剩多少秒静音（>=0.04s ⇒ 有正常收尾）
    #     tail_ratio = 语音最后 20ms 的 RMS / 主体 RMS（>=0.7 ⇒ 没衰减就被掐）
    _idx = np.where(np.abs(x) > max(body_rms * 0.05, 1e-5))[0]
    if len(_idx):
        _last = int(_idx[-1])
        tail_gap = (len(x) - 1 - _last) / float(sr)
        _seg = x[max(0, _last - int(0.02 * sr)):_last + 1]
        tail_ratio = float(np.sqrt((_seg ** 2).mean()) + 1e-9) / body_rms
    else:
        tail_gap, tail_ratio = 0.0, 0.0

    # ★ 2026-11-24 新增：噪声类指标。此前 G1 只测削波/静音占比/硬切/RMS，
    #   完全没有「底噪」与「段间底噪一致性」，所以 190 条底噪 > −60 dBFS 的成品
    #   一路被judged A 档送到用户耳朵里（用户原话：「这么明显的错误都没排除掉」）。
    #   帧能量用整段 10ms 帧（不是 silent 那种 10ms 窗口），口径与 _noise_stats.py 一致。
    fr_all = fr
    fr_db = 20 * np.log10(np.maximum(fr_all, 1e-12))
    floor_db = float(np.percentile(fr_db, 10))
    snr_db = float(np.percentile(fr_db, 95) - floor_db)

    # 数字零：abs(x)==0 是 PCM 的绝对静音，人声不可能出现；插停顿灌零 / 裁尾都会留下
    z = np.flatnonzero(x == 0.0)
    zero_ms = 0.0
    if len(z):
        _runs = np.split(z, np.flatnonzero(np.diff(z) != 1) + 1)
        zero_ms = float(sum(len(r) / sr * 1000 for r in _runs if len(r) / sr >= 0.010))

    # 段间底噪跨度：200ms 块各自的 p10，取 max−min。听感「忽有忽无」就是这个数大
    # 段间底噪跨度：只比「真静音块」之间的底噪。
    # ★ 2026-11-24 改：原来取所有 200ms 块 p10 的 max−min，正常条也报 38~55 dB
    #   （含语音的块 p10 天然高），等于 100% 误报。改成先筛 p10 < p97−30dB 的静音块，
    #   再比这些块之间的跨度 —— c2_0291 是 −240 与 −70 混着，才会露出来。
    _blk = int(0.2 * sr)
    _jumps = []
    if _blk > 0 and len(x) >= 3 * _blk:
        for i in range(len(x) // _blk):
            seg = x[i * _blk:(i + 1) * _blk]
            m = len(seg) // w
            if m < 5:
                continue
            f2 = np.sqrt((seg[:m * w].reshape(m, w) ** 2).mean(1)) + 1e-12
            _jumps.append(float(np.percentile(20 * np.log10(f2), 10)))
    _p97all = float(np.percentile(fr_db, 97))
    _quiet = [v for v in _jumps if v < _p97all - 30.0]
    floor_jump = float(max(_quiet) - min(_quiet)) if len(_quiet) >= 2 else 0.0

    # 硬切：看最后 2ms 的 RMS 占峰值的比例。
    # ★ 旧判据（tail_gap<0.04 且 tail_ratio>=0.7）误报率极高：c1_0034/c2_0306 这类
    #   收在元音上的正常句，尾部本来就满幅、也没有静音，一律被判「真硬切」。
    #   实测正常条 last2ms ≤1.2%pk，而人为砍尾的样本是 2.6%～3.4% ⇒ 卡 2%。
    _t2 = x[-max(1, int(0.002 * sr)):]
    tail_last_ratio = float(np.sqrt((_t2 ** 2).mean())) / max(peak, 1e-9)

    return {
        "dur": round(len(x) / sr, 2),
        "rms_db": round(20 * np.log10(rms), 1),
        "peak": round(peak, 3),
        "silent": round(silent, 2),
        "tail_db": round(20 * np.log10(tail_rms / body_rms), 1),
        "tail_gap": round(tail_gap, 3),
        "tail_ratio": round(tail_ratio, 2),
        "floor_db": round(floor_db, 1),
        "snr_db": round(snr_db, 1),
        "zero_ms": round(zero_ms, 1),
        "floor_jump": round(floor_jump, 1),
        "tail_last_ratio": round(tail_last_ratio, 4),
    }


def gate_tech(s, strict_floor=False):
    """G1 技术闸门：只看信号，不看语义。硬缺陷 → REGEN；可修项 → 只记提示。

    ★ 2026-11-24：补噪声类判据（底噪 / SNR / 数字零 / 段间底噪跨度 / 硬切升 REGEN）。
    此前这一闸完全没有噪声项，导致「底噪 −33 dBFS、SNR 10.8 dB」的条也能过七闸进 A 档。
    阈值标定见 _noise_stats.json（239 条实测），不是拍数字：
      底噪 p50 −53.8 / p90 −44.0  ⇒ 统一目标 −72，闸卡 −60（留 12 dB 余量）
      SNR   p10  25.7 / p50 34.7  ⇒ 闸卡 25（只拦真正的糊条，8%）
      数字零 40% 的条带，c2_0291 高达 1282 ms ⇒ 闸卡 20 ms
      段间跨度 95% >6 dB ⇒ 默认只记 note（全库未统一前开硬闸会把 95% 判死），
                          --strict-floor 时才判 REGEN
    """
    notes = []
    verdict = "PASS"
    # ★ 2026-11-11 修：短句判 MANUAL，不判 REGEN。
    #   原来 dur<0.9s 直接 REGEN，等于「因为句子短所以判它坏」，重生成一百次也还是短。
    #   239 条对白里 this 触发 49 条（20.5%），全是 "Why?" / "Yes." / "Moths." 这类
    #   一到两个词的应答 —— 它们不是废案，是判据（分位数、F0 统计）在这种时长上不成立。
    #   「测不了」不能当成「测出来是坏的」。
    if s["dur"] < 0.9:
        verdict = "MANUAL"
        notes.append(("too_short", "时长 %.2fs，短于判据下限，声学指标不可测" % s["dur"]))
    if s["peak"] >= 0.999:
        verdict = "REGEN"
        notes.append(("clipped", "峰值 %.3f 已削波" % s["peak"]))
    if s["silent"] > 0.6:
        verdict = "REGEN"
        notes.append(("mostly_silence", "静音占 %.0f%%" % (s["silent"] * 100)))
    # ★ 2026-11-11 修：旧判据 `tail_db < -35` 在 45 条候选上触发 38 条（84%），
    #   因为它是绝对能量，正常收尾的静音也照触发；实测无一条真截断。
    #   改成看「语音结束后还有没有静音」+「收尾那一帧是否还是满幅」。
    # ★ 2026-11-24 改：硬切判据换成「最后 2ms RMS / 峰值」。
    #   旧判据（tail_gap<0.04 且 tail_ratio>=0.7）在阴性对照上误报 2/5 ——
    #   c1_0034（ratio 1.08）和 c2_0306（0.71）都是收在元音上的正常句。
    #   实测正常条 last2ms ≤1.2%pk，人为砍尾 2.6~3.4% ⇒ 卡 2%。
    tlr = s.get("tail_last_ratio")
    if s["dur"] >= 0.9 and tlr is not None and tlr > 0.02:
        verdict = "REGEN"
        notes.append(("hard_cut", "尾部 2ms 仍为 %.1f%% 峰值，波形被直接掐断" % (tlr * 100)))
    if abs(s["rms_db"] + 24) > 8:
        notes.append(("level_off", "RMS %.1f dBFS，偏离全库 −24 有 %.0f dB" % (s["rms_db"], abs(s["rms_db"] + 24))))

    # ★ 2026-11-24 新增噪声判据
    fd = s.get("floor_db")
    if fd is not None and fd > -60.0:
        verdict = "REGEN"
        notes.append(("noise_floor", "底噪 %.1f dBFS（统一目标 −72，闸 −60）" % fd))
    sd = s.get("snr_db")
    if sd is not None and sd < 25.0:
        verdict = "REGEN"
        notes.append(("snr_low", "SNR %.1f dB（<25，人声与底噪分不开）" % sd))
    zm = s.get("zero_ms")
    if zm is not None and zm > 20.0:
        verdict = "REGEN"
        notes.append(("digital_zero", "数字零累计 %.0f ms（人声不可能出现；插停顿灌零/裁尾留下）" % zm))
    fj = s.get("floor_jump")
    if fj is not None and fj > 10.0:
        if strict_floor:
            verdict = "REGEN"
            notes.append(("floor_jump", "段间底噪跨度 %.0f dB（>10，听感忽有忽无）" % fj))
        else:
            notes.append(("floor_jump", "段间底噪跨度 %.0f dB（>10，全库统一后才严判）" % fj))
    return verdict, notes


def _role_centroids(ev):
    """每个角色的音色质心（全部参考的平均 embedding，L2 归一化）。

    为什么需要它
    ------------
    原判法 role_max(r) = 该角色**所有情绪格**里最高的 z。但本库各角色的情绪格
    不对等：Thomas 只有 loud/calm/scold/begging，Charles 只有 excited/angry/soft/neutral，
    而 Joseph/Helena/Fielding 各有 nervous/wronged/wary/defiant。

    于是「Thomas 紧张」这句在 Thomas 侧只能和四个不相干的格比，天然低分；而
    Joseph/Helena/Fielding 恰好有 nervous 格，天然高分 —— **判错的不是音频，是库的覆盖**。
    2026-11-11 实测：239 条里 wrong_speaker 63 条，逐条回查发现 49 条属于这种
    「目标角色没这一格」的假阳性，另外 14 条的质心 gap 只有 0.003–0.199（两男孩之间
    本来就分不开），没有一条是真正跨年龄/跨性别的串人。

    质心法把角色归属降成纯音色问题：情绪不参与角色判定（情绪由 gate_emotion 管），
    这正好符合本文件开头写的「角色/情绪分离」原则。
    """
    c = getattr(ev, "_cent", None)
    if c is not None:
        return c
    roles = {}
    for i, k in enumerate(ev.keys):
        roles.setdefault(k[0], []).append(i)
    c = {}
    for r, idx in roles.items():
        v = ev.mats[idx].mean(0)
        c[r] = v / (np.linalg.norm(v) + 1e-9)
    ev._cent = c
    return c


# 质心 cos gap 阈值 —— 2026-11-11 用 239 条成品标定，不是拍脑袋：
#   gap>=0.05 → 放行 213/239，精度 97.7%
#   gap>=0.10 → 放行 168/239，精度 98.2%
#   gap<0.05  → 判对组 p05 只有 0.036，与判错组（p75 0.058）完全重叠 ⇒ 不可判
# 所以：>=0.10 敢 PASS；0.05–0.10 与 <0.05 一律 MANUAL。
# REGEN 只留一条路：**跨族**（童声 ↔ 成年声）且 gap>=0.10 —— 这种串人是真缺陷，
# 实测 239 条里一条都没有，但阈值留着，换成别的书（角色音色差异大）才有用。
CEN_PASS = 0.10
CEN_WEAK = 0.05
CHILD = {"Charles", "Thomas"}

# ★ 2026-11-11：短句不做声纹判定。
#   实测 63 条 wrong_speaker 里 37 条时长 <1.0s，其中 z_target 常为负值或 0.2 量级
#   —— 0.5s 的 embedding 不足以稳定刻画说话人，cos/z 的差异是噪声不是证据。
#   这和 gate_tech 的 too_short 是同一条原则：「测不了」不等于「测出来是坏的」。
MIN_SPK_DUR = 1.0

# 中文情绪档 ↔ 参考库里的英文档名。用于判断「这条实际用的参考是否对得上标签」：
#   对不上 = 该角色没有这一档，只能用替代档生成，情绪未被验证（不是生成失败）。
EMO2EN = {
    "激动反抗": {"loud", "defiant", "angry", "scold"},
    "平静": {"calm", "neutral", "normal"},
    "紧张": {"nervous", "panic",
             # ★ 2026-11-24 用户定调：紧张档取消，全部走平静。
             #   生成用 calm/neutral/normal/wary 都是**刻意**的，不是缺档替代。
             #   加上这些键，fallback 才会算 False，台账不会把它记成「缺档」。
             "calm", "neutral", "normal", "wary"},
    "警惕": {"wary"},
    "委屈": {"soft", "wronged", "begging"},
    "兴奋": {"excited"},
}


def _fam(role):
    return "child" if role in CHILD else "adult"


def gate_speaker(ev, wav, who, identify=False, role_blind=(), weak_guard=True,
                 no_conflict=False, mode="centroid", dur=None):
    """G2 声纹闸门：1-NN + Z-norm 判角色归属，按 role_gap 三档。

    role_blind：只做情绪参考、不参与角色归属的情绪档（soft）。见 chain_check.check()。

    identify=True（剪辑场景：不知道说话人是谁）：只报候选与倾向，不判对错。
    无真值时无法验证结论，而且错误是系统性偏向而非随机噪声 —— 实测 59 条里
    判错的 10 条有 8 条被同一个 Charles/soft 档吸走，|role_z| 分布也随之偏低
    （低 |gap| 几乎全是 Thomas）。所以这一档只给「明确 / 倾向 / 模糊」提示，
    不输出 PASS/REGEN 结论，避免用假置信度骗人。
    """
    if not who and not identify:
        return None, "PASS", []
    # 短句：embedding 不稳，不下角色结论
    if dur is not None and dur < MIN_SPK_DUR and not identify:
        return None, "MANUAL", [("spk_short",
                                 "时长 %.2fs < %.1fs，声纹 embedding 不稳，不判角色"
                                 % (dur, MIN_SPK_DUR))]
    target = ROLE_MAP.get(who, who) if who else None
    r = ev.check(wav, role_blind=role_blind)
    notes = []

    if identify or not target:
        rz = abs(float(r["role_z"]))
        r["z_target"] = r["z_other"] = None
        r["role_gap"] = round(rz, 2)
        lvl = "明确" if rz >= GAP_PASS else ("倾向" if rz >= 0.2 else "模糊")
        notes.append(("identify", "候选 %s/%s（z %.2f），跨角色差 %.2f → %s%s" % (
            r["role"], r["emo"], r["z1"], rz, lvl,
            "" if r.get("emo_top") == r.get("emo") else
            "；按情绪看是 %s(%.2f)（该档不参与角色判定）" % (r.get("emo_top"), r.get("z_emo", 0)))))
        if r["z1"] < Z_NOTE:
            notes.append(("low_z", "最高 z 仅 %.2f，音色偏离所有模板，可能是库外的人" % r["z1"]))
        return r, ("PASS" if rz >= GAP_PASS and r["z1"] >= Z_NOTE else "MANUAL"), notes
    if mode == "centroid" and target:
        cent = _role_centroids(ev)
        e = ev.m.embed(wav)
        e = e / (np.linalg.norm(e) + 1e-9)
        cos = {rr: float(cent[rr] @ e) for rr in cent}
        order = sorted(cos.items(), key=lambda x: -x[1])
        top, c1 = order[0]
        gap = c1 - order[1][1] if len(order) > 1 else 0.0
        r.update({"cen_top": top, "cen_gap": round(gap, 3),
                  "cen_cos": {k: round(v, 3) for k, v in cos.items()}})
        if top != target and gap >= CEN_PASS and _fam(top) != _fam(target):
            notes.append(("wrong_speaker",
                          "质心判为 %s（gap %.3f，跨族 %s→%s）" % (
                              top, gap, _fam(target), _fam(top))))
            return r, "REGEN", notes
        if top != target and gap >= CEN_PASS:
            notes.append(("role_ambiguous",
                          "质心更像 %s（gap %.3f），但同族童声差异小于噪声，交人耳" % (top, gap)))
            return r, "MANUAL", notes
        if gap < CEN_WEAK:
            notes.append(("role_unmeasurable",
                          "质心 gap 仅 %.3f（<%.2f），两角色音色分不开，不判" % (gap, CEN_WEAK)))
            return r, "MANUAL", notes
        return r, "PASS", notes

    zr = r.get("z_role") or r["z_all"]     # 角色视角：已剔除 soft（分离模式）
    z_target = max((v for k, v in zr.items() if k.startswith(target + "/")), default=-9)
    z_other = max((v for k, v in zr.items() if not k.startswith(target + "/")), default=-9)
    r["z_target"] = round(float(z_target), 2)
    r["z_other"] = round(float(z_other), 2)
    r["role_gap"] = round(float(z_target - z_other), 2)

    gap = r["role_gap"]

    # 两个视角打架：情绪视角（含 soft）的 top1 是 soft、且指向另一个角色，
    # 而角色视角（剔 soft）给出另一个结论。实测两类都出现过：
    #   L063（真 Charles）全库最像 Charles/soft（z 2.07），剔掉 soft 后 Thomas 靠
    #        0.56 的相对优势胜出 → 这条会被错放成 PASS；
    #   L045（真 Charles）同样最像 Charles/soft，剔掉后 Thomas 领先 1.35
    #        → 这条会被错杀成 REGEN，白跑一条本来正确的音频。
    # 既然是我们主动把最强证据（soft）从判定里拿掉的，就没有资格下明确结论：
    # 冲突一律收进 MANUAL，既不 PASS 也不 REGEN。
    if (role_blind and not no_conflict
            and r.get("role_top") != r["role"] and r.get("emo_top") in role_blind):
        notes.append(("view_conflict", "情绪视角最像 %s/%s（z %.2f），角色视角判 %s 且 gap %+.2f"
                                       " —— 两视角互斥，交人耳" % (
                                           r["role_top"], r["emo_top"], r.get("z_emo", 0),
                                           r["role"], gap)))
        if r["z1"] < Z_NOTE:
            notes.append(("low_z", "最高 z 仅 %.2f，音色偏离所有模板" % r["z1"]))
        return r, "MANUAL", notes

    if gap < GAP_REGEN:
        verdict = "REGEN"
        notes.append(("wrong_speaker", "gap %+.2f < %+.1f：判成 %s（目标 %s）" % (
            gap, GAP_REGEN, r["role"], target)))
    elif gap < GAP_PASS:
        verdict = "MANUAL"
        notes.append(("role_ambiguous", "gap %+.2f 在 [%+.1f, %+.1f) 之间，两个角色分不开，需人耳" % (
            gap, GAP_REGEN, GAP_PASS)))
    elif weak_guard and r["z_target"] <= Z_TARGET_MIN:
        # 相对优势成立、但绝对水平不如背景均值 —— 这是「矮子里拔将军」，
        # 实测这一档里确实混着错判（L064：z_target −0.02 却 gap +0.41）。
        verdict = "MANUAL"
        notes.append(("weak_target", "gap %+.2f 但目标角色最高 z %.2f ≤ %.1f，"
                                     "绝对水平不如背景均值，相对优势不可信" % (
                                         gap, r["z_target"], Z_TARGET_MIN)))
    else:
        verdict = "PASS"

    if r["z1"] < Z_NOTE:
        notes.append(("low_z", "最高 z 仅 %.2f，音色偏离所有模板" % r["z1"]))
    return r, verdict, notes


# ★ 2026-11-13 00:10：**生成层数学上限**，换任何参考素材都推不动，不是缺素材。
#   Thomas/兴奋：a_x_v 实测上限旧档 0.32 / 换新参考 0.18，参考 p25 = 0.3745。
#   机制是 D≈A ⇒ A(1−D) ≤ 0.25，属于模型能力边界。
#   判成 ref_fallback（缺档）会让人一直去找素材，白费 —— 单独给 emo_unreachable。
EMO_UNREACHABLE = {
    ("Thomas", "兴奋"): "该档历史命中率极低（6 条样本 max 0.312，换参考实测 0.180 更差）；"
                        "但 2026-11-13 实测 c2_0491 = 0.555 已达标 ⇒ 只有实测未达的条目才判不可达",
}


def gate_emotion(wav, emo, stats, vox, e2v=None, ref_emo=None, dur=None, who=None):
    """G3 情绪闸门：按六类定档表逐类判。

    ref_emo：这条实际使用的参考档（英文，取自 spk.emo）。
    ★ 2026-11-11：若该角色在参考库里没有这一档（如 Thomas 没有 wary/excited、
      Charles 没有 nervous），生成时只能用替代档，音频的声学特征本来就不是目标情绪
      —— 这时候判 emo_low 是把「素材库缺档」误记成「生成失败」，会让人无谓重跑。
      实测 239 条里 55 条（23.0%）属此情况，其中 Charles/紧张 26 条、Thomas/警惕 17 条。
      正确处理是交人耳（MANUAL），既不判废也不放行。
    """
    if not emo:
        return None, "PASS", []

    # 短句：情绪的信号值同样不稳（0.5s 里没有足够的语调起伏可测）
    if dur is not None and dur < MIN_SPK_DUR:
        return ({"emo": emo, "note": "时长不足，情绪不可测"},
                "MANUAL",
                [("emo_short", "时长 %.2fs < %.1fs，情绪信号不可测" % (dur, MIN_SPK_DUR))])

    # ★ 2026-11-13 17:30：这里原来是无条件短路 —— 只要 (who, emo) 在 EMO_UNREACHABLE
    #   就直接 MANUAL 返回，**根本不去实测**。于是 Thomas/兴奋 5 条从来没被测过一次，
    #   实测 c2_0491 的 happy = 0.555（p25 = 0.3745，早已达标），c2_0264 才是 0.000。
    #   「整组不可达」是拿 6 条样本的 max 推的，不能覆盖逐条实测。
    #   改为：先测，低于 p10 才标 emo_unreachable（语义＝别在这条上反复重跑）。

    # ★ 2026-11-13 17:35：`ref_fallback` 原来也在这里无条件 return —— 但它只是
    #   「用了替代档，情绪**未验证**」的意思，而不是「情绪一定不对」。
    #   实测反例：Thomas/兴奋 5 条全被判 fallback 从未测过，其中 c2_0491 实测 0.555 早已达标。
    #   改为记标记，测完分再决定：到位→放过（备注替代档），未达→才归缺档。
    fallback = bool(ref_emo and emo in EMO2EN and ref_emo not in EMO2EN[emo])

    if emo == "平静":
        # 判据退化：V 测的是「有能量」，兴奋 ref 的产物 6/6 都能过平静线。
        # 所以这里只报两维数值，不判档 —— 判了就是假结论。
        sc = vox.score(wav) or {}
        A, Vv = sc.get("arousal", 0), sc.get("valence", 0)
        import parselmouth
        snd = parselmouth.Sound(wav).resample(16000)
        f = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=450).selected_array["frequency"]
        f = f[f > 0]
        span = float(np.percentile(f, 90) - np.percentile(f, 10)) if len(f) else 0.0
        return ({"V": round(Vv, 3), "A": round(A, 3), "f0_span": round(span, 1),
                 "note": "平静判据退化，只报值不判档；真人 neutral F0 跨度中位 87Hz"},
                "PASS", [("calm_no_tier", "平静无可靠判据，F0 跨度 %.1fHz（真人中位 87）" % span)])

    if emo in LOW_AROUS_EMO:
        # ★ 2026-11-20 用户当场否决该判据：「这种都能标错，紧张这个情绪判断就有问题吧，
        #   根本不会比普通的更亮，直接替换掉吧」+「不是说喊，是情绪很激动很快的说话，
        #   这是跟紧张完全不同的」。
        #   所以紧张**不再测情绪强度**：低唤醒的「紧张」在声学上既不必更亮也不必更高，
        #   用 arousal p10 卡它只会逼着我们去挑更激动、更亮的 take —— 越修越像喊。
        #   紧张句改走韵律闸（`_calm_gate.py`：吐字语速 / voiced-tilt / 停顿结构）。
        sc = vox.score(wav) or {}
        A, Vv = sc.get("arousal", 0), sc.get("valence", 0)
        return ({"V": round(Vv, 3), "A": round(A, 3),
                 "note": "%s 豁免情绪强度项（用户 2026-11-20 裁定），改走 _calm_gate 韵律闸" % emo},
                "PASS", [("lowarousal_waived",
                          "%s 不判情绪强度（A=%.3f 仅记录），改走韵律闸" % (emo, A))])

    src, key = V.PRIMARY[emo]
    st = stats[emo]["signals"]["%s:%s" % (src, key)]
    pos = st["pos"]
    p25, p10 = pos["p25"], pos["p10"]

    if src == "vox":
        sc = vox.score(wav) or {}
        val = V.vox_feat(sc, key)
        extra = {"A": round(sc.get("arousal", 0), 3), "V": round(sc.get("valence", 0), 3),
                 "D": round(sc.get("dominance", 0), 3)}
    else:
        if e2v is None:
            import ser as S
            e2v = S.E2V(P.EMO2VEC)
        sc = e2v.score(wav) or {}
        val = float(sc.get("厌恶/disgusted", 0.0))
        extra = {"top": sc.get("_top"), "angry": round(float(sc.get("生气/angry", 0)), 3)}

    tier = "到位" if val >= p25 else ("勉强" if val >= p10 else "未达")
    res = {"emo": emo, "signal": key, "value": round(float(val), 4),
           "p25": p25, "p10": p10, "tier": tier, "auc": round(st["auc"], 3), **extra}

    notes = []
    verdict = "PASS"
    if tier == "未达":
        # 用的替代档、且实测未达 ⇒ 这才是「缺档」该有的样子：素材端没档，情绪也上不去。
        if fallback:
            verdict = "MANUAL"
            notes.append(("ref_fallback",
                          "%s 档无可用参考（实际用 %s 替代），实测 %.3f < P10 %.3f ⇒ 确实缺档"
                          % (emo, ref_emo, val, p10)))
        # 紧张撞的是数学顶，不是素材问题。判 REGEN 会让人无谓重跑，
        # 所以降到 MANUAL 并把上限写进原因，别让人再去找素材。
        elif who and (who, emo) in EMO_UNREACHABLE:
            # 实测仍未达才算「不可达」；一旦某条达标就按实测放过（见函数开头注释）。
            verdict = "MANUAL"
            notes.append(("emo_unreachable",
                          "%s/%s 本次实测 %.3f < P10 %.3f；%s"
                          % (who, emo, val, p10, EMO_UNREACHABLE[(who, emo)])))
        elif emo in HARD_CAP:
            verdict = "MANUAL"
            notes.append(("hard_cap", "%s 值 %.3f，生成层上限约 %.2f（D≈A ⇒ A(1−D)≤0.25），"
                                     "不建议再找素材" % (emo, val, HARD_CAP[emo])))
        else:
            verdict = "REGEN"
            notes.append(("emo_low", "%s 值 %.3f < P10 %.3f" % (emo, val, p10)))
    elif tier == "勉强":
        verdict = "MANUAL"
        notes.append(("emo_marginal", "%s 值 %.3f 在 P10–P25 之间，可人工听" % (emo, val)))

    if fallback and tier == "到位":
        # 替代档但实测到位：不算缺档，只留一条备注，别让报表把它记成 C。
        notes.append(("fallback_ok", "%s 无专用参考（用 %s 替代），实测 %.3f ≥ P25 %.3f，情绪到位"
                                     % (emo, ref_emo, val, p25)))

    if emo in BIMODAL:
        notes.append(("bimodal", "%s 输出双峰（同 ref 五个 seed 可 0.906/0.031 两极），"
                                 "单条不合格不代表 ref 错，需 2 seed 取一" % emo))
    return res, verdict, notes


SEV = {"PASS": 0, "MANUAL": 1, "REGEN": 2}
import gate_intra as GI
import gate_scs as GS
import gate_nat as GN
import gate_timbre_seq as TS

WHY = {"too_short", "clipped", "mostly_silence", "wrong_speaker", "intra_switch", "intra_drift", "intra_severe",
      "scs_outlier", "nat_fail", "ref_poor",
       "role_ambiguous", "role_unmeasurable", "emo_low", "emo_marginal",
       "hard_cap", "weak_target", "view_conflict",
       "spk_short", "ref_fallback", "emo_short",
       # ★ 2026-11-13 01:58：这两个码原先不在 WHY 里，被当成「信息性备注」丢进 notes，
       #   于是报表看不到：`emo_unreachable` 5 条（Thomas/兴奋）全部落到 F「待人工」，
       #   本该归 E「生成层不可达」；`tail_abrupt` 2 条的尾音硬切也从未出现在任何清单里。
       #   凡是会改变「处理动作」的码，都必须在 WHY 里。
       "emo_unreachable", "tail_abrupt"}


def decide(*verdicts):
    """三档收敛：取最严重的那个。一个闸门说 REGEN，整条就 REGEN。"""
    return max(verdicts, key=lambda v: SEV[v])


def _voice_emo(voice):
    """`Thomas_calm_1` -> `calm`。取不到就 None。

    ★ 2026-11-11 修：原先 ref_emo 取 `spk["emo"]`，那是**声纹 1-NN 按音色最近**
    找出来的档，跟「这条音频实际是用哪个情绪档生成的」是两件事。实测反例：
    c2_0320 标注「激动反抗」，1-NN 找成 excited；c2_0467 找成 wary；
    c3_0628 找成 wronged ⇒ 82~95 条被判 ref_fallback，全是这个原因。
    正确口径：生成时用的档（plan 的 voice 字段），它才决定「这条是不是用对参考生成的」。
    """
    if not voice:
        return None
    parts = str(voice).rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    head = parts[0]
    return head.split("_", 1)[1] if "_" in head else None


def one(ev, wav, who=None, emo=None, stats=None, vox=None, e2v=None,
        identify=False, role_blind=(), weak_guard=True, no_conflict=False,
        spk_mode="centroid", voice=None, intra=True, scs=True, nat=True,
        seq=True, strict_floor=False):
    tech = audio_stats(wav)
    t_v, t_notes = gate_tech(tech, strict_floor=strict_floor)
    spk, s_v, s_notes = gate_speaker(ev, wav, who, identify=identify,
                                     role_blind=role_blind, weak_guard=weak_guard,
                                     no_conflict=no_conflict, mode=spk_mode,
                                     dur=tech["dur"])
    # 优先用生成时实际使用的档；没给就退回 1-NN 的档（旧行为）
    ref_emo = _voice_emo(voice) or (spk or {}).get("emo")
    e_res, e_v, e_notes = gate_emotion(wav, emo, stats, vox, e2v,
                                       ref_emo=ref_emo,
                                       dur=tech["dur"], who=who)

    notes = t_notes + s_notes + e_notes
    # ★ 2026-11-12 新增第 4 闸：句内音色一致性（gate_intra.py）。NA = 短句测不了，不参与判决。
    i_v, i_info = "NA", None
    if intra:
        try:
            i_v, i_info = GI.check(wav)
        except Exception as e:
            i_v, i_info = "NA", {"code": "intra_unmeasurable", "why": "闸4 执行失败：%s" % e}
        if i_info:
            notes = notes + [(i_info["code"], i_info["why"])]
    # ★ 2026-11-12 新增第 5 闸（档内音色一致性 gate_scs）与第 6 闸（自然度 gate_nat）。
    #   两闸都把「整档一起坏」归因为参考档质量，避免把 79 条噪音当成 79 次独立返工。
    sc_v, sc_info = "NA", None
    if scs:
        try:
            sc_v, sc_info = GS.check(wav)
        except Exception as e:
            sc_v, sc_info = "NA", {"code": "scs_unmeasurable", "why": "闸5 执行失败：%s" % e}
        if sc_info:
            notes = notes + [(sc_info["code"], sc_info["why"])]
    n_v, n_info = "NA", None
    if nat:
        try:
            n_v, n_info = GN.check(wav, tier=voice)
        except Exception as e:
            n_v, n_info = "NA", {"code": "nat_unmeasured", "why": "闸6 执行失败：%s" % e}
        if n_info:
            notes = notes + [(n_info["code"], n_info["why"])]
    # ★ 2026-11-14 新增第 8 维（只报警，**不参与 decide**）：音色突变按物理位置三路。
    #   路2 = 标点停顿后换音区（用户最在意的场景）；路3 = 句内声道形状突变。
    #   路1（条间换档落差）是设计常态（中位 6.4 半音），只记极端值作参考。
    #   理由见 DECISIONS「音色突变要按物理位置分三路测」。
    sq = None
    if seq:
        try:
            sq = TS.check(os.path.basename(wav)[:-4], wav)
        except Exception as e:
            sq = {"level": "ok", "why": "第8维执行失败：%s" % e,
                  "r1": [], "r2": [], "r3": None}
    verdict = decide(*([t_v, s_v, e_v] + ([i_v] if i_v != "NA" else [])
                       + ([sc_v] if sc_v != "NA" else []) + ([n_v] if n_v != "NA" else [])))
    return {
        "wav": os.path.basename(wav), "who": who, "emo": emo,
        "verdict": verdict,
        "gates": {"tech": t_v, "speaker": s_v, "emotion": e_v, "intra": i_v,
                  "scs": sc_v, "nat": n_v},
        "intra": i_info, "scs": sc_info, "nat": n_info,
        "timbre_seq": sq,
        "reasons": [{"code": c, "why": w} for c, w in notes if c in WHY],
        "notes": [{"code": c, "why": w} for c, w in notes if c not in WHY],
        "tech": tech,
        "spk": {k: spk.get(k) for k in ("role", "emo", "ref", "z1", "z2", "margin",
                                        "role_gap", "z_target", "z_other",
                                        "role_top", "emo_top", "ref_emo", "z_emo",
                                        "cen_top", "cen_gap", "cen_cos")} if spk else None,
        "emo_res": e_res,
    }


def main():
    global Z_TARGET_MIN
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--dir")
    ap.add_argument("--plan", help="清单 jsonl：每行 {path, who, emo, id?, text?}，可混多类情绪")
    ap.add_argument("--manifest", help="台账 json：{id: {who, text, emo, ...}}")
    ap.add_argument("--cues", help="cut_cues.py 产出的 cues.json。给了它就直接按它建清单，"
                                   "并且**自动跳过 sfx（音效）和 multi（混人对白）**——"
                                   "这两类本来就不能当素材，判它们只会造出假结论（实测把"
                                   "'(grognements et cris)' 判成了 Thomas/begging z=2.12）")
    ap.add_argument("--include-mixed", action="store_true",
                    help="连 sfx/multi 一起判（只在排查切条质量时用）")
    ap.add_argument("--no-intra", action="store_true",
                    help="关掉第 4 闸（句内音色一致性）")
    ap.add_argument("--no-scs", action="store_true",
                    help="关掉第 5 闸（档内音色一致性）")
    ap.add_argument("--no-nat", action="store_true",
                    help="关掉第 6 闸（自然度下限）")
    ap.add_argument("--no-seq", action="store_true",
                    help="关掉第 8 维（音色突变三路：标点停顿后 / 句内 / 条间）。"
                         "该维只报警不判死，默认开启")
    ap.add_argument("--who")
    ap.add_argument("--emo", choices=list(V.PRIMARY) + ["平静"])
    ap.add_argument("--emo-auto", action="store_true", help="按台账 emo 字段，缺失则跳过情绪闸")
    ap.add_argument("--identify", action="store_true",
                    help="识别模式（剪辑用）：不知道 who 也判归属，只报候选与倾向，不判对错")
    ap.add_argument("--probe", action="store_true", help="只出原始指标不判档（用于标定阈值）")
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int, default=0)
    # 换片/做对照实验要能换库，不能只跑写死的那一套
    ap.add_argument("--lib", default=P.EMO_LIB, help="声纹模板库 json")
    ap.add_argument("--bg", default=P.BG_Z, help="Z-norm 背景集 json")
    ap.add_argument("--bg-map", default="",
                    help="按角色分域的背景集：Charles=bg1.json,Joseph=bg2.json。多片合库时必须给，"
                         "否则一个域的 μ/σ 会把别的片的角色放大（PASS 38→17 就是这么来的）")
    ap.add_argument("--model", default="r34")
    ap.add_argument("--spk-mode", choices=["centroid", "cell"], default="centroid",
                    help="角色归属判法。centroid=角色音色质心（默认，2026-11-11 标定，"
                         "239 条 92.5%% 判对、gap>=0.10 精度 98.2%%）；"
                         "cell=旧法（角色×情绪最好那一格），会被「库缺档」带偏，仅供对照")
    ap.add_argument("--loose-role", action="store_true",
                    help="旧方案 C：角色判定直接删掉 soft 档（Thomas 多放行 8 条，"
                         "但 PASS 精度 94%%）。已被默认的分离模式取代，保留供对照")
    ap.add_argument("--no-split-soft", action="store_true",
                    help="关闭 soft 档角色/情绪分离（回到基线：soft 参与角色归属）。"
                         "分离默认开启——59 条实测 PASS 纯度 100%% 不变、PASS 多 4 条、"
                         "整体准确率 83%%→86%%、Thomas 误判重生成 7→3")
    ap.add_argument("--no-weak-guard", action="store_true",
                    help="关闭「z_target ≤ 0 判 MANUAL」的绝对下限保护（做对照实验用）")
    ap.add_argument("--conflict", action="store_true",
                    help="开启「两视角冲突判 MANUAL」（默认关闭）。实测在 59 条成品上收益为 0、"
                         "成本 1 条 PASS：修好 z 取最大值之后，冲突规则拦不到任何错判（两种口径纯度都是 100%%）")
    ap.add_argument("--z-target-min", type=float, default=Z_TARGET_MIN,
                    help="绝对下限阈值（默认 %.1f）。补过素材的库 z 分布会整体抬高，"
                         "这个线要跟着重标" % Z_TARGET_MIN)
    a = ap.parse_args()

    if not a.wav and not a.dir and not a.plan and not a.cues:
        sys.exit("给 --wav / --dir / --plan / --cues 之一")

    ev = EmoVoice(model=a.model, lib=a.lib, bg=a.bg,
                  exclude_emo={"soft"} if a.loose_role else None,
                  bg_map=_parse_bg_map(a.bg_map))
    role_blind = () if (a.no_split_soft or a.loose_role) else ("soft",)
    Z_TARGET_MIN = a.z_target_min
    print("声纹模板 %d 条（1-NN + Z-norm）%s" % (
        len(ev.keys), "｜角色判定排除 soft（分离模式）" if role_blind else ""), flush=True)
    stats = load_ref_stats()

    items = []
    skipped = []
    if a.cues:
        # 直接从切条产物建清单：省掉「手写 jsonl」这一步，也避免它成为链路上的断点。
        for c in json.load(open(a.cues, encoding="utf-8")):
            p = c.get("path") or ""
            if not os.path.isabs(p):
                p = os.path.join(os.path.dirname(os.path.abspath(a.cues)), os.path.basename(p))
                if not os.path.exists(p):
                    p = c["path"]
            tag = "sfx" if c.get("sfx") else ("multi" if c.get("multi") else None)
            if tag and not a.include_mixed:
                skipped.append({"path": os.path.basename(p), "why": tag, "text": (c.get("text") or "")[:40]})
                continue
            items.append({"path": p, "who": a.who, "emo": a.emo,
                          "mid": "c%03d" % c.get("i", 0), "text": c.get("text")})
    elif a.wav:
        items = [{"path": a.wav, "who": a.who, "emo": a.emo}]
    elif a.plan:
        # 清单驱动：每行 {"path":..., "who":..., "emo":...}
        # 一次能跑多类情绪，不用为每种情绪重启一次（重启要重载模板）
        for line in open(a.plan, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            items.append({"path": d["path"], "who": d.get("who") or a.who,
                          "emo": d.get("emo") or a.emo, "mid": d.get("id"),
                          "voice": d.get("voice"), "text": d.get("text")})
    else:
        man = {}
        if a.manifest:
            man = json.load(open(a.manifest, encoding="utf-8"))
        files = sorted(f for f in os.listdir(a.dir) if f.lower().endswith(".wav"))
        if a.limit:
            files = files[:a.limit]
        for f in files:
            mid = f[:-4]
            m = man.get(mid, {})
            items.append({"path": os.path.join(a.dir, f),
                          "who": a.who or m.get("who"),
                          "emo": a.emo or (m.get("emo") if a.emo_auto else None),
                          "mid": mid, "text": m.get("text")})

    # ★ 2026-11-11 修：--limit 原先只作用于 --dir 分支，--plan / --cues 完全不生效
    #   （实测 `--plan ... --limit 20` 跑了全量 239 条，还覆盖了快照文件）。
    if a.limit:
        items = items[:a.limit]

    vox = None
    if any(it.get("emo") for it in items):
        import ser as S
        print("加载 VAD …", flush=True)
        vox = S.VoxDim()

    if skipped:
        print("跳过 %d 条非素材（sfx 音效 / multi 混人对白）：" % len(skipped))
        for s in skipped:
            print("  %-28s %-6s %s" % (s["path"][:28], s["why"], s["text"]))

    rows = []
    for i, it in enumerate(items):
        emo = it.get("emo")
        if emo and emo not in list(V.PRIMARY) + ["平静"]:
            emo = None                       # 台账里的 "拆句"/"disgusted" 不是标准六类
        r = one(ev, it["path"], it.get("who"), emo, stats, vox,
                identify=a.identify, role_blind=role_blind,
                weak_guard=not a.no_weak_guard, no_conflict=not a.conflict,
                spk_mode=a.spk_mode, voice=it.get("voice"),
                intra=not a.no_intra, scs=not a.no_scs, nat=not a.no_nat,
                seq=not a.no_seq)
        r["id"] = it.get("mid") or it["path"]
        r["voice"] = it.get("voice")
        r["text"] = (it.get("text") or "")[:60]
        rows.append(r)
        if (i + 1) % 10 == 0:
            print("  %d/%d" % (i + 1, len(items)), flush=True)

    if a.probe:
        print("\n=== PROBE 原始指标 ===")
        print("%-6s %-3s %5s %6s %5s %5s %6s %6s %6s %6s %8s" %
              ("id", "who", "dur", "rms", "peak", "sil", "A", "V", "D", "z1", "role_gap"))
        for r in rows:
            s, k = r["tech"], r["spk"]
            print("%-6s %-3s %5.2f %6.1f %5.3f %5.2f %s %s %s %s %s" % (
                r["id"][:6], (r["who"] or "?")[:3], s["dur"], s["rms_db"], s["peak"], s["silent"],
                "  -  " if not r["emo_res"] else "%6.3f" % r["emo_res"].get("A", 0),
                "  -  " if not r["emo_res"] else "%6.3f" % r["emo_res"].get("V", 0),
                "  -  " if not r["emo_res"] else "%6.3f" % r["emo_res"].get("D", 0),
                "%6.2f" % k["z1"] if k else "  -   ",
                "%8.2f" % k["role_gap"] if k else "   -    "))
        # 分布，供阈值标定
        zg = [r["spk"]["role_gap"] for r in rows if r["spk"]]
        z1 = [r["spk"]["z1"] for r in rows if r["spk"]]
        for name, arr in (("role_gap", zg), ("z1", z1)):
            if arr:
                arr = sorted(arr)
                print("\n%s: min %.2f p10 %.2f p25 %.2f 中位 %.2f p75 %.2f max %.2f" % (
                    name, arr[0], np.percentile(arr, 10), np.percentile(arr, 25),
                    np.median(arr), np.percentile(arr, 75), arr[-1]))
        if a.out:
            os.makedirs(os.path.dirname(a.out), exist_ok=True)
            json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("\n写 ->", a.out)
        return

    # 正式输出
    print("\n=== 判定 ===")
    for k, v in collections.Counter(r["verdict"] for r in rows).most_common():
        print("  %-8s %3d  (%2.0f%%)" % (k, v, 100 * v / len(rows)))
    print("\n=== 各闸门判定 ===")
    for g in ("tech", "speaker", "emotion", "intra", "scs", "nat"):
        c = collections.Counter(r["gates"][g] for r in rows)
        print("  %-8s PASS %2d / MANUAL %2d / REGEN %2d" % (
            g, c.get("PASS", 0), c.get("MANUAL", 0), c.get("REGEN", 0)))
    print("\n=== 触发原因 ===")
    for k, v in collections.Counter(f["code"] for r in rows for f in r["reasons"]).most_common():
        print("  %-16s %3d" % (k, v))

    if a.identify:
        print("\n=== 识别结果（无真值，只是候选）===")
        print("%-10s %-8s %-8s %6s %8s %s" % ("id", "候选角色", "情绪档", "z1", "角色差", "倾向"))
        for r in rows:
            s = r["spk"]
            if not s:
                continue
            rz = s["role_gap"]
            lvl = "明确" if rz >= GAP_PASS else ("倾向" if rz >= 0.2 else "模糊")
            print("%-10s %-8s %-8s %6.2f %8.2f %s" % (
                str(r["id"])[:10], s["role"], s["emo"], s["z1"], rz, lvl))
        roles = collections.Counter(r["spk"]["role"] for r in rows if r["spk"])
        print("\n角色分布:", dict(roles))
        rzl = sorted(r["spk"]["role_gap"] for r in rows if r["spk"])
        if rzl:
            print("角色差: p10 %.2f p25 %.2f 中位 %.2f p75 %.2f" % (
                np.percentile(rzl, 10), np.percentile(rzl, 25), np.median(rzl),
                np.percentile(rzl, 75)))
            print("模糊（<0.2）%d 条，需人耳" % sum(1 for x in rzl if x < 0.2))

    print("\n=== 需处理清单 ===")
    for r in rows:
        if r["verdict"] != "PASS":
            why = "; ".join(f["code"] for f in r["reasons"]) or "-"
            print("%-6s %-3s %-6s %-8s %s" % (r["id"][:6], (r["who"] or "?")[:3],
                                              (r["emo"] or "-")[:6], r["verdict"], why))

    if a.out:
        # 坑：--out 只给文件名时 dirname 是 ''，os.makedirs('') 直接 FileNotFoundError，
        # 结果全在 stdout 里但 JSON 写不出来（2026-11-10 踩过）。
        _d = os.path.dirname(a.out)
        if _d:
            os.makedirs(_d, exist_ok=True)
        json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n写 ->", a.out)


if __name__ == "__main__":
    main()
