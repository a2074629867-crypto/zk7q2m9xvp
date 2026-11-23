# -*- coding: utf-8 -*-
"""_adv_prom.py —— 副词「放慢 / 重读」的**无分位判据**。

## 为什么推倒重来

前两版判据都死在同一个错误上：拿一个**分布内的分位**当及格线。

    sps 0.28     → 落在 55 条样本的第 56 百分位 ⇒ 数学上注定 56% 不及格
    F0 分位 0.65 → 同样是分位；句子里只有 3 个内容词时 rank2/3=0.50 直接判死

用户抽听了 4 条被判「不合格」的（N0807 / N0542 / N0142 / N0063），**全部说没问题**。
所以问题不在 ASR（对齐已能拆合并词），而在于判据没有物理锚点。

## 本版：只比物理量

  loc    = 该词 F0 峰 − 前后 ±1.2s 上下文（排除自身）F0 中位（半音）
  sps    = 词时长 / 音节数（秒/音节）
  dur_z  = log(sps) 相对「同音节数应有的 sps」的偏离（σ 数）
           —— 基线用全库内容词做 log-log 回归，消掉**多音节压缩**

为什么必须有 dur_z：副词几乎都是 -ly 多音节词，同句邻居多是单音节，
而多音节词每音节本来就短。实测把副词直接和邻居比，全库比值中位只有 0.73
—— 「比邻居慢」这个标准对副词天生不公平，会把读得完全正常的
N0063 solemnly（0.667 倍）判成「太快」。

物理门槛（有听觉意义，不随样本变）：
  loc   ≥ 2.0 半音  ≈ 一个可听的音高重音（语音 JND 约 1~2 半音）
  dur_z ≥ +1.0 σ    ≈ 明显长于同音节数词的常态
  margin = max(loc/2.0, dur_z/1.0) ≥ 1 即「至少一条通道达到可听的门槛」

## 判定

  ABSENT    voiced < 0.06s              根本没出声
  SWALLOW   rms_x<0.35 且 dur_z<-1.0    出声但被压没、还读快了
  STRONG    margin ≥ 1.00               至少一条通道过门槛
  MID       0.65 ≤ margin < 1.00        有倾向但不够硬
  FLAT      margin < 0.65               两条通道都没动静

另外做**配对对照**（副词 vs 同句其它内容词），用来回答
「这批配音到底有没有对副词做重读」这个母问题——单看副词绝对值回答不了。
"""
import argparse
import json
import math
import os
import statistics
import sys
from collections import Counter

import numpy as np
import parselmouth

sys.path.insert(0, "G:/_setup")
import _adv_align
import _adv_check as AC
import _f0_accent as F

ROOT = "G:/_setup"
STATE = os.path.join(ROOT, "_mt_adv_state.json")
PROM_DIR = os.path.join(ROOT, "_wpt_out")
REGEN = [(2025, "_mt_adv_s2025", "_mt_adv_prom_2025"),
         (2027, "_mt_adv_s2027", "_mt_adv_prom_2027"),
         (2029, "_mt_adv_s2029", "_mt_adv_prom_2029")]

LOC_MARGIN = 2.0     # 半音
DUR_Z_MARGIN = 1.0   # σ


# ---------------- 单句特征 ----------------

def content_words(text, spans, ts, fs, ref, it, iv, dur, ss=None, speech=None):
    """原文每个实词的物理特征（每句只跑一次 F0/强度，不再一词一进程）。"""
    tw = _adv_align.text_words(text)
    out = []
    for i, x in enumerate(tw):
        if not x["is_word"] or x["key"] in F.FUNC:
            continue
        sp = spans[i]
        if sp["t0"] is None:
            continue
        t0, t1 = sp["t0"], sp["t1"]
        fe = F.word_feats(ts, fs, ref, t0, t1, ss=ss)
        if not fe:
            continue
        seg = iv[(it >= t0) & (it < t1)]
        whole = iv[(it >= 0) & (it < dur)]
        r = 10 ** (np.median(seg) / 20.0) if len(seg) else 0.0
        b = 10 ** (np.median(whole) / 20.0) if len(whole) else 1e-9
        out.append(dict(
            w=x["w"], key=x["key"], t0=t0, t1=t1,
            nsyl=max(1, AC.syllables(x["w"])),
            sps=(t1 - t0) / max(1, AC.syllables(x["w"])),
            loc=F.ctx_res(fe, ts, fs, ref, t0, t1),
            lin=F.lin_res(fe, ts, fs, ref),
            peak=fe["peak"], raw_peak=fe.get("raw_peak"),
            p90=fe.get("p90"), n_fr=fe["n"],
            voiced=round(float(((ts >= t0) & (ts < t1)).sum()) * F.FRAME, 3),
            speech=round(speech, 3),
            share=round(float(((ts >= t0) & (ts < t1)).sum()) * F.FRAME / max(speech, 1e-9), 4),
            rms_x=float(r / max(b, 1e-9)),
            synthetic=bool(sp["synthetic"])))
    return out


