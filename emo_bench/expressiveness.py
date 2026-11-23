# -*- coding: utf-8 -*-
"""音色表现力评分 v2：按真人分布区间打分，并做「加标签 vs 不加标签」对照。

为什么用区间而不是单点目标：
  真人 laughing 的 A：p25 0.65 / 中位 0.68 / p90 0.76（最高 0.82）。
  拿中位数 0.68 当靶心的话，真人自己演得激动一点（0.80）就会被判「过冲」——
  实测把 C_excited 这一档的**真人参考切片**喂进去也只有 18 分。
  ⇒ 改成 [p25, p90] 区间内给满分，越界才扣，尺度才对得上人的判断。

主分不含 V：生成侧 V 天花板 0.43，真人 happy 0.56 / laughing 0.73。
  这一轴对所有音色同样够不到（模型通病），放进总分只会把音色差异压平。
  V 单独列，作为「上限提示」。

评分：
  dev_x = 0（落在区间内）否则 越界距离 / 尺度
          跨度用对数尺度 0.30；A 用真人组内 SD 0.0729；D 用 0.10
  fit   = 2·dev_span + dev_A + 0.3·dev_D
  score = 100·exp(−fit/3)      锚：0→100  1→72  2→51  3→37  4→26
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

# 区间 [lo, hi]：跨度 / arousal / dominance
# laughing/happy/sad 用 Expresso 的 p25–p90 实测值；其余三个语料里没有，按语音学构造
BAND = {
    "laughing": dict(span=(108, 209), A=(0.65, 0.76), D=(0.61, 0.72), real=True),
    "happy":    dict(span=(123, 229), A=(0.52, 0.69), D=(0.57, 0.69), real=True),
    "sad":      dict(span=(60, 149),  A=(0.29, 0.40), D=(0.36, 0.48), real=True),
    "angry":    dict(span=(140, 260), A=(0.60, 0.82), D=(0.62, 0.85), real=False),
    "afraid":   dict(span=(90, 200),  A=(0.52, 0.78), D=(0.38, 0.62), real=False),
    "calm":     dict(span=(40, 110),  A=(0.18, 0.42), D=(0.35, 0.55), real=False),
}
ORDER = ["laughing", "happy", "sad", "angry", "afraid", "calm"]
HDR = {"laughing": "激动", "happy": "开心", "sad": "难过",
       "angry": "愤怒*", "afraid": "害怕*", "calm": "平静*"}
TAG_OF = {"laughing": "happy", "happy": "happy", "angry": "angry",
          "afraid": "afraid", "sad": "sad", "calm": "calm"}
REF_WAV = {"C_normal": "1_charles_normal.wav", "C_soft": "2_charles_soft.wav",
           "C_excited": "3_charles_excited_v2.wav", "C_angry": "4_charles_angry_v2.wav",
           "E_calm": "6_hooper_calm.wav", "E_loud": "5_hooper_loud.wav",
           "E_scold": "6b_hooper_scold.wav", "E_begging": "7_hooper_begging.wav"}
SD_A, SD_D, SPAN_SCALE = 0.0729, 0.10, 0.30


def load(n):
    p = os.path.join(HERE, "out", n)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def dev_span(v, band):
    lo, hi = band
    if v < lo:
        return abs(np.log(v / lo)) / SPAN_SCALE
    if v > hi:
        return abs(np.log(v / hi)) / SPAN_SCALE
    return 0.0


def dev_lin(v, band, sd):
    lo, hi = band
    if v < lo:
        return (lo - v) / sd
    if v > hi:
        return (v - hi) / sd
    return 0.0


def score(r, key):
    b = BAND[key]
    ds = dev_span(max(r["span"], 10), b["span"])
    da = dev_lin(r["A"], b["A"], SD_A)
    dd = dev_lin(r["D"], b["D"], SD_D)
    fit = 2 * ds + da + 0.3 * dd
    return 100.0 * np.exp(-fit / 3.0), fit, dict(span=ds, A=da, D=dd)


def main():
    chk = {(r["ref"], r["emo"] or "base"): r
           for r in json.load(open(os.path.join(HERE, "out", "gen_check.json"),
                                   encoding="utf-8"))}
    refs = ["C_normal", "C_soft", "C_excited", "C_angry",
            "E_calm", "E_loud", "E_scold", "E_begging"]
    MAIN = {"C_normal", "E_calm"}

    # 真人参考切片在这把尺子上的分数（= 该情绪的「人类天花板」参照）
    import ser as S
    _V = S.get("vox_dim")
    REFCEIL = {}
    _refsc = {e: [] for e in ORDER}
    for ref in refs:
        pp = os.path.join("G:/_setup/cloud/ref", REF_WAV[ref])
        ph, dm = S.phys(pp), _V.score(pp)
        rr = dict(span=ph["f0_p90"] - ph["f0_p10"], A=dm["arousal"],
                  D=dm["dominance"], V=dm["valence"], db=ph["speech_db"])
        for e in ORDER:
            _refsc[e].append(score(rr, e)[0])
    for e in ORDER:
        REFCEIL[e] = max(_refsc[e])

    def grid(title, fn, note=""):
        print("\n" + "=" * 100)
        print(title)
        if note:
            print(note)
        print()
        print("%-11s %s" % ("音色", "".join("%-11s" % HDR[e] for e in ORDER)))
        for ref in refs:
            cells = ["%.0f" % fn(ref, e) if fn(ref, e) is not None else "-" for e in ORDER]
            print("%-11s %s" % (ref + (" ★" if ref in MAIN else ""),
                                "".join("%-11s" % c for c in cells)))
        print("%-11s %s" % ("真人切片上限", "".join("%-11s" % ("%.0f" % REFCEIL[e]) for e in ORDER)))

    sc_base = {(r, e): score(chk[(r, "base")], e)[0] for r in refs for e in ORDER}
    sc_tag = {(r, e): score(chk[(r, TAG_OF[e])], e)[0] for r in refs for e in ORDER}

    grid("① 不加标签（裸用 base）—— 这一档「本身」的表演力",
         lambda r, e: sc_base[(r, e)])
    grid("② 加语义正确的标签 —— 激动/开心→happy，愤怒→angry，害怕→afraid，难过→sad，平静→calm",
         lambda r, e: sc_tag[(r, e)])
    grid("③ 加标签的净收益（②−①，正=标签有用，负=标签反而更远）",
         lambda r, e: sc_tag[(r, e)] - sc_base[(r, e)])

    # 每情绪排名（取 base 与加标签的高者）
    print("\n" + "=" * 100)
    print("④ 每种情绪下，八档音色怎么排（取 base / 加标签 的高者）\n")
    for e in ORDER:
        rows = []
        for r in refs:
            b, t = sc_base[(r, e)], sc_tag[(r, e)]
            rows.append((max(b, t), r, "base" if b >= t else "+" + TAG_OF[e], b, t))
        rows.sort(reverse=True)
        tag = "" if BAND[e]["real"] else "  *构造区间"
        print("  %s%s" % (HDR[e], tag))
        for i, (s, r, c, b, t) in enumerate(rows[:4], 1):
            print("    %d. %-11s %3.0f   (%s；裸用 %.0f → 加标签 %.0f)" % (i, r, s, c, b, t))
        print()

    # 重点：激动专项
    print("=" * 100)
    print("⑤ 专项：拿「激动」文本去测，各档差在哪（区间：跨度 108–209Hz，A 0.65–0.76，D 0.61–0.72）\n")
    print("%-11s %-7s %-6s %-6s %-6s %-6s %-6s  %s" %
          ("音色", "条件", "评分", "跨度", "A", "D", "V", "越界项"))
    for ref in refs:
        for c in ["base", TAG_OF["laughing"]]:
            r = chk[(ref, c)]
            s, fit, d = score(r, "laughing")
            outs = []
            if d["span"] > 0:
                outs.append("跨度%s%.1f" % ("低" if r["span"] < BAND["laughing"]["span"][0] else "高", d["span"]))
            if d["A"] > 0:
                outs.append("A%s%.1f" % ("低" if r["A"] < BAND["laughing"]["A"][0] else "高", d["A"]))
            if d["D"] > 0:
                outs.append("D%s%.1f" % ("低" if r["D"] < BAND["laughing"]["D"][0] else "高", d["D"]))
            print("%-11s %-7s %-6.0f %-6.0f %-6.2f %-6.2f %-6.2f  %s" %
                  (ref, c, s, r["span"], r["A"], r["D"], r["V"],
                   "、".join(outs) if outs else "全部在区间内"))
        print()

    # 正控：真人 ref 自己打分
    print("=" * 100)
    print("⑥ 正控：把 8 档**真人参考切片**本身喂进这套尺子（若尺度合理，它们在自己那一档应该拿高分）\n")
    import ser as S
    V = S.get("vox_dim")
    print("%-11s %s" % ("真人 ref", "".join("%-11s" % HDR[e] for e in ORDER)))
    tot = []
    for ref in refs:
        p = os.path.join("G:/_setup/cloud/ref", REF_WAV[ref])
        ph = S.phys(p)
        dm = V.score(p)
        r = dict(span=ph["f0_p90"] - ph["f0_p10"], A=dm["arousal"],
                 D=dm["dominance"], V=dm["valence"], db=ph["speech_db"])
        row = [score(r, e)[0] for e in ORDER]
        print("%-11s %s" % (ref, "".join("%-11s" % ("%.0f" % v) for v in row)))
        tot.append(row)
    t = np.array(tot)
    print("\n  每列的最高分（= 该情绪真人最强的那一档）：")
    for j, e in enumerate(ORDER):
        i = int(np.argmax(t[:, j]))
        print("    %-5s %.0f 分 ← %s" % (HDR[e], t[i, j], refs[i]))


if __name__ == "__main__":
    main()
