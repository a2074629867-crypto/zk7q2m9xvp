# -*- coding: utf-8 -*-
"""自然度下限闸门（nat_guard）。

指标：NISQA-MOS / NISQA-DIS / NISQA-COL + torchaudio SQUIM-SUBJ 的 z 均值。
标定依据（2026-10-27，`_nat_deg/` 合成已知坏样本 + 真 take 池）：

  合成退化 AUC（5 好 vs 8 类退化 × 5）
      NISQA-MOS 0.84 ｜ SQUIM 0.81 ｜ 组合 **0.90** ｜ DNSMOS 0.61
  分工
      NISQA 抓剪切/削波/低通/等响：chop 1.00 flatamp 1.00 lowpass 0.96 hole 0.92
      SQUIM 抓纯韵律：mono 1.00 jitter 0.96（NISQA 对 mono 只有 0.84）
      重复三连 stutter 全模型失效（0.56）→ 只能靠 ASR word_gate
  真数据（n=37 OK / 7 audio-FAIL，bootstrap 95% CI）
      NISQA-MOS 0.49 [0.28,0.69]  DIS 0.48 [0.29,0.69]  COL 0.54 [0.31,0.76]
      SQUIM 0.76 [0.53,0.93]  DNSMOS 0.78 [0.61,0.92]
      组合(原始) 0.70 [0.45,0.90]  组合(全段残差) 0.56 [0.34,0.77]
      ⇒ **全部覆盖 0.5，真数据上一个都分不开**；且 7 条 audio-FAIL 的标签
         本身来自差值闸门（p95 ⇒ 5% 假阳性），ground truth 不可靠。
      ⇒ 选型只能靠合成 known-answer；真数据只用于确认「不会乱报」。
      ⇒ **只能当「明显不行」的下限筛，不能排序、不能选最优 take**
      阈值 −2.3（残差噪声 p95 = 2.15）

★ 评测前必须剪掉我们插入的逗号/句号停顿（>220ms），否则 NISQA-DIS
  测到的是停顿占比：N0824「He said stiffly,」2.40s 里 1.18s 是插入停顿，
  DIS 1.87；剪完回到 3.45，全库最差 6 条换了 4 条。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")

STAT = "G:/_setup/_nat_stat.json"
STAT_DLG = "G:/_setup/_nat_stat_dlg.json"   # ★ 对白专属（2026-11-12 23:50）
CACHE = "G:/_setup/_nat_cache.json"
KEYS = ["nq_mos", "nq_dis", "nq_col", "squim"]
NAT_FAIL = -2.3          # ★ 残差阈值：换-take 残差噪声 p95 = 2.15
NAT_WARN = -1.4          # 残差 p90 = 1.60
# 对白专属阈值（_nat_stat_dlg.json 标定，锚集 134 条）：
#   -2.0σ → 锚集误报 3.0%，r5 已知坏音频抓出 71.4%，新音频保住 100%
NAT_FAIL_DLG = -2.0
NAT_WARN_DLG = -1.2
SP_MIN = 0.90            # 语音短于 0.9s 不做自然度判断（长度污染压不住）
SP_REG = 1.20            # ★ 只有语音 <1.2s 才扣长度效应；更长的句子上回归会吃掉真缺陷


def _cache():
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    return {}


def _save(c):
    json.dump(c, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)


def _key(p):
    import hashlib
    h = hashlib.md5(open(p, "rb").read()).hexdigest()[:12]
    return "%s|%s" % (os.path.basename(p), h)


def raw(wav, ref=None):
    """剪停顿后算四项原始分 + 语音时长。模型分按文件 md5 缓存。"""
    import _nat_screen as S
    c = _cache()
    k = _key(wav)
    d = tempfile.mkdtemp(prefix="ng_")
    try:
        tw = S.trim_silence(wav, os.path.join(d, "w.wav"))
        x, sr = sf.read(tw, dtype="float32", always_2d=True)
        sp = len(x) / float(sr)
        base = dict(c.get(k) or {})
        if "nq_mos" in base and "squim" in base:
            base["sp"] = sp
            return base
        tr = S.trim_silence(ref, os.path.join(d, "r.wav")) if ref else tw
        out = {}
        n = S.nisqa_batch([tw])
        if tw in n:
            out.update({("nq_" + kk): v for kk, v in n[tw].items()})
        out["squim"] = S.squim_mos(tw, tr)
        out["sp"] = sp
    finally:
        shutil.rmtree(d, ignore_errors=True)
    c[k] = out
    _save(c)
    return out


def build_ref(wavs):
    """建参照：四项均值/标准差 + **自然度对 ln(语音时长) 的回归**。

    ★ 语音时长与自然度分 r = 0.58（55 条交付版）。不回归掉长度，
      3 词短句（0.33s 语音）会被判成「明显不行」——N0824 就是这么误报的。
    """
    rows = [raw(w) for w in wavs]
    st = {}
    for k in KEYS:
        v = [r[k] for r in rows if r.get(k) is not None]
        st[k] = dict(mean=float(np.mean(v)), sd=float(np.std(v)), n=len(v))

    def _ens(sc):
        zs = [(sc[k] - st[k]["mean"]) / max(st[k]["sd"], 1e-9)
              for k in KEYS if sc.get(k) is not None]
        return float(np.mean(zs)) if zs else None

    xs, ys = [], []
    for r in rows:
        e = _ens(r)
        if e is None or r.get("sp", 0) < 0.2:
            continue
        xs.append(np.log(r["sp"]))
        ys.append(e)
    b, a = np.polyfit(np.array(xs), np.array(ys), 1)
    st["_reg"] = dict(a=float(a), b=float(b),
                      r=float(np.corrcoef(xs, ys)[0, 1]), n=len(xs))
    json.dump(st, open(STAT, "w", encoding="utf-8"), indent=1)
    return st


def _center(st, k):
    """兼容两种标定口径：旁白用 mean，对白用 median（med）。"""
    return st[k]["med"] if "med" in st[k] else st[k]["mean"]


def _keys(stat):
    """对白标定里带 _meta.keys（已按判别力筛过），旁白没有就退回 KEYS。"""
    return (stat.get("_meta") or {}).get("keys") or KEYS


def ens(sc, stat=None):
    stat = stat or load_stat()
    zs = []
    for k in _keys(stat):
        v = sc.get(k)
        if v is None or k not in stat:
            continue
        zs.append((v - _center(stat, k)) / max(stat[k]["sd"], 1e-9))
    return float(np.mean(zs)) if zs else None


def residual(sc, stat=None):
    stat = stat or load_stat()
    e = ens(sc, stat)
    if e is None:
        return None, None
    reg = stat.get("_reg") or dict(a=0.0, b=0.0)
    sp = max(sc.get("sp") or 0.0, 0.05)
    res = e - (reg["a"] + reg["b"] * np.log(sp))
    return e, res


def load_stat(domain="narr"):
    """domain: narr（旁白，默认） / dlg（对白专属）。"""
    p = STAT_DLG if domain == "dlg" else STAT
    return json.load(open(p, encoding="utf-8"))


def score_raw(sc, stat=None, domain="narr"):
    """从**已有测量**判自然度，不再跑模型。

    ★ 2026-11-12 23:55：口径换成对白专属后，239 条缓存里的 raw 还能用，
      只是判决要按新参照重算。不必重跑 NISQA（每条 1~2s，239 条要 6 分钟）。
    """
    stat = stat or load_stat(domain)
    if domain == "dlg":
        fail, warn = NAT_FAIL_DLG, NAT_WARN_DLG
    else:
        fail, warn = NAT_FAIL, NAT_WARN
    e, res = residual(sc, stat)
    if e is None:
        return dict(ens=None, res=None, verdict="UNKNOWN", why="无测量")
    sp = sc.get("sp") or 0.0
    if sp < SP_MIN:
        return dict(ens=round(e, 2), res=round(res, 2), score=None,
                    axis="none", verdict="UNKNOWN",
                    why="语音仅 %.2fs，短于 %.1fs 判不出" % (sp, SP_MIN), raw=sc)
    # ★★ 长度回归只在短端应用（2026-10-27 二次标定）
    #   全段回归会把「本来就短」当解释项，连真缺陷一起扣掉：
    #   audio-FAIL 语音中位 1.10s vs OK 2.04s ⇒ 真数据 AUC 从 0.70 掉到 0.56。
    #   sp ≥ SP_REG 时长度污染可忽略（那个 r=0.58 主要由短端撑起来），用原始 z 均值。
    use_res = sp < SP_REG
    score = res if use_res else e
    tag = "残差" if use_res else "原始"
    if score < fail:
        v, why = "FAIL", "%s %.2fσ（低于下限 %.1f）" % (tag, score, fail)
    elif score < warn:
        v, why = "WARN", "%s %.2fσ 偏低" % (tag, score)
    else:
        v, why = "OK", "%s %+.2fσ" % (tag, score)
    return dict(ens=round(e, 2), res=round(res, 2), score=round(score, 2),
                axis=("res" if use_res else "raw"), verdict=v, why=why, raw=sc,
                domain=domain, fail_thr=fail, warn_thr=warn)


def verdict(wav, ref=None, stat=None, domain="narr"):
    sc = raw(wav, ref)
    return score_raw(sc, stat=stat, domain=domain)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-ref", action="store_true", help="用 _mt_pick/*.wav 建参照分布")
    ap.add_argument("--units", default=None, help="逗号分隔的单元，检查 _mt_pick")
    ap.add_argument("--wavs", default=None)
    ap.add_argument("--apply", action="store_true", help="把结果写进 _mt_adv_state.json 的 nat 字段")
    a = ap.parse_args()

    if a.build_ref:
        ws = sorted("G:/_setup/_mt_pick/%s" % f
                    for f in os.listdir("G:/_setup/_mt_pick") if f.endswith(".wav"))
        st = build_ref(ws)
        print("参照集 %d 条" % len(ws))
        for k, v in st.items():
            print("  %-8s mean %.3f sd %.3f" % (k, v["mean"], v["sd"]))
        return

    if a.units:
        ws = ["G:/_setup/_mt_pick/%s.wav" % u.strip() for u in a.units.split(",")]
    elif a.wavs:
        ws = [w.strip() for w in a.wavs.split(",")]
    else:
        ap.error("需要 --units 或 --wavs")

    stat = load_stat()
    res = {}
    for w in ws:
        if not os.path.exists(w):
            continue
        d = verdict(w, stat=stat)
        res[os.path.basename(w)[:-4]] = d
        print("%-8s %-7s ens %+5.2f res %+5.2f  %-26s" % (
            os.path.basename(w)[:-4], d["verdict"], d["ens"] or 0,
            d.get("res") or 0, d["why"]))
    if a.apply:
        p = "G:/_setup/_mt_adv_state.json"
        s = json.load(open(p, encoding="utf-8"))
        for u, d in res.items():
            if u in s.get("units", {}):
                s["units"][u]["nat"] = d["ens"]
                s["units"][u]["nat_res"] = d.get("res")
                s["units"][u]["nat_score"] = d.get("score")
                s["units"][u]["nat_axis"] = d.get("axis")
                s["units"][u]["nat_sp"] = round((d.get("raw") or {}).get("sp") or 0, 2)
                s["units"][u]["nat_verdict"] = d["verdict"]
        json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("已写回 state（%d 条）" % len(res))


if __name__ == "__main__":
    main()
