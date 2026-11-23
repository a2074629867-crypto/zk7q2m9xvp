# -*- coding: utf-8 -*-
"""句内起伏合理性（intra-sentence contour）—— 判据全部在句子内部归一化。

为什么重写：之前用整章 IQR 中位数对齐马修（1.94），那是**全局分布**口径，
只能回答「这一章整体起伏偏大」，回答不了「这一句话的起伏合不合理」。
为了让整章中位数下来，把每一条都压平了 —— 方向错了。

本脚本测的是**句内**的四条：
  A 落点   F0 峰值落在句内哪个词上？内容词 / 功能词 / 最长词
  B 突跳   音节间 |ΔF0| 的分布（>3 半音算跳）
  C 断裂   句内停顿前后 F0 是否连续（同一语调短语内应连续）
  D 分布   起伏是集中在少数位置（自然），还是均匀撒满（机械）

马修侧有 whisper 词级时间戳，可精确到词；我们侧没有，用音节核（能量峰）对齐。
"""
import os
import sys
import json
import glob
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- 基础量

def load_wav(p):
    import soundfile as sf
    x, sr = sf.read(p, dtype="float64", always_2d=True)
    return x.mean(1), sr


def st_of(hz, ref):
    """转半音，相对 ref（Hz）。"""
    return 12.0 * np.log2(np.maximum(hz, 1e-6) / max(ref, 1e-6))


