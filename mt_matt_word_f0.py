# -*- coding: utf-8 -*-
"""马修母带的**词级** F0 分析 —— 起伏是不是由「词 + 上下文」决定。

为什么重做：
  之前用「段后间隙长度」当句末/句内的代理，比 decl_st 中位数，得出
  「马修不做句法驱动的起伏」。这个测法有三处错：
    1. 段后间隙 ≠ 句法位置（gap>1.2 也可能是句内强停顿）
    2. decl_st = 段末−段首，是整段单调走向，不是起伏落点
    3. 627 段当独立样本做组间中位比较 = 跨句统计，正好把「词决定的起伏」平均掉

本脚本把 F0 切到**词**，回答：
  A 同一个词在不同上下文里的 F0 变化有多大（功能词 vs 内容词）
  B 句内 F0 方差里，句间 / 句内词间 / 词内 各占多少
  C 哪些词拿到高 F0（词类、音节数、句内位置、是否句末）
  D 词级 F0 高度能被「词属性」解释多少（方差分解 R²）
"""
import os
import sys
import json
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
WORDS = "G:/_setup/_matt_asr_words.json"

FUNC = set("""a an the and or but nor for so yet of to in on at by with from into onto
about over under between among through during before after above below up down out off
is am are was were be been being do does did have has had will would shall should can
could may might must this that these those it its he she they them his her their our your
my me him us i you we as if than then there here not no
""".split())

# 粗略词类（whisper 不给词性，用后缀 + 功能词表 + 位置启发）
def guess_pos(w):
    c = "".join(ch for ch in w.lower() if ch.isalpha())
    if not c:
        return "punct"
    if c in FUNC:
        return "func"
    if c.endswith("ly"):
        return "adv"
    if c.endswith(("ing", "ed")):
        return "verb"
    if c.endswith(("ous", "ful", "less", "ive", "able", "ible", "al", "ic", "ish", "y")):
        return "adj"
    if c.endswith(("tion", "sion", "ment", "ness", "ity", "ance", "ence", "er", "or", "ist")):
        return "noun"
    if c.endswith("s") and len(c) > 3:
        return "noun"
    return "other"


def nsyl(w):
    c = "".join(ch for ch in w.lower() if ch.isalpha())
    if not c:
        return 0
    n, prev = 0, False
    for ch in c:
        v = ch in "aeiouy"
        if v and not prev:
            n += 1
        prev = v
    if c.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def load_wav(p):
    import soundfile as sf
    x, sr = sf.read(p, dtype="float64", always_2d=True)
    return x.mean(1), sr