def measure_one(wav, prom, text, strict=False):
    """strict=True 时用 pitch strength 过滤弱周期帧（词尾呼吸/衰减段）。"""
    if strict:
        ts, fs, ss, dur = F.track_ex(wav)
    else:
        ts, fs, dur = F.track(wav)
        ss = None
    if len(fs) < 20:
        return None
    ref = float(np.median(fs))
    snd = parselmouth.Sound(wav)
    inten = snd.to_intensity(minimum_pitch=60, time_step=0.01)
    it, iv = inten.xs(), inten.values[0]
    iv = np.where(np.isfinite(iv), iv, 0.0)
    rows = F.read_prom(prom)
    spans = _adv_align.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    speech = F.speech_dur(ts)
    return content_words(text, spans, ts, fs, ref, it, iv, dur, ss=ss, speech=speech)


# ---------------- 音节-时长基线 ----------------

def fit_baseline(allc):
    pts = [(w["nsyl"], w["sps"]) for w in allc if w["sps"] > 0]
    if len(pts) < 50:
        return None
    x = np.log([p[0] for p in pts])
    y = np.log([p[1] for p in pts])
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    mad = float(np.median(np.abs(resid - np.median(resid))))
    return dict(a=float(a), b=float(b), sd=max(1.4826 * mad, 0.08),
                n=len(pts), r=float(np.corrcoef(x, y)[0, 1]))


def z_dur(w, base):
    if not base or w["sps"] <= 0:
        return None
    pred = base["a"] + base["b"] * math.log(max(1, w["nsyl"]))
    return (math.log(w["sps"]) - pred) / base["sd"]


BASE_FILE = os.path.join(ROOT, "_adv_baseline.json")


