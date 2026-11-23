"""_f0_accent.py —— 用 F0 曲线判「该词是否真被重读」

背景：现在的 sps 判据只看时长。用户指出重音应看 F0。实测也证实 wpt 的 prominence
由时长主导（ρ=0.712）、F0 只有 0.271，所以两条路线必须分开算。

核心难点：英语句子有**音高下倾（declination）**，句首天然高。直接比绝对 F0 会让
句首永远"重"。所以每个候选词都要给出两个去趋势版本：

  loc : 该词 F0 峰值 − 前后 ±1.2s 上下文窗内、**排除该词**的 F0 中位（半音）
  lin : 该词 F0 峰值 − 全句 F0 对时间做稳健线性拟合后在该时刻的值（半音）

另附词内起伏 rng（半音）与起音跃升 d_in（词首 − 前 150ms）。

用法：
  G:/Python310/python.exe _f0_accent.py --pb                 # 在最小对立对上验证
  G:/Python310/python.exe _f0_accent.py --units              # 在 30 个待修单元上量
  G:/Python310/python.exe _f0_accent.py --all --out x.json   # 在 55 个双票单元上量
"""
import argparse
import glob
import json
import math
import os
import statistics
import sys

import numpy as np
import parselmouth

sys.path.insert(0, "G:/_setup")
import _adv_align

ROOT = "G:/_setup"
PROM_DIR = os.path.join(ROOT, "_wpt_out")
STATE = os.path.join(ROOT, "_mt_adv_state.json")


def semis(f, ref):
    return 12.0 * math.log2(max(f, 1e-6) / max(ref, 1e-6))


def fix_octaves(f, ref):
    """修倍频跳变：与全句中位相差 ~12 半音整数倍时折回。

    parselmouth 在气声/弱起音上常把 F0 判高一个八度（+12）或两个（+24），
    会让 loc/lin 出现 20~33 半音的假峰（N0476/N0710 就是）。
    """
    out = f.copy()
    for i, x in enumerate(f):
        if x <= 0:
            continue
        best, bd = x, abs(12 * math.log2(x / ref))
        for k in (0.5, 0.25, 2.0, 4.0):
            y = x * k
            d = abs(12 * math.log2(y / ref))
            if d < bd - 0.5:
                best, bd = y, d
        out[i] = best
    return out