def f0_series(x, sr, floor=60.0, ceil=250.0, vt=0.20):
    import parselmouth
    snd = parselmouth.Sound(np.asarray(x, dtype=np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceil,
                          voicing_threshold=vt, silence_threshold=0.03)
    f = pit.selected_array["frequency"]
    t = pit.xs()
    m = f > 0
    return np.asarray(t[m]), np.asarray(f[m])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", default=MASTER)
    ap.add_argument("--words", default=WORDS)
    ap.add_argument("--out", default="G:/_setup/_matt_word_f0.json")
    a = ap.parse_args()

    x, sr = load_wav(a.wav)
    raw = json.load(open(a.words, encoding="utf-8"))
    W = [(w, float(t0), float(t1)) for t0, t1, w in raw]
    W = [t for t in W if t[2] - t[1] <= 1.5 and t[2] > t[1]]
    W.sort(key=lambda t: t[1])
    print("母带 %.1f s，%d 词" % (len(x) / sr, len(W)))

    # 整条 F0
    T, F = f0_series(x, sr)
    print("voiced 帧 %d（%.1f%% 时间）" % (len(T), 100 * len(T) * 0.01 / (len(x) / sr)))

    # 切句（按标点）
    sents, cur = [], []
    for w, t0, t1 in W:
        cur.append((w, t0, t1))
        if w.rstrip("\"'")[-1:] in ".?!":
            if len(cur) >= 3:
                sents.append(cur)
            cur = []
    if len(cur) >= 3:
        sents.append(cur)
    print("切出 %d 句" % len(sents))

    # 每句：句内中位 F0 → 词级相对值
    rows = []
    for si, s in enumerate(sents):
        st0, st1 = s[0][1], s[-1][2]
        m = (T >= st0) & (T <= st1)
        if m.sum() < 8:
            continue
        sent_f = F[m]
        sent_med = float(np.median(sent_f))
        if sent_med <= 0:
            continue
        # 句内语音段（用于判「词内 F0 方差」和「词间方差」）
        word_rows = []
        for wi, (w, t0, t1) in enumerate(s):
            mm = (T >= t0) & (T < t1)
            if mm.sum() < 2:
                continue
            fw = F[mm]
            rel = 12.0 * np.log2(np.median(fw) / sent_med)
            word_rows.append(dict(
                w=w, i=wi, n=len(s), t0=round(t0, 3), t1=round(t1, 3),
                nsyl=nsyl(w), pos=guess_pos(w),
                rel=round(float(rel), 2),
                in_word_sd=round(float(np.std(12 * np.log2(fw / sent_med))), 2),
                nframe=int(mm.sum()),
            ))
        if len(word_rows) < 3:
            continue
        # 句内统计
        rels = np.array([r["rel"] for r in word_rows])
        rows.append(dict(
            si=si, text=" ".join(r["w"] for r in word_rows),
            n_word=len(word_rows), sent_med_hz=round(sent_med, 1),
            words=word_rows,
            rel_p10=round(float(np.percentile(rels, 10)), 2),
            rel_p90=round(float(np.percentile(rels, 90)), 2),
            rel_iqr=round(float(np.percentile(rels, 75) - np.percentile(rels, 25)), 2),
            rel_range=round(float(rels.max() - rels.min()), 2),
            peak_word=word_rows[int(np.argmax(rels))]["w"],
            peak_idx=int(np.argmax(rels)),
        ))

    print("有效句 %d" % len(rows))
    json.dump(dict(rows=rows, n=len(rows),
                   meta=dict(wav=a.wav, words=a.words,
                             f0=dict(floor=60, ceil=250, vt=0.20))),
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", a.out)

    # ---------------- 分析 ----------------
    allw = [w for r in rows for w in r["words"]]
    print("\n词级样本 %d" % len(allw))

    # A 按词类看 rel
    print("\n=== A 词级 F0 相对句内中位（半音）===")
    print("%-8s %6s %8s %8s %8s %8s %8s" % ("pos", "n", "p10", "p25", "p50", "p75", "p90"))
    by_pos = {}
    for p in ["func", "noun", "verb", "adj", "adv", "other"]:
        v = [w["rel"] for w in allw if w["pos"] == p]
        if len(v) < 20:
            continue
        q = [float(np.percentile(v, k)) for k in (10, 25, 50, 75, 90)]
        by_pos[p] = dict(n=len(v), p10=round(q[0], 2), p25=round(q[1], 2),
                         p50=round(q[2], 2), p75=round(q[3], 2), p90=round(q[4], 2),
                         sd=round(float(np.std(v)), 2))
        print("%-8s %6d %8.2f %8.2f %8.2f %8.2f %8.2f" % (p, len(v), *q))

    # B 词内方差 vs 词间方差
    print("\n=== B 方差分解 ===")
    in_word = [w["in_word_sd"] for w in allw]
    sent_meds = [r["sent_med_hz"] for r in rows]
    # 句间：各句中位 F0（Hz→相对全体中位的半音）
    gm = float(np.median(F)) if len(F) else 0.0
    between = 12 * np.log2(np.array(sent_meds) / gm) if gm > 0 else np.array([0])
    within_word = np.array(in_word)
    # 句内词间：每句内词级 rel 的 sd
    in_sent = []
    for r in rows:
        v = [w["rel"] for w in r["words"]]
        if len(v) >= 3:
            in_sent.append(np.std(v))
    print("  句间（句中位 F0 的 sd）      %.2f 半音" % float(np.std(between)))
    print("  句内词间（词级 rel 的 sd）   %.2f 半音" % float(np.median(in_sent)))
    print("  词内（一个词内部 F0 的 sd）  %.2f 半音" % float(np.median(within_word)))
    tot = np.std(between) ** 2 + np.median(in_sent) ** 2 + np.median(within_word) ** 2
    print("  → 占比  句间 %.0f%% / 句内词间 %.0f%% / 词内 %.0f%%" % (
        100 * np.std(between) ** 2 / tot,
        100 * np.median(in_sent) ** 2 / tot,
        100 * np.median(within_word) ** 2 / tot))

    # C 峰值词的属性
    print("\n=== C 句内 F0 峰值落在什么词上 ===")
    peaks = [r["words"][r["peak_idx"]] for r in rows]
    import collections
    cpos = collections.Counter(p["pos"] for p in peaks)
    n = len(peaks)
    for p, c in cpos.most_common():
        print("  %-8s %4d  %.1f%%" % (p, c, 100 * c / n))
    func_all = sum(1 for w in allw if w["pos"] == "func") / len(allw)
    print("  （全库功能词占比 %.1f%%，若峰值均匀分布，功能词应占同样比例）" % (100 * func_all))
    # 峰值词在句内位置的分布
    pf = np.array([r["peak_idx"] / max(1, r["n_word"] - 1) for r in rows])
    print("  峰值词位置（0=句首 1=句末）: p10 %.2f p50 %.2f p90 %.2f" % tuple(
        np.percentile(pf, [10, 50, 90])))
    # 峰值词是否句内最长
    longest_hit = 0
    for r in rows:
        lens = [len("".join(ch for ch in w["w"] if ch.isalpha())) for w in r["words"]]
        if max(lens) <= 2:
            continue
        pk = r["words"][r["peak_idx"]]
        cur = len("".join(ch for ch in pk["w"] if ch.isalpha()))
        if cur >= max(lens) - 1:
            longest_hit += 1
    print("  峰值落在句内最长词: %d / %d = %.1f%%" % (longest_hit, len(rows),
                                                  100 * longest_hit / len(rows)))

    # D 同一个词在不同上下文里的 F0 波动
    print("\n=== D 高频词在不同上下文里的 F0（看起伏是否随上下文变）===")
    byw = collections.defaultdict(list)
    for w in allw:
        c = "".join(ch for ch in w["w"].lower() if ch.isalpha())
        if c:
            byw[c].append(w["rel"])
    print("%-10s %5s %7s %7s %7s %7s" % ("word", "n", "p10", "p50", "p90", "sd"))
    for c, v in sorted(byw.items(), key=lambda x: -len(x[1]))[:14]:
        if len(v) < 8:
            continue
        print("%-10s %5d %7.2f %7.2f %7.2f %7.2f" % (
            c, len(v), *[float(np.percentile(v, k)) for k in (10, 50, 90)],
            float(np.std(v))))

    # E 词属性对 F0 的解释力（粗 R²）
    print("\n=== E 「词属性」能解释多少词级 F0 方差 ===")
    y = np.array([w["rel"] for w in allw])
    groups = {}
    for w in allw:
        groups.setdefault(w["pos"], []).append(w["rel"])
    ss_tot = float(((y - y.mean()) ** 2).sum())
    ss_within = sum(float(((np.array(v) - np.mean(v)) ** 2).sum()) for v in groups.values())
    print("  词类（6 类）            R² = %.3f" % (1 - ss_within / ss_tot))
    # 音节数
    groups2 = {}
    for w in allw:
        groups2.setdefault(min(w["nsyl"], 5), []).append(w["rel"])
    ss_w2 = sum(float(((np.array(v) - np.mean(v)) ** 2).sum()) for v in groups2.values())
    print("  音节数（1~5+）          R² = %.3f" % (1 - ss_w2 / ss_tot))
    # 句内相对位置（分 5 桶）
    groups3 = {}
    for r in rows:
        for w in r["words"]:
            b = min(4, int(5 * w["i"] / max(1, w["n"])))
            groups3.setdefault(b, []).append(w["rel"])
    ss_w3 = sum(float(((np.array(v) - np.mean(v)) ** 2).sum()) for v in groups3.values())
    print("  句内位置（5 桶）        R² = %.3f" % (1 - ss_w3 / ss_tot))
    # 词 × 位置 联合
    groups4 = {}
    for r in rows:
        for w in r["words"]:
            b = min(4, int(5 * w["i"] / max(1, w["n"])))
            groups4.setdefault((w["pos"], b), []).append(w["rel"])
    ss_w4 = sum(float(((np.array(v) - np.mean(v)) ** 2).sum())
                for v in groups4.values() if len(v) >= 3)
    print("  词类 × 位置（联合）     R² = %.3f" % (1 - ss_w4 / ss_tot))
    print("  ⇒ 剩余是「具体词 + 上下文」，必须靠 LLM 判焦点")


if __name__ == "__main__":
    main()