def save_baseline(base):
    if base:
        json.dump(base, open(BASE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def load_baseline():
    try:
        return json.load(open(BASE_FILE, encoding="utf-8"))
    except Exception:
        return None


# ---------------- 判定 ----------------

def target_row(cws, adv, base):
    hit = [w for w in cws if w["key"] == AC.norm(adv)]
    if not hit:
        return None
    t = hit[-1]
    others = [w for w in cws if w is not t]
    if not others:
        return None
    mid = (t["t0"] + t["t1"]) / 2.0
    nb = sorted(others, key=lambda w: abs((w["t0"] + w["t1"]) / 2.0 - mid))[:4]
    locs = [w["loc"] for w in others if w["loc"] is not None]
    # ★ 2026-10-27：补 rel / rel_z（口径见 _align_lib）——
    #   rel 分母 = **句内全部内容词** sps 中位（含自身），与真人锚点一致；
    #   rel_z 以 rel 为底、用真人拟合系数校正音节数。dur_x 保留但不再作判据。
    _all = [w["sps"] for w in cws if w.get("sps")]
    _rel = (t["sps"] / max(statistics.median(_all), 1e-6)) if _all else None
    try:
        import _align_lib as _AL
        _bl = _AL.load_baseline()
        _rz = _AL.rel_z_value(_rel, t["nsyl"], _bl)
    except Exception:
        _rz = None
    return dict(
        adv=adv, nsyl=t["nsyl"], sps=round(t["sps"], 3),
        dur_z=None if z_dur(t, base) is None else round(z_dur(t, base), 2),
        dur_x=round(t["sps"] / max(statistics.median(w["sps"] for w in others), 1e-6), 3),
        dur_nb=round(t["sps"] / max(statistics.median(w["sps"] for w in nb), 1e-6), 3),
        rel=None if _rel is None else round(_rel, 3),
        rel_z=None if _rz is None else round(_rz, 2),
        loc=None if t["loc"] is None else round(t["loc"], 2),
        lin=None if t["lin"] is None else round(t["lin"], 2),
        voiced=t["voiced"], speech=t.get("speech"), share=t.get("share"),
        rms_x=round(t["rms_x"], 2),
        synthetic=t["synthetic"], n_content=len(cws),
        ref_loc=None if not locs else round(statistics.median(locs), 2))


def verdict(r):
    if r["voiced"] < 0.06:
        return "ABSENT", 0.0
    dz = r.get("dur_z")
    if r["rms_x"] < 0.35 and (dz is None or dz < -1.0):
        return "SWALLOW", 0.0
    m = max((r.get("loc") or 0.0) / LOC_MARGIN, (dz or 0.0) / DUR_Z_MARGIN)
    m = round(m, 2)
    return ("STRONG" if m >= 1.0 else "MID" if m >= 0.65 else "FLAT"), m


# ---------------- 取音源 ----------------

def unit_sets(which):
    """(uid, wav, prom, seed_tag)。原版散在 s1234 / s42 / srate 里，s1234 优先。"""
    out = []
    if which in ("orig", "both"):
        cand = {}
        for f in sorted(os.listdir(PROM_DIR)):
            if not (f.endswith(".prom") and "__" in f):
                continue
            pre, uid = f[:-5].split("__", 1)
            if not pre.startswith("_mt_raw_s"):
                continue
            wav = os.path.join(ROOT, pre, uid + ".wav")
            if not os.path.exists(wav):
                continue
            rank = 0 if pre.endswith("s1234") else 1
            if uid not in cand or rank < cand[uid][0]:
                cand[uid] = (rank, wav, os.path.join(PROM_DIR, f),
                             pre.replace("_mt_raw_s", ""))
        for uid, v in cand.items():
            out.append((uid, v[1], v[2], v[3]))
    if which in ("regen", "both"):
        for seed, wd, pd in REGEN:
            if not os.path.isdir(wd):
                continue
            for f in sorted(os.listdir(wd)):
                if f.endswith(".wav"):
                    p = os.path.join(pd, f[:-4] + ".prom")
                    if os.path.exists(p):
                        out.append((f[:-4], os.path.join(wd, f), p, str(seed)))
    return out


# ---------------- 主流程 ----------------

def measure_manifest(items):
    """items = [{uid, text, wav, prom, advs}] → 逐条测量记录（供回环批量调用）。"""
    cws_all, mid = [], []
    for it in items:
        uid = str(it["uid"])
        advs = it.get("advs") or [it.get("adv") or ""]
        cws = measure_one(it["wav"], it["prom"], it["text"])
        if not cws:
            mid.append(dict(uid=uid, advs=advs, verdict="NO_AUDIO", margin=0.0))
            continue
        cws_all += [dict(uid=uid, **w) for w in cws]
        mid.append(dict(uid=uid, advs=advs, cws=cws))
    base = fit_baseline(cws_all) or load_baseline()
    rows = []
    for r in mid:
        if r.get("verdict") == "NO_AUDIO":
            rows.append(r)
            continue
        t = target_row(r["cws"], r["advs"][-1], base)
        if t is None:
            rows.append(dict(uid=r["uid"], advs=r["advs"], verdict="UNMEASURED", margin=0.0))
            continue
        rec = dict(uid=r["uid"], advs=r["advs"], **t)
        rec["verdict"], rec["margin"] = verdict(rec)
        rows.append(rec)
    return rows


def cmd_batch(a):
    man = json.load(open(a.batch, encoding="utf-8"))
    items = man if isinstance(man, list) else man.get("items", [])
    rows = measure_manifest(items)
    if a.out:
        json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for r in rows:
        print("%-8s %-13s %-5s loc=%-6s dur_z=%-6s %s"
              % (r["uid"], (r.get("adv") or (r.get("advs") or [""])[-1])[:13],
                 r["verdict"], r.get("loc"), r.get("dur_z"), r.get("margin")))
    print("batch %d 条" % len(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="orig", choices=["orig", "regen", "both"])
    ap.add_argument("--batch", default=None, help="清单 json：[{uid,text,wav,prom,advs}]")
    ap.add_argument("--out", default="_adv_prom.json")
    ap.add_argument("--show", type=int, default=20)
    a = ap.parse_args()
    if a.batch:
        return cmd_batch(a)

    st = json.load(open(STATE, encoding="utf-8"))["units"]
    raws, allc = [], []
    for uid, wav, prom, tag in unit_sets(a.set):
        if uid not in st:
            continue
        x = st[uid]
        advs = x.get("advs") or [x["adv"]]
        cws = measure_one(wav, prom, x["text"])
        if not cws:
            raws.append(dict(uid=uid, advs=advs, set=tag, verdict="NO_AUDIO", margin=0.0))
            continue
        raws.append(dict(uid=uid, advs=advs, set=tag, cws=cws))

    allc = [dict(uid=r["uid"], **w) for r in raws for w in r.get("cws", [])]
    base = fit_baseline(allc)
    save_baseline(base)
    if base:
        print("=== 音节-时长基线（消多音节压缩）===")
        print("  log(sps/秒) = %+.3f %+.3f*log(nsyl)   n=%d  r=%.3f  sd=%.3fσ"
              % (base["a"], base["b"], base["n"], base["r"], base["sd"]))

    rows = []
    for r in raws:
        if r.get("verdict") == "NO_AUDIO":
            rows.append(r)
            continue
        t = target_row(r["cws"], r["advs"][-1], base)
        if t is None:
            rows.append(dict(uid=r["uid"], adv=r["advs"][-1], advs=r["advs"],
                             set=r["set"], verdict="UNMEASURED", margin=0.0))
            continue
        rec = dict(uid=r["uid"], advs=r["advs"], set=r["set"], **t)
        rec["verdict"], rec["margin"] = verdict(rec)
        rows.append(rec)

    print("\n" + "%-8s %-3s %-13s %-5s %-6s %-6s %-6s %-6s %-6s %-6s %s"
          % ("uid", "syl", "adv", "seed", "sps", "dur_z", "dur_nb",
             "loc", "lin", "margin", "判定"))
    for r in sorted(rows, key=lambda z: z["margin"])[:a.show]:
        if r["verdict"] in ("UNMEASURED", "NO_AUDIO"):
            print("%-8s %-3s %-13s %-5s   %s" % (r["uid"], "", r["adv"][:13],
                                                 r["set"], r["verdict"]))
            continue
        print("%-8s %-3d %-13s %-5s %-6s %-6s %-6s %-6s %-6s %-6s %s"
              % (r["uid"], r["nsyl"], r["adv"][:13], r["set"], r["sps"],
                 r["dur_z"], r["dur_nb"], r["loc"], r["lin"],
                 r["margin"], r["verdict"]))
    print("\n判定分布:", dict(Counter(r["verdict"] for r in rows)))

    # ---- 配对对照 ----
    byu = {}
    for w in allc:
        byu.setdefault(w["uid"], []).append(w)
    dzz, dl = [], []
    for r in rows:
        ws = byu.get(r["uid"], [])
        keys = {AC.norm(z) for z in r.get("advs", [])}
        t = [w for w in ws if w["key"] in keys]
        o = [w for w in ws if w["key"] not in keys]
        if not t or not o:
            continue
        a_ = [v for v in (z_dur(w, base) for w in t) if v is not None]
        b_ = [v for v in (z_dur(w, base) for w in o) if v is not None]
        if a_ and b_:
            dzz.append(statistics.median(a_) - statistics.median(b_))
        tl = [w["loc"] for w in t if w["loc"] is not None]
        ol = [w["loc"] for w in o if w["loc"] is not None]
        if tl and ol:
            dl.append(statistics.median(tl) - statistics.median(ol))
    print("\n=== 配对对照（副词 − 同句其它内容词，句级中位）===")
    for name, arr, unit in (("时长 dur_z", dzz, "σ"), ("音高 loc", dl, "半音")):
        if not arr:
            continue
        n = len(arr)
        arr = sorted(arr)
        k = sum(1 for x in arr if x > 0)
        pv = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
        print("  %-10s 中位 %+.2f%s  p25 %+.2f  p75 %+.2f  >0 的 %d/%d，单侧二项 p=%.3f"
              % (name, statistics.median(arr), unit, arr[n // 4], arr[3 * n // 4],
                 k, n, pv))

    json.dump(dict(baseline=base, rows=rows), open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出", a.out)


if __name__ == "__main__":
    main()
