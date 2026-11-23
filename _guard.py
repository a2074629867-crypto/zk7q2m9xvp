# -*- coding: utf-8 -*-
"""_guard.py —— 回环的三道闸门：音色、音质、韵律。

为什么需要它
------------
2026-10-26 那轮「挑 F0 最高的 take」在没有闸门时采纳了 2 条换人的音频。
2026-10-27 又发现 `rate 0.70` 会把词拖成气声（高频比 +66%）。
「指标好看」和「听起来对」是两回事，中间必须有过关条件。

⚠️ 短句（3~8 s）上的绝对阈值一律不可信，本模块全部走**相对判断**：
   有对照（同 seed 无标签）→ 比差值
   无对照 → 只报告，不判定

三道闸门
--------
1. `audio_guard`   音质：HNR 中位、高频能量比、DNSMOS SIG
2. `spk_guard`     音色：cohort 归一化（T-norm）——裸余弦在 7 s 短句上噪声底 ±0.5，不能用
3. `prosody_guard` 韵律：F0 帧间跳变（cent）、相邻词语速跳变（比值）、F0 跨度

用法
----
    from _guard import audio_guard, spk_guard, prosody_guard
    a = audio_guard("cand.wav", ctl="ctl.wav")     # ctl=同 seed 无标签
    p = prosody_guard("cand.wav", "cand.prom", text)
    s = spk_guard("cand.wav", "delivered.wav", cohort=[...])
"""
import glob
import os
import statistics as S
import sys
import warnings

import numpy as np
import soundfile as sf

warnings.filterwarnings("ignore")
sys.path.insert(0, "G:/_setup")

import _adv_align as A
import _f0_accent as F

try:
    import parselmouth
except Exception:                                    # pragma: no cover
    parselmouth = None

ROOT = "G:/_setup"

# ---------------- 阈值（初版，2026-10-27 用 6 个样本标定，后续按实测调整） ----------------
# 音质：相对同 seed 无标签对照
# ⚠️ 2026-10-27 用 249 对「同文本不同 take」标定（_guard_calib.py）：
#   ΔHNR 中位 0.625 / p90 2.211 / p95 2.851 / max 4.545  dB
#   高频比 中位 1.000 / p90 1.616 / p95 2.388 / max 6.417
#   ΔDNSIG 中位 0.372 / p90 1.054 / p95 1.430 / max 1.859
# 旧值（2.0 / 1.40 / 0.50）全部落在 p90 以内 ⇒ 10~40% 的正常 take 会被误杀。
# 现在：FAIL 线取 p95，WARN 带取 p90（只记录不拦）。
HNR_DROP_DB = 2.85        # p95
HF_RATIO_MAX = 2.39       # p95
DNSIG_DROP = 1.43         # p95
HNR_WARN_DB = 2.21        # p90
HF_WARN_MAX = 1.62        # p90
# ★★ 分母塌陷保护（2026-10-27）：对照的 >4kHz 能量本身接近 0 时，比值是噪声放大。
#   交付版 55 条 hf 分布 p5=0.0018 / p10=0.021 / 中位 0.099；7 条低于 0.01。
#   N0634 s2041 被判 ×3.98，实际候选 1.9% / 对照 0.5% —— 两边都在噪声级。
HF_ABS_MIN = 0.02         # 对照 hf < 2% 时这一项不判
# ★★ 候选侧保护：历史上这一项触发 12 次，**没有一次**是候选绝对高频能量异常
#   （最高 N0723 0.356 而比值仅 1.7），全是「对照偏低」把比值顶上去。
#   候选自身不到 p90（0.29）就谈不上毛刺 ⇒ 只 WARN 不 FAIL。
HF_CAND_MIN = 0.25
DNSIG_WARN = 1.05         # p90

# 音色：cohort 归一化
SPK_MARGIN_MIN = 0.05    # s_same − median(cohort)：同人要明显为正
SPK_Z_MIN = 1.5          # 标准化后的同一判据

# 韵律
F0_JUMP_P95_C = 300.0    # 帧间跳变 p95（cent）>300 ⇒ 音高抖
RATE_JUMP_RATIO_MAX = 1.20  # 语速跳相对对照涨 >20% ⇒ 忽快忽慢（绝对线已验证无效）
F0_SPAN_MAX = 16.0       # 句内 F0 p5–p95 跨度（半音）>16 ⇒ 夸张
F0_SPAN_MIN = 3.0        # <3 ⇒ 平得像念稿