def f0_series(x, sr, floor=60.0, ceil=250.0, vt=0.20):
    """返回 (t, f0_hz)，只保留 voiced 帧。"""
    import parselmouth
    snd = parselmouth.Sound(np.asarray(x, dtype=np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceil,
                          voicing_threshold=vt, silence_threshold=0.03)
    f = pit.selected_array["frequency"]
    t = pit.xs()
    m = f > 0
    return t[m], f[m]


def frame_db(x, sr, hop=0.01):
    n = max(1, int(hop * sr))
    nf = len(x) // n
    if nf < 1:
        return np.array([-120.0])
    a = np.asarray(x[: nf * n], dtype=np.float64).reshape(nf, n)
    r = np.sqrt((a ** 2).mean(1) + 1e-20)
    return 20.0 * np.log10(r + 1e-12)


def vad_segs(x, sr, thr_rel=25.0, min_sil=0.10, min_seg=0.06):
    """能量 VAD，返回 [(t0,t1)]。"""
    db = frame_db(x, sr)
    if len(db) < 5:
        return []
    thr = np.percentile(db, 90) - thr_rel
    on = db > thr
    segs, i, n = [], 0, len(on)
    while i < n:
        if not on[i]:
            i += 1
            continue
        j = i
        while j < n and on[j]:
            j += 1
        if (j - i) * 0.01 >= min_seg:
            segs.append((i * 0.01, j * 0.01))
        i = j
    # 合并间隔 < min_sil 的相邻段
    if not segs:
        return []
    out = [segs[0]]
    for a, b in segs[1:]:
        if a - out[-1][1] < min_sil:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


# ---------------------------------------------------------------- 音节核

def syllabic_peaks(x, sr, t0, t1, min_gap=0.055):
    """在 [t0,t1] 内找音节核（能量包络局部峰），返回峰值时间列表。

    音节核 = 元音，是能量最集中的位置。用 10ms 帧的 dB 包络找局部极大，
    再按最小间隔合并（避免把同一个元音的多个小峰算成两个音节）。
    """
    i0, i1 = int(t0 * sr), int(t1 * sr)
    seg = x[i0:i1]
    if len(seg) < int(0.05 * sr):
        return []
    # 20ms 窗做平滑包络（音节级）
    w = max(1, int(0.020 * sr))
    nf = len(seg) // w
    if nf < 3:
        return []
    env = np.sqrt((np.asarray(seg[: nf * w], dtype=np.float64).reshape(nf, w) ** 2).mean(1) + 1e-20)
    db = 20 * np.log10(env + 1e-12)
    # 局部极大：比左右各 2 帧都高，且高于段内 p40
    thr = np.percentile(db, 40)
    peaks = []
    for k in range(2, len(db) - 2):
        if db[k] < thr:
            continue
        if db[k] >= db[k - 1] and db[k] >= db[k + 1] and db[k] >= db[k - 2] and db[k] >= db[k + 2]:
            peaks.append(t0 + (k + 0.5) * w / sr)
    # 最小间隔合并：保留更高者
    merged = []
    for t in peaks:
        if merged and t - merged[-1][0] < min_gap:
            if db[min(len(db) - 1, int((t - t0) * sr / w))] > merged[-1][1]:
                merged[-1] = (t, db[min(len(db) - 1, int((t - t0) * sr / w))])
            continue
        merged.append((t, db[min(len(db) - 1, int((t - t0) * sr / w))]))
    return [t for t, _ in merged]


# ---------------------------------------------------------------- 词对齐

def split_words_by_syllables(text, n_syl_target, boundaries):
    """把 text 的词按音节数比例映射到 boundaries（时间点序列）。

    返回 [(word, t_start, t_end)]。近似：假设每个音节时长相等。
    """
    words = text.split()
    if not words or n_syl_target <= 0 or len(boundaries) < 2:
        return []
    # 粗估每词音节数（元音组）
    def nsyl(w):
        w = "".join(c for c in w.lower() if c.isalpha())
        if not w:
            return 1
        n, prev = 0, False
        for c in w:
            v = c in "aeiouy"
            if v and not prev:
                n += 1
            prev = v
        return max(1, n)
    syl = [nsyl(w) for w in words]
    tot = sum(syl)
    if tot <= 0:
        return []
    t0, t1 = boundaries[0], boundaries[-1]
    span = t1 - t0
    out, acc = [], 0.0
    for w, s in zip(words, syl):
        a = t0 + span * acc / tot
        acc += s
        b = t0 + span * acc / tot
        out.append((w, a, b))
    return out


FUNC = set("""a an the and or but nor for so yet of to in on at by with from into onto
about over under between among through during before after above below up down out off
is am are was were be been being do does did have has had will would shall should can
could may might must this that these those it its he she they them his her their our your
my me him us i you we as if than then there here not no""".split())


def is_func(w):
    c = "".join(ch for ch in w.lower() if ch.isalpha())
    return c in FUNC


# ---------------------------------------------------------------- 单句特征

def feats_of_sentence(t_f0, f0_hz, text, segs, word_bounds=None):
    """一句的句内起伏特征。

    t_f0 / f0_hz : 该句内所有 voiced 帧（秒，Hz）
    segs         : 该句的 VAD 段 [(t0,t1)]（句内小停顿就是段间隙）
    word_bounds  : 可选，[(word,t0,t1)]；没有就按音节核估
    """
    if len(f0_hz) < 10:
        return None
    med = float(np.median(f0_hz))
    st = st_of(f0_hz, med)          # 句内归一：中位为 0
    r = dict(n_frame=int(len(f0_hz)), f0_med_hz=round(med, 1))

    # --- 幅度（描述用，不判）
    r["iqr_st"] = round(float(np.percentile(st, 75) - np.percentile(st, 25)), 2)
    r["p90_st"] = round(float(np.percentile(st, 90)), 2)
    r["p10_st"] = round(float(np.percentile(st, 10)), 2)

    # --- B 突跳：按 100ms 窗取中位后再看相邻差（去掉帧级抖动）
    w = 0.10
    t0, t1 = float(t_f0[0]), float(t_f0[-1])
    if t1 - t0 < 2 * w:
        r["jump_max_st"] = 0.0
        r["jump_p90_st"] = 0.0
        r["jump_rate"] = 0.0
    else:
        edges = np.arange(t0, t1 + 1e-9, w)
        sm = []
        for a in edges[:-1]:
            m = (t_f0 >= a) & (t_f0 < a + w)
            if m.sum() >= 3:
                sm.append(float(np.median(st[m])))
        sm = np.array(sm)
        if len(sm) >= 3:
            d = np.abs(np.diff(sm))
            r["jump_max_st"] = round(float(d.max()), 2)
            r["jump_p90_st"] = round(float(np.percentile(d, 90)), 2)
            r["jump_rate"] = round(float((d > 3.0).mean()), 3)
        else:
            r["jump_max_st"] = r["jump_p90_st"] = r["jump_rate"] = 0.0

    # --- A 落点：峰值位置
    k = int(np.argmax(st))
    tp = float(t_f0[k])
    r["peak_t"] = round(tp, 3)
    r["peak_st"] = round(float(st[k]), 2)
    dur = max(1e-6, t1 - t0)
    r["peak_pos"] = round((tp - t0) / dur, 3)

    words = text.split()
    r["n_word"] = len(words)
    if word_bounds:
        # 峰落在哪个词
        hit = None
        for wd, a, b in word_bounds:
            if a - 0.02 <= tp <= b + 0.02:
                hit = (wd, a, b)
                break
        if hit is None:
            # 找最近的词
            best, bd = None, 1e9
            for wd, a, b in word_bounds:
                d = min(abs(tp - a), abs(tp - b))
                if d < bd:
                    best, bd = (wd, a, b), d
            hit = best
        if hit:
            wd, a, b = hit
            r["peak_word"] = wd
            r["peak_word_func"] = bool(is_func(wd))
            # 该词是不是句内最长（按字母数）
            lens = [len("".join(c for c in x if c.isalpha())) for x in words]
            if lens:
                longest = max(lens)
                cur = len("".join(c for c in wd if c.isalpha()))
                r["peak_word_is_longest"] = bool(cur >= longest - 1 and longest > 2)
                r["peak_word_len_rank"] = round(
                    float(sum(1 for L in lens if L > cur)) / max(1, len(lens)), 3)
            # 峰值词的位置（句内第几个词 / 总词数）
            idx = next((i for i, x in enumerate(words)
                        if x.strip(".,;:!?\"'") == wd.strip(".,;:!?\"'")), None)
            r["peak_word_idx_frac"] = round(idx / max(1, len(words) - 1), 3) if idx is not None else None

    # --- C 断裂：句内停顿前后 F0 差
    if len(segs) >= 2:
        gaps = []
        for i in range(len(segs) - 1):
            g0, g1 = segs[i][1], segs[i + 1][0]
            if g1 - g0 < 0.12:      # 只算真停顿
                continue
            pre = (t_f0 >= g0 - 0.15) & (t_f0 < g0)
            post = (t_f0 > g1) & (t_f0 <= g1 + 0.15)
            if pre.sum() >= 3 and post.sum() >= 3:
                gaps.append(abs(float(np.median(st[post])) - float(np.median(st[pre]))))
        r["gap_jump_st"] = round(float(np.median(gaps)), 2) if gaps else None
        r["gap_jump_max_st"] = round(float(np.max(gaps)), 2) if gaps else None
        r["n_gap"] = len(gaps)
    else:
        r["gap_jump_st"] = r["gap_jump_max_st"] = None
        r["n_gap"] = 0

    # --- D 分布：起伏集中度（前 30% 时间占了多少幅度）
    if t1 - t0 > 0.6:
        early = st[t_f0 <= t0 + 0.3 * (t1 - t0)]
        late = st[t_f0 > t0 + 0.3 * (t1 - t0)]
        if len(early) >= 5 and len(late) >= 5:
            r["early_iqr"] = round(float(np.percentile(early, 75) - np.percentile(early, 25)), 2)
            r["late_iqr"] = round(float(np.percentile(late, 75) - np.percentile(late, 25)), 2)
            r["iqr_skew"] = round(r["early_iqr"] - r["late_iqr"], 2)
    return r


# ---------------------------------------------------------------- 马修侧

def matt_sentences(words, min_words=4):
    """用 whisper 词序列（带标点）切句，返回 [{'text':..,'t0':..,'t1':..,'words':[(w,t0,t1)]}]"""
    sents, cur = [], []
    for w, a, b in words:
        cur.append((w, a, b))
        if w.rstrip("\"'")[-1:] in ".?!":
            if len(cur) >= min_words:
                sents.append(cur)
            cur = []
    if len(cur) >= min_words:
        sents.append(cur)
    out = []
    for c in sents:
        txt = " ".join(x[0] for x in c)
        out.append(dict(text=txt, t0=c[0][1], t1=c[-1][2], words=c))
    return out


def run_matt(wav, words_json, out_json):
    x, sr = load_wav(wav)
    words = [(w, float(a), float(b)) for a, b, w in
             json.load(open(words_json, encoding="utf-8"))]
    words = [t for t in words if t[2] - t[1] <= 1.5]
    words.sort(key=lambda t: t[1])
    sents = matt_sentences(words)
    print("马修：%d 词 → %d 句" % (len(words), len(sents)))
    rows = []
    for s in sents:
        i0, i1 = int(s["t0"] * sr), int(s["t1"] * sr)
        seg = x[max(0, i0): min(len(x), i1)]
        if len(seg) < sr // 4:
            continue
        t_f, f = f0_series(seg, sr)
        if len(f) < 10:
            continue
        t_f = t_f + s["t0"]
        segs = [(a + s["t0"], b + s["t0"]) for a, b in
                vad_segs(seg, sr)]
        wb = [(w, a, b) for w, a, b in s["words"]]
        r = feats_of_sentence(t_f, f, s["text"], segs, word_bounds=wb)
        if r:
            r.update(dict(text=s["text"], t0=round(s["t0"], 2), t1=round(s["t1"], 2)))
            rows.append(r)
    json.dump(dict(rows=rows, n=len(rows)), open(out_json, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("写出 %s（%d 句）" % (out_json, len(rows)))
    return rows


# ---------------------------------------------------------------- 我们侧

def run_ours(dirp, state_json, out_json, ch="ch1", limit=0):
    S = json.load(open(state_json, encoding="utf-8"))["units"]
    files = sorted(glob.glob(os.path.join(dirp, "*.wav")))
    if ch:
        files = [f for f in files
                 if S.get(os.path.splitext(os.path.basename(f))[0], {}).get("ch") == ch]
    if limit:
        files = files[:limit]
    print("我们：%d 条" % len(files))
    rows = []
    for f in files:
        k = os.path.splitext(os.path.basename(f))[0]
        u = S.get(k)
        if not u:
            continue
        x, sr = load_wav(f)
        if len(x) < sr // 4:
            continue
        t_f, f0 = f0_series(x, sr)
        if len(f0) < 10:
            continue
        segs = vad_segs(x, sr)
        # 没有词级时间戳：按音节核 + 音节数比例对齐
        bounds = [s[0] for s in segs] + [segs[-1][1]] if segs else [0.0, len(x) / sr]
        n_syl = sum(1 for _ in syllabic_peaks(x, sr, segs[0][0], segs[-1][1])) if segs else 0
        wb = split_words_by_syllables(u["text"], n_syl, [bounds[0], bounds[-1]])
        r = feats_of_sentence(t_f, f0, u["text"], segs, word_bounds=wb)
        if r:
            r.update(dict(uid=k, text=u["text"], n_syl_est=int(n_syl)))
            rows.append(r)
    json.dump(dict(rows=rows, n=len(rows)), open(out_json, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("写出 %s（%d 条）" % (out_json, len(rows)))
    return rows


# ---------------------------------------------------------------- 汇总

def summarize(rows, tag):
    if not rows:
        print(tag, "无数据")
        return {}
    def q(key, ps=(10, 25, 50, 75, 90)):
        v = [r[key] for r in rows if r.get(key) is not None]
        if not v:
            return None
        return [round(float(np.percentile(v, p)), 2) for p in ps]
    out = dict(n=len(rows))
    print("\n=== %s (n=%d) ===" % (tag, len(rows)))
    for key in ["iqr_st", "jump_max_st", "jump_p90_st", "jump_rate",
                "gap_jump_st", "gap_jump_max_st", "peak_pos", "iqr_skew"]:
        v = q(key)
        if v:
            print("  %-16s p10 %6.2f  p25 %6.2f  p50 %6.2f  p75 %6.2f  p90 %6.2f"
                  % (key, *v))
            out[key] = v
    # 落点
    pf = [r for r in rows if "peak_word_func" in r]
    if pf:
        rate = sum(1 for r in pf if r["peak_word_func"]) / len(pf)
        print("  峰值落在功能词: %d/%d = %.1f%%" % (
            sum(1 for r in pf if r["peak_word_func"]), len(pf), 100 * rate))
        out["peak_on_func_pct"] = round(100 * rate, 1)
    pl = [r for r in rows if r.get("peak_word_is_longest") is not None]
    if pl:
        rate = sum(1 for r in pl if r["peak_word_is_longest"]) / len(pl)
        print("  峰值落在句内最长词: %d/%d = %.1f%%" % (
            sum(1 for r in pl if r["peak_word_is_longest"]), len(pl), 100 * rate))
        out["peak_on_longest_pct"] = round(100 * rate, 1)
    # 突跳超限比例
    for th in (4.0, 6.0, 8.0):
        v = [r["jump_max_st"] for r in rows if r.get("jump_max_st") is not None]
        if v:
            print("  句内最大跳变 > %.0f 半音: %d/%d = %.1f%%" % (
                th, sum(1 for x in v if x > th), len(v),
                100 * sum(1 for x in v if x > th) / len(v)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["matt", "ours", "cmp"], default="cmp")
    ap.add_argument("--matt-wav", default=r"G:/_setup/_matt_master.wav")
    ap.add_argument("--matt-words", default=r"G:/_setup/_matt_asr_words.json")
    ap.add_argument("--ours-dir", default=r"G:/_setup/_mt_raw_ch1")
    ap.add_argument("--state", default=r"G:/_setup/_mt_loop_state.json")
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out-matt", default=r"G:/_setup/_intra_matt.json")
    ap.add_argument("--out-ours", default=r"G:/_setup/_intra_ours.json")
    a = ap.parse_args()

    if a.mode in ("matt", "cmp"):
        if not os.path.exists(a.matt_wav):
            cand = glob.glob(r"G:/_setup/*matt*master*.wav") + glob.glob(r"G:/_setup/*.wav")
            print("找不到母带，候选：", cand[:5])
        else:
            run_matt(a.matt_wav, a.matt_words, a.out_matt)
    if a.mode in ("ours", "cmp"):
        run_ours(a.ours_dir, a.state, a.out_ours, a.ch, a.limit)


if __name__ == "__main__":
    main()