def despike(st, win=11, th=6.0):
    """半音域中值滤波去倍频抖动。

    N0634 原曲线在 211/265Hz 之间逐帧翻跳（正好 12 半音），是 parselmouth 在
    气声区的倍频误判。真实音高变化在 50ms（10 帧）尺度上连续，所以用 11 帧窗口
    的中位做参照，偏离 >6 半音的帧直接替换成中位值。丢掉的是抖动，不是真峰。
    """
    n = len(st)
    if n < win:
        return st
    out = st.copy()
    for i in range(n):
        a, b = max(0, i - win // 2), min(n, i + win // 2 + 1)
        m = float(np.median(st[a:b]))
        if abs(st[i] - m) > th:
            out[i] = m
    return out


FRAME = 0.005    # parselmouth 帧步长（秒）——所有时长换算必须用它，别再写 0.01


def speech_dur(ts, gap=0.04, min_seg=3):
    """全句有声时长：把有声帧切成连续段（间隔 ≥gap 断开），累加段长，丢弃 <min_seg 帧的孤立段。

    用途：作为「副词时长份额」的分母。比文件时长干净 —— 不含首尾静音和句间停顿。
    """
    ts = np.asarray(ts, dtype=float)
    if ts.size == 0:
        return 0.0
    segs = np.split(ts, np.where(np.diff(ts) >= gap)[0] + 1)
    return float(sum((s[-1] - s[0] + FRAME) for s in segs if len(s) >= min_seg))


def track_ex(path, floor=60, ceiling=500):
    """同 track，另外返回 parselmouth 的 voicing strength（0~1）与时长。

    strength 用来过滤「有 F0 但周期性很弱」的帧 —— 句尾呼吸、词尾衰减段都在这里。
    """
    snd = parselmouth.Sound(path)
    pit = snd.to_pitch(time_step=0.005, pitch_floor=floor, pitch_ceiling=ceiling)
    t = pit.xs()
    f = pit.selected_array["frequency"]
    s = pit.selected_array["strength"]
    ok = f > 0
    ts, fs, ss = (np.asarray(t)[ok], np.asarray(f)[ok], np.asarray(s)[ok])
    if len(fs) >= 20:
        ref = float(np.median(fs))
        fs = fix_octaves(fs, ref)
        st = np.array([12.0 * math.log2(x / ref) for x in fs])
        st = despike(st)
        fs = ref * np.power(2.0, st / 12.0)
    return ts, fs, ss, snd.duration


def track(path, floor=60, ceiling=500):
    snd = parselmouth.Sound(path)
    pit = snd.to_pitch(time_step=0.005, pitch_floor=floor, pitch_ceiling=ceiling)
    t = pit.xs()
    f = pit.selected_array["frequency"]
    ok = f > 0
    ts, fs = np.asarray(t)[ok], np.asarray(f)[ok]
    if len(fs) >= 20:
        ref = float(np.median(fs))
        fs = fix_octaves(fs, ref)
        st = np.array([12.0 * math.log2(x / ref) for x in fs])
        st = despike(st)
        fs = ref * np.power(2.0, st / 12.0)
    return ts, fs, snd.duration


def robust_line(ts, ys):
    """Huber 式稳健直线：先最小二乘，再剔除残差 >1.5*MAD 的点重拟合 3 轮。"""
    ts, ys = np.asarray(ts, float), np.asarray(ys, float)
    if len(ts) < 20:
        return None
    w = np.ones(len(ts), bool)
    a = b = 0.0
    for _ in range(3):
        if w.sum() < 10:
            break
        a, b = np.polyfit(ts[w], ys[w], 1)
        r = ys - (a * ts + b)
        mad = np.median(np.abs(r[w] - np.median(r[w])))
        if mad < 1e-6:
            break
        w = np.abs(r) <= 1.5 * 1.4826 * mad
    return a, b


def word_feats(ts, fs, ref, t0, t1, ss=None, str_min=0.50):
    """词区间内的 F0 特征（半音，相对全句 F0 中位 ref）。

    ★ 2026-10-26 修：`peak` 原来取词内 max，会被**词尾弱周期段**的单点抬升污染。
    实测 N0627 r6 的 +5.21 全部来自 4.33~4.38 一段 8 帧（0.04s、自相关仅 0.44、
    pyin 判清音）的伪峰；同一段 parselmouth 给 221Hz，被 fix_octaves 折成 110，
    再被 despike 折成 102 —— 三次加工后剩下的数字已经没有物理意义。

    因此 peak 改为 **p75**：需要词内 25% 的帧都抬高才抬得起来，
    0.04s 的孤立尖峰在 60 帧的词里只占 13%，压不动 p75。
    同时给出 `raw_peak`（旧定义）用于对照，别把历史数字直接作废。
    """
    sel = (ts >= t0) & (ts < t1)
    if ss is not None:
        sel = sel & (ss >= str_min)
    if sel.sum() < 3:            # 区间太窄（清辅音起音）时向两侧各扩 60ms
        sel = (ts >= t0 - 0.06) & (ts < t1 + 0.06)
        if ss is not None:
            sel = sel & (ss >= str_min)
    if sel.sum() < 3:
        return None
    f = fs[sel]
    st = np.array([semis(x, ref) for x in f])
    i = int(np.argmax(st))
    return dict(t_peak=float(ts[sel][i]), peak=float(np.percentile(st, 75)),
                raw_peak=float(st[i]),
                med=float(np.median(st)), rng=float(st.max() - st.min()),
                n=int(sel.sum()),
                p90=float(np.percentile(st, 90)))


CTX_MIN_FR = 10


def ctx_res(feat, ts, fs, ref, t0, t1, half=1.2, min_fr=CTX_MIN_FR):
    """loc：峰值 − 上下文窗（排除词本身）中位。

    退化：短句（≤3 实词）或首尾长静音时，±half 窗里凑不够 min_fr 帧有声帧，
    旧版直接返回 None ⇒ 被当成「测不到」，其实是句子里没有可比对象。
    此时把基线换成**整句除去该词**的所有有声帧（句子级音高水平），
    短句里这本来就是正确的参照。仍不足 3 帧才返回 None。"""
    sel = ((ts >= t0 - half) & (ts < t0)) | ((ts > t1) & (ts <= t1 + half))
    if sel.sum() < min_fr:
        sel = (ts < t0) | (ts > t1)
        if sel.sum() < 3:
            return None
    base = statistics.median([semis(x, ref) for x in fs[sel]])
    return feat["peak"] - base


def lin_res(feat, ts, fs, ref):
    """lin：峰值 − 全句稳健线性趋势在该时刻的值。"""
    if len(ts) < 30:
        return None
    st = np.array([semis(x, ref) for x in fs])
    fit = robust_line(ts, st)
    if not fit:
        return None
    a, b = fit
    return feat["peak"] - (a * feat["t_peak"] + b)


def onset_delta(ts, fs, ref, t0, win=0.15):
    """起音跃升：词首 40ms 内 F0 − 前 win 秒中位。"""
    a = (ts >= t0) & (ts < t0 + 0.04)
    b = (ts >= t0 - win) & (ts < t0)
    if a.sum() < 1 or b.sum() < 2:
        return None
    return (statistics.median([semis(x, ref) for x in fs[a]])
            - statistics.median([semis(x, ref) for x in fs[b]]))


def read_prom(p):
    """prom 6 列：文件名 | 起始 | 结束 | 词 | prominence | boundary。"""
    rows = []
    for line in open(p, encoding="utf-8"):
        x = line.rstrip("\n").split("\t")
        if len(x) < 6:
            continue
        try:
            rows.append((float(x[1]), float(x[2]), x[3], float(x[4])))
        except ValueError:
            continue
    return rows


def wav_for_prom(prom_path):
    base = os.path.splitext(os.path.basename(prom_path))[0]
    if "__" not in base:
        return None
    d, uid = base.split("__", 1)
    p = os.path.join(ROOT, d, uid + ".wav")
    return p if os.path.exists(p) else None


def analyse_prom(prom_path, target=None, wav=None, text=None):
    """返回该句每个词的 F0 特征列表；target 给词形时只返回匹配词。

    text 给了就用「原文↔ASR 对齐」的区间（能处理 ASR 合并词），否则退回 prom 行。
    """
    wav = wav or wav_for_prom(prom_path)
    if not wav:
        return []
    ts, fs, dur = track(wav)
    if len(fs) < 20:
        return []
    ref = float(np.median(fs))
    rows = read_prom(prom_path)
    if text:
        spans = _adv_align.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
        tw = _adv_align.text_words(text)
        out = []
        for i, x in enumerate(tw):
            if not x["is_word"]:
                continue
            sp = spans[i]
            if sp["t0"] is None:
                continue
            feat = word_feats(ts, fs, ref, sp["t0"], sp["t1"])
            if not feat:
                continue
            feat.update(word=x["w"], t0=sp["t0"], t1=sp["t1"], prom=0.0,
                        ref=round(ref, 1), synthetic=sp["synthetic"],
                        loc=ctx_res(feat, ts, fs, ref, sp["t0"], sp["t1"]),
                        lin=lin_res(feat, ts, fs, ref),
                        d_in=onset_delta(ts, fs, ref, sp["t0"]))
            out.append(feat)
        if target:
            return [x for x in out
                    if x["word"].lower().strip(".,;:!?'\"—-–()[]") == target.lower()]
        return out
    out = []
    for t0, t1, w, prom in rows:
        if not w.strip(".,;:!?'\"—-–()[]"):
            continue
        feat = word_feats(ts, fs, ref, t0, t1)
        if not feat:
            continue
        feat.update(word=w, t0=t0, t1=t1, prom=prom, ref=round(ref, 1),
                    loc=ctx_res(feat, ts, fs, ref, t0, t1),
                    lin=lin_res(feat, ts, fs, ref),
                    d_in=onset_delta(ts, fs, ref, t0))
        out.append(feat)
    if target:
        hit = [x for x in out if x["word"].lower().strip(".,;:!?") == target.lower()]
        return hit
    return out


FUNC = set("""a an the and or but nor so yet for if because as than that this these those
i you he she it we they me him her us them my your his its our their am is are was were be
been do does did have has had will would can could may might must to of in on at by with
from into about once too then not no up down out off over under again there here all any
some each every other another such what which who whom whose when where why how""".split())


def content_only(ws):
    return [w for w in ws if w["word"].lower().strip(".,;:!?'\"—-–()[]") not in FUNC]


def target_rank(words, target, key="loc"):
    """目标词在句内内容词里的分位（0=最轻 1=最重）与名次。"""
    cs = [w for w in content_only(words) if w.get(key) is not None]
    if len(cs) < 3:
        return None
    cs.sort(key=lambda w: w[key])
    t = target.lower()
    idx = [i for i, w in enumerate(cs)
           if w["word"].lower().strip(".,;:!?'\"—-–()[]") == t]
    if not idx:
        return None
    i = idx[-1]
    return dict(pct=round(i / (len(cs) - 1), 3), rank=len(cs) - i, n=len(cs))


# ---------------- 最小对立对验证 ----------------

def pb_nuclei(path):
    """音节核：强度峰，去抖，返回 [(时刻, 强度)]。"""
    snd = parselmouth.Sound(path)
    inten = snd.to_intensity(minimum_pitch=50, time_step=0.005)
    v = inten.values[0]
    t0, dt = inten.x1, inten.dx
    v = np.where(np.isfinite(v), v, -np.inf)
    peaks = []
    for i in range(2, len(v) - 2):
        if v[i] >= v[i - 1] and v[i] >= v[i + 1] and v[i] > np.max(v) * 0.55:
            peaks.append((t0 + i * dt, float(v[i])))
    keep = []
    for t, val in peaks:
        if keep and t - keep[-1][0] < 0.08:
            if val > keep[-1][1]:
                keep[-1] = (t, val)
            continue
        keep.append((t, val))
    return keep, snd.duration


PB_TXT = {1: "GREENHOUSE", 2: "WHITEBOARD", 3: "BULLSEYE", 4: "BLACKBIRD",
          5: "BULLSEYE", 6: "BLACKBIRD", 7: "DARKROOM", 8: "WETSUIT",
          9: "DARKROOM", 10: "WHITEBOARD", 11: "HOTDOG", 12: "WETSUIT",
          13: "GREENHOUSE", 14: "BLUEBELL", 15: "HOTDOG", 16: "BLUEBELL"}
# 主重音在复合词前半=1，短语后半=2
PB_EXPECT = {1: 1, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2, 7: 1, 8: 1, 9: 2, 10: 2,
             11: 1, 12: 2, 13: 2, 14: 1, 15: 2, 16: 2}


def cmd_pb(a):
    dirs = sorted(glob.glob(os.path.join(ROOT, "_pb", "el*")))
    if not dirs:
        raise SystemExit("no _pb/el* dirs")
    allrows = []
    for d in dirs:
        files = sorted(glob.glob(os.path.join(d, "*_trial_*.wav")),
                       key=lambda p: int(p.rsplit("_", 1)[1].split(".")[0]))
        if not files:
            continue
        stat = {"loc": 0, "lin": 0, "med": 0, "d_in": 0, "f0abs": 0}
        n = 0
        detail = []
        for f in files:
            i = int(f.rsplit("_", 1)[1].split(".")[0])
            if i not in PB_EXPECT:
                continue
            ns, dur = pb_nuclei(f)
            if len(ns) < 2:
                continue
            ts, fs, _ = track(f)
            if len(fs) < 20:
                continue
            ref = float(np.median(fs))
            h = len(ns) // 2
            feats = {}
            for tag, part in (("head", ns[:h]), ("tail", ns[h:])):
                best = None
                for t, _v in part:
                    feat = word_feats(ts, fs, ref, t - 0.04, t + 0.12)
                    if not feat:
                        continue
                    feat["loc"] = ctx_res(feat, ts, fs, ref, feat["t_peak"] - 0.10,
                                          feat["t_peak"] + 0.16, half=0.8)
                    feat["lin"] = lin_res(feat, ts, fs, ref)
                    feat["d_in"] = onset_delta(ts, fs, ref, feat["t_peak"] - 0.02)
                    feat["f0abs"] = feat["peak"]
                    if best is None or feat["peak"] > best["peak"]:
                        best = feat
                feats[tag] = best
            if not feats.get("head") or not feats.get("tail"):
                continue
            n += 1
            exp = PB_EXPECT[i]
            for k in stat:
                hv, tv = feats["head"].get(k), feats["tail"].get(k)
                if hv is None or tv is None:
                    continue
                got = 1 if hv > tv else 2
                stat[k] += (got == exp)
            detail.append(dict(trial=i, expect=exp, head=feats["head"]["peak"],
                               tail=feats["tail"]["peak"]))
        if n:
            print("== %s  n=%d" % (os.path.basename(d) or "303", n))
            for k in ("loc", "lin", "med", "d_in", "f0abs"):
                print("   %-6s %2d/%2d = %.3f" % (k, stat[k], n, stat[k] / n))
        allrows.append(dict(speaker=os.path.basename(d) or "303", n=n, stat=stat))
    tot = {}
    N = 0
    for r in allrows:
        N += r["n"]
        for k, v in r["stat"].items():
            tot[k] = tot.get(k, 0) + v
    print("\n=== 合计 n=%d ===" % N)
    for k, v in sorted(tot.items(), key=lambda z: -z[1]):
        print("  %-6s %3d/%d = %.3f" % (k, v, N, v / N))
    if a.out:
        json.dump(allrows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---------------- 副词单元测量 ----------------

def cmd_units(a):
    st = json.load(open(STATE, encoding="utf-8"))
    units = st["units"]
    if a.only_bad:
        pick = {u: x for u, x in units.items()
                if x.get("verdict") in ("FLAT", "WEAK", "MISSING")}
    else:
        pick = units
    rows = []
    for uid, x in sorted(pick.items()):
        prom, seed = None, None
        for f in os.listdir(PROM_DIR):
            if f.endswith(".prom") and f.endswith("__" + uid + ".prom"):
                prom = os.path.join(PROM_DIR, f)
                seed = f.split("__")[0].replace("_mt_raw_s", "")
                break
        if not prom:
            rows.append(dict(uid=uid, adv=x["adv"], sps=x.get("sps"),
                             verdict=x.get("verdict"), f0=None))
            continue
        hits = analyse_prom(prom, x["adv"])
        best = None
        if hits:
            best = max(hits, key=lambda h: (h["loc"] if h["loc"] is not None else -9))
        rows.append(dict(uid=uid, adv=x["adv"], seed=seed, sps=x.get("sps"),
                         verdict=x.get("verdict"),
                         f0=None if not best else dict(
                             loc=round(best["loc"], 2) if best["loc"] is not None else None,
                             lin=round(best["lin"], 2) if best["lin"] is not None else None,
                             med=round(best["med"], 2), rng=round(best["rng"], 2),
                             d_in=round(best["d_in"], 2) if best["d_in"] is not None else None,
                             peak=round(best["peak"], 2))))
    print("%-8s %-13s %-6s %-7s %-7s %-7s %-6s %s"
          % ("uid", "adv", "sps", "sps判", "F0loc", "F0lin", "rng", "F0判"))
    n_acc = 0
    for r in rows:
        f = r["f0"]
        if not f:
            print("%-8s %-13s %-6s %-7s  —" % (r["uid"], r["adv"], r["sps"], r["verdict"]))
            continue
        acc = (f["loc"] is not None and f["loc"] >= a.th) or \
              (f["lin"] is not None and f["lin"] >= a.th)
        n_acc += acc
        print("%-8s %-13s %-6s %-7s %-7s %-7s %-6s %s"
              % (r["uid"], r["adv"], r["sps"], r["verdict"],
                 f["loc"], f["lin"], f["rng"], "ACCENT" if acc else "flat"))
    print("\nF0 判为重读: %d / %d（阈值 %.1f 半音）" % (n_acc, len(rows), a.th))
    if a.out:
        json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def cmd_rank(a):
    """目标词在句内内容词中的 F0 分位（这才是「有没有被重读」的正确问法）。"""
    st = json.load(open(STATE, encoding="utf-8"))
    units = st["units"]
    pick = {u: x for u, x in units.items()
            if (not a.only_bad) or x.get("verdict") in ("FLAT", "WEAK", "MISSING")}
    prom_by_uid = {}
    for f in os.listdir(PROM_DIR):
        if f.endswith(".prom") and "__" in f:
            u = f[:-5].split("__", 1)[1]
            prom_by_uid.setdefault(u, []).append(os.path.join(PROM_DIR, f))
    rows = []
    for uid, x in sorted(pick.items()):
        cands = prom_by_uid.get(uid) or []
        if not cands:
            continue
        allw = analyse_prom(sorted(cands)[0])
        if not allw:
            continue
        rk = target_rank(allw, x["adv"])
        if not rk:
            continue
        rows.append(dict(uid=uid, adv=x["adv"], sps=x.get("sps"),
                         verdict=x.get("verdict"), **rk))
    pcts = sorted(r["pct"] for r in rows)
    print("%-8s %-13s %-6s %-7s %-6s %-6s %s"
          % ("uid", "adv", "sps", "sps判", "名次", "分位", "内容词数"))
    for r in sorted(rows, key=lambda z: -z["pct"]):
        print("%-8s %-13s %-6s %-7s %-6s %-6s %d"
              % (r["uid"], r["adv"], r["sps"], r["verdict"],
                 "%d" % r["rank"], "%.2f" % r["pct"], r["n"]))
    n = len(pcts)
    if n:
        print("\n=== 目标词 F0 分位（n=%d）===" % n)
        for f in (0, .1, .25, .5, .75, .9):
            print("  p%-4d %.2f" % (int(f * 100), pcts[min(n - 1, int(f * (n - 1)))]))
        print("  中位 %.2f   均匀分布基线 0.50" % statistics.median(pcts))
        top3 = sum(1 for r in rows if r["rank"] <= 3)
        hi = sum(1 for r in rows if r["pct"] >= 0.65)
        print("  名次≤3: %d/%d = %.1f%%   分位≥0.65: %d/%d = %.1f%%"
              % (top3, n, 100.0 * top3 / n, hi, n, 100.0 * hi / n))
        # 单侧符号检验（分位 > 0.5 的条数 vs 二项 0.5）
        k = sum(1 for p in pcts if p > 0.5)
        pv = sum(math.comb(n, i) for i in range(k, n + 1)) / (2 ** n)
        print("  分位>0.5 的 %d/%d = %.1f%%，单侧二项 p=%.3f" % (k, n, 100.0 * k / n, pv))
    if a.out:
        json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pb", action="store_true")
    ap.add_argument("--units", action="store_true")
    ap.add_argument("--rank", action="store_true")
    ap.add_argument("--only-bad", action="store_true", default=True)
    ap.add_argument("--all", dest="only_bad", action="store_false")
    ap.add_argument("--th", type=float, default=2.5, help="F0 重读阈值（半音）")
    ap.add_argument("--prom", default=None, help="单条：prom 路径")
    ap.add_argument("--word", default=None, help="单条：目标词")
    ap.add_argument("--wav", default=None, help="单条：wav 路径（默认从 prom 名反推）")
    ap.add_argument("--text", default=None, help="单条：原文（用对齐区间，能处理 ASR 合并词）")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.prom and a.word:
        allw = analyse_prom(a.prom, wav=a.wav, text=a.text)
        rk = target_rank(allw, a.word)
        hit = [x for x in allw
               if x["word"].lower().strip(".,;:!?'\"—-–()[]") == a.word.lower()]
        best = max(hit, key=lambda h: h["loc"] if h["loc"] is not None else -9) if hit else None
        out = dict(prom=a.prom, word=a.word, rank=rk,
                   loc=None if not best else round(best["loc"], 2),
                   lin=None if not best else (round(best["lin"], 2) if best["lin"] is not None else None),
                   med=None if not best else round(best["med"], 2),
                   rng=None if not best else round(best["rng"], 2),
                   n_words=len(allw))
        print(json.dumps(out, ensure_ascii=False))
        return
    if a.pb:
        cmd_pb(a)
    elif a.units:
        cmd_units(a)
    elif a.rank:
        cmd_rank(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