# ---------------- 1. 音质 ----------------

def _hnr_median(wav):
    if parselmouth is None:
        return None
    s = parselmouth.Sound(wav)
    h = s.to_harmonicity_cc(minimum_pitch=60, time_step=F.FRAME)
    v = h.values[0]
    v = v[np.isfinite(v)]
    v = v[v > -100]
    return float(np.median(v)) if v.size else None


def _hf_ratio(wav):
    x, sr = sf.read(wav, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    if len(x) < 512:
        return None
    X = np.abs(np.fft.rfft(x)) ** 2
    fr = np.fft.rfftfreq(len(x), 1.0 / sr)
    return float(X[fr > 4000].sum() / max(X.sum(), 1e-9))


def _dnsmos_sig(wav):
    try:
        import librosa
        from speechmos import dnsmos
        x, sr = sf.read(wav, dtype="float32")
        if x.ndim > 1:
            x = x.mean(1)
        if sr != 16000:
            x = librosa.resample(x, orig_sr=sr, target_sr=16000)
        return float(dnsmos.run(x, 16000)["sig_mos"])
    except Exception:
        return None


def audio_guard(wav, ctl=None):
    """音质闸门。ctl=同 seed 无标签对照；None 时只报告不判定。"""
    m = dict(hnr=_hnr_median(wav), hf=_hf_ratio(wav), dnsig=_dnsmos_sig(wav))
    if not ctl:
        return dict(m, verdict="N/A", why="无对照")
    c = dict(hnr=_hnr_median(ctl), hf=_hf_ratio(ctl), dnsig=_dnsmos_sig(ctl))
    bad, warn = [], []
    if m["hnr"] is not None and c["hnr"] is not None:
        d = c["hnr"] - m["hnr"]
        if d > HNR_DROP_DB:
            bad.append("HNR %.1f→%.1f" % (c["hnr"], m["hnr"]))
        elif d > HNR_WARN_DB:
            warn.append("HNR −%.1fdB" % d)
    if m["hf"] is not None and c["hf"] is not None and c["hf"] >= HF_ABS_MIN:
        r = m["hf"] / c["hf"]
        if r > HF_RATIO_MAX and m["hf"] >= HF_CAND_MIN:
            bad.append("高频比 ×%.1f（候选 %.1f%%）" % (r, m["hf"] * 100))
        elif r > HF_WARN_MAX:
            warn.append("高频比 ×%.1f" % r)
    if m["dnsig"] is not None and c["dnsig"] is not None:
        d = c["dnsig"] - m["dnsig"]
        if d > DNSIG_DROP:
            bad.append("DNSIG −%.2f" % d)
        elif d > DNSIG_WARN:
            warn.append("DNSIG −%.2f" % d)
    return dict(m, ctl=c,
                verdict="FAIL" if bad else ("WARN" if warn else "OK"),
                why="；".join(bad) if bad else ("；".join(warn) if warn else "正常"))


# ---------------- 2. 音色 ----------------

def _emb(wav):
    sys.path.insert(0, "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab")
    import spk_embed as SP
    return SP.embed(wav)


def _cos(a, b):
    n = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / n) if n else 0.0


_COHORT_CACHE = {}


def cohort_pool(exclude_uid=None, limit=14):
    """交付版里抽 N 条做 cohort（同人不同文本的参照分布）。"""
    key = (exclude_uid, limit)
    if key in _COHORT_CACHE:
        return _COHORT_CACHE[key]
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "_mt_pick", "*.wav"))):
        u = os.path.basename(p)[:-4]
        if u == exclude_uid:
            continue
        try:
            out.append(_emb(p))
        except Exception:
            continue
        if len(out) >= limit:
            break
    _COHORT_CACHE[key] = out
    return out


def spk_guard(wav, delivered, exclude_uid=None, cohort=None):
    """音色闸门：cohort 归一化。delivered = 该单元当前交付版（同文本同人）。"""
    try:
        e = _emb(wav)
        d = _emb(delivered)
    except Exception as exc:
        return dict(verdict="N/A", why="声纹失败:%s" % exc)
    pool = cohort if cohort is not None else cohort_pool(exclude_uid)
    if not pool:
        return dict(s_same=_cos(e, d), verdict="N/A", why="无 cohort")
    cs = [_cos(e, c) for c in pool]
    s_same = _cos(e, d)
    med = S.median(cs)
    sd = S.pstdev(cs) if len(cs) > 1 else 0.0
    margin = s_same - med
    z = (s_same - S.mean(cs)) / sd if sd > 1e-6 else 0.0
    bad = margin < SPK_MARGIN_MIN and z < SPK_Z_MIN
    # ⚠️ 2026-10-27：音色**不参与否决**。用户原话「声纹没问题其实」。
    # `_spk_calib.py` 实测：同一条录音切两半，裸余弦最低 0.346；同一人不同句子最低 −0.139。
    # 7 秒级片段上 CAM++ 的噪声底约 ±0.5 ⇒ margin 为负是常态，不能当缺陷。
    # 只记 warn，交给报告标出给人耳复核。
    return dict(s_same=round(s_same, 3), cohort_med=round(med, 3),
                cohort_max=round(max(cs), 3), margin=round(margin, 3),
                z=round(z, 2), warn=bool(bad),
                verdict="WARN" if bad else "OK",
                why=("音色偏低 margin %.3f / z %.2f（仅提示）" % (margin, z))
                if bad else "正常")


# ---------------- 2.5 ASR 词表闸门 ----------------

def word_gate(cand_cws, ctl_cws, adv=None, drop_ratio=0.40, rms_ratio=0.50):
    """转写词表闸门：唯一真正抓到过事故的一道。

    2026-10-26 的 `rate0.6 + pitch9` 把 N0219 的 `nervously` 整个吞掉，
    ASR 转写变成 `They all stood about Kingshaw had red hair.`，about 撑到 1.36 s。
    `_adv_present`（只看音频有没有声）完全拦不住 —— 必须查转写里有没有这个词。

    ⚠️ 2026-10-27 修正：**不能只看 voiced**。voiced 只数有基频的帧，
    气声/耳语段有能量但没基频，会把它误判成「被压没」（与 §20.6 的 ABSENT 误杀同源）。
    现在要求「有声帧塌 + 能量也塌」同时成立才算：
        voiced 比 < drop_ratio  **且**  rms_x 比 < rms_ratio
    """
    bad, soft = [], []
    if not cand_cws:
        return dict(verdict="FAIL", why="无可测内容词", adv_missing=True)
    hit = [c for c in cand_cws if adv and c["key"] == adv.lower()]
    if adv and not hit:
        bad.append("副词吞掉")
    if ctl_cws:
        cm = {c["key"]: c for c in ctl_cws}
        dropped, weak = [], []
        for c in cand_cws:
            o = cm.get(c["key"])
            if not o:
                continue
            rv = (c.get("voiced") or 0) / max(o.get("voiced") or 1e-9, 1e-9)
            rr = (c.get("rms_x") or 0) / max(o.get("rms_x") or 1e-9, 1e-9)
            if rv < drop_ratio and rr < rms_ratio:
                dropped.append("%s 声%.2f/能%.2f" % (c["key"], rv, rr))
            elif rv < drop_ratio:
                weak.append("%s 声%.2f" % (c["key"], rv))
        if dropped:
            bad.append("词被压没：" + "、".join(dropped[:3]))
        elif weak:
            soft.append("有声帧偏少：" + "、".join(weak[:3]))
    why = "；".join(bad) if bad else ("；".join(soft) if soft else "词表完整")
    return dict(verdict="FAIL" if bad else ("WARN" if soft else "OK"),
                adv_missing=bool(adv and not hit), why=why)


# ---------------- 3. 韵律 ----------------

def prosody_guard(wav, prom, text, ctl=None, ctl_prom=None, adv=None):
    """韵律闸门。

    ⚠️ 第一版把「相邻词语速跳 >1.5」当阈值，实测**全部误判**：
    对照组 2.00 / 2.22、交付版 3.00 / 1.75 —— 全都超线。
    英语里重读词与弱读词的音节时长天然差 2~3 倍，那不是缺陷。
    ⇒ 语速跳只能**跟对照比**，不能设绝对线。

    ⚠️ 2026-10-27 第二版修正：算语速跳时**必须排除目标副词所在的相邻对**。
    `<rate, factor=0.70>` 的目的就是让那个词变长，它和左右邻居的比值必然拉大；
    把它算成「忽快忽慢」等于惩罚我们想要的效果（实测 10 条 REJECT 里 5 条是这么误判的）。
    """
    ts, fs, ss, dur = F.track_ex(wav)
    st = 12.0 * np.log2(np.maximum(fs, 1e-6) / max(float(np.median(fs)), 1e-6))
    d = np.diff(st) * 100.0                       # cent
    dt = np.diff(ts)
    jump = d[dt < 0.05]                            # 只算连续帧
    p95 = float(np.percentile(np.abs(jump), 95)) if jump.size else 0.0

    p5, p95f = np.percentile(st, [5, 95])
    span = float(p95f - p5)

    adv_k = (adv or "").lower()

    def _rate_jump(prom_path):
        rows = F.read_prom(prom_path)
        spans = A.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
        tw = A.text_words(text)
        vals, flag = [], []
        for i, w in enumerate(tw):
            if not w["is_word"] or w["key"] in F.FUNC:
                continue
            sp = spans[i]
            if sp["t0"] is None:
                continue
            n = max(1, len([c for c in w["w"] if c.lower() in "aeiouy"]))
            vals.append((sp["t1"] - sp["t0"]) / n)
            flag.append(bool(adv_k) and w["key"] == adv_k)
        ratios = [max(a, b) / max(min(a, b), 1e-6)
                  for k, (a, b) in enumerate(zip(vals, vals[1:]))
                  if a > 1e-6 and b > 1e-6 and not (flag[k] or flag[k + 1])]
        return max(ratios) if ratios else None

    rmax = _rate_jump(prom)
    rctl = _rate_jump(ctl_prom) if (ctl_prom and os.path.exists(ctl_prom)) else None

    bad, soft = [], []
    if p95 > F0_JUMP_P95_C:
        bad.append("F0跳%.0fc" % p95)
    if span > F0_SPAN_MAX:
        bad.append("F0跨度%.1f半音太大" % span)
    if span < F0_SPAN_MIN:
        bad.append("F0跨度%.1f太平" % span)
    # ⚠️ 「语速跳」降为 WARN。理由：绝对阈值已被实测推翻（见上），
    # 相对阈值（+20%）没有标定过零分布，而本轮 10 条 REJECT 里有 4 条靠它，
    # 且排除目标词后数值不变 ⇒ 触发点与我们要改的那个词无关，属噪声级判据。
    # 真正的「词被压没」由 word_gate（声+能双条件）负责，不靠这个。
    if rmax and rctl and rmax > rctl * RATE_JUMP_RATIO_MAX:
        soft.append("语速跳 ×%.0f%%于对照" % (100 * (rmax / rctl - 1)))
    why = "；".join(bad) if bad else ("；".join(soft) if soft else "正常")
    return dict(f0_jump_p95=round(p95, 1), f0_span=round(span, 2),
                rate_jump=round(rmax, 2) if rmax else None,
                rate_jump_ctl=round(rctl, 2) if rctl else None,
                verdict="FAIL" if bad else ("WARN" if soft else "OK"), why=why)


def all_guards(wav, prom, text, ctl=None, delivered=None, exclude_uid=None,
               ctl_prom=None, cand_cws=None, ctl_cws=None, adv=None):
    out = dict(
        audio=audio_guard(wav, ctl),
        prosody=prosody_guard(wav, prom, text, ctl, ctl_prom, adv),
    )
    out["speaker"] = (spk_guard(wav, delivered, exclude_uid) if delivered
                      else dict(verdict="N/A", why="无交付版"))
    if cand_cws is not None:
        out["words"] = word_gate(cand_cws, ctl_cws, adv)
    # ⚠️ speaker 不进 fails：音色只提示不否决（见 spk_guard 注释）
    fails = [k for k in ("audio", "prosody", "words")
             if out[k].get("verdict") == "FAIL"]
    warns = [k for k in ("speaker",) if out[k].get("verdict") == "WARN"]
    out["verdict"] = "FAIL" if fails else "OK"
    out["failed"] = fails
    out["warned"] = warns
    return out


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--prom")
    ap.add_argument("--text")
    ap.add_argument("--ctl", help="同 seed 无标签对照 wav")
    ap.add_argument("--delivered", help="当前交付版 wav")
    ap.add_argument("--uid")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.prom and a.text:
        r = all_guards(a.wav, a.prom, a.text, a.ctl, a.delivered, a.uid)
    else:
        r = dict(audio=audio_guard(a.wav, a.ctl))
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if a.out:
        json.dump(r, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
