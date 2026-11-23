# -*- coding: utf-8 -*-
"""对白链路情绪判定器 —— 给定一条生成音频 + 目标的 ref 与情绪，判断「到底做到没有」。

设计原则（全部来自 2026-11-06 的 48 条实测矩阵，阈值不留想象空间）：

  ① 不看单点绝对分数。Vox 维度头在 TTS 输出上系统性偏低 arousal
     （两个主音色的 base 是 0.32/0.38，真人是 0.50），绝对阈值必然误杀。
  ② 主干判据用 **F0 跨度（p90-p10）** —— 不依赖任何模型，且实测最灵敏：
     真人 neutral 138Hz / happy 153 / sad 84；生成侧 C_normal base 只有 56（语调平），
     打上 happy 后 106、angry 后 185。这一轴的区分度远好于任何分类器输出。
  ③ 音量必须单独看。C_soft / E_begging 上打任何标签都 +4~+12dB，
     那是「喊」，不是「演」——情绪对不对先看 F0 跨度，过冲先看 dB。
  ④ e2v（emotion2vec）在 TTS 域不可靠：48 条里 30 条被判 angry，sad/afraid 命中 0/8。
     只用作佐证，不参与判定。

用法：
  python emo_check.py --wav a.wav --ref C_normal --emo happy [--base b.wav]
  python emo_check.py --dir out/gen --report
"""
import argparse, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

# ── F0 跨度（Hz, p90-p10）目标区间 ──
# 真人锚点：neutral 138 / happy 153 / sad 84 / whisper 134(耳语伪影，不用)
# 区间下沿允许 30% 偏差，上沿到「失控喊叫」为止
SPAN_RANGE = {
    "happy":  (95, 190),
    "sad":    (35, 95),
    "angry":  (140, 230),
    "afraid": (75, 175),
    "calm":   (25, 85),
}
# 各情绪期望 arousal 方向（相对同 ref 的 base）
EXP_DIR = {"happy": +1, "sad": -1, "angry": +1, "afraid": +1, "calm": -1}

# arousal 的**绝对**落点区间。
# 只判相对变化会放过「从 0.80 退到 0.70 就叫 sad」这种假达标
# （C_angry+sad 实测 A=0.70，真人 sad 是 0.32）。
# 区间 = 真人锚点放宽 ±0.13（Vox 头在 TTS 输出上系统性偏低，不放宽会误杀）。
A_RANGE = {
    "happy":  (0.42, 0.72),
    "sad":    (0.20, 0.48),
    "angry":  (0.55, 0.80),
    "afraid": (0.30, 0.62),
    "calm":   (0.18, 0.45),
}

# 过了这条线就是「喊」：实测 C_soft+angry +11.9dB、E_begging+angry +7.4dB 都不可用，
# 而 C_normal+happy 只 +0.7dB —— 干净的表演几乎不动音量
DB_OVER = 6.0
# ★ 不是「吼叫阈值」，是模型观测区间的上界。
#   2026-11-06 审计：真人 745 条实测 A ∈ [0.18, 0.82]，超过 0.85 的占 0.0%——
#   这个头**结构上就到不了 1.0**，IS2025 挑战赛官方把同一现象记作 "gravity of the mean"。
#   所以旧值 0.78（自称「真人 laughing 最高 0.73」）是拿 p99 当墙，会误伤 1.1% 的真人样本。
#   现在只当「超出分布 ⇒ 分数是外推，别信」的告警，判「喊」交给 DB_OVER（物理量，无域偏移）。
A_LIMIT = 0.82
# 效应量分母：真人合并组内 SD（见 analyze_final.py）
SD_A = 0.0729


def phys(path):
    import ser as S
    return S.phys(path)


def dim(path):
    import ser as S
    return S.get("vox_dim").score(path)


def check(wav, ref=None, emo=None, base=None):
    """返回 dict(verdict, reasons, metrics)。verdict ∈ pass / warn / fail。"""
    p = phys(wav)
    d = dim(wav) or {}
    span = p["f0_p90"] - p["f0_p10"]
    out = dict(wav=os.path.basename(wav), ref=ref, emo=emo,
               span=round(span, 1), f0_med=p["f0_med"], db=p["speech_db"],
               hnr=p["hnr"], dur=p["dur"], A=d.get("arousal"),
               V=d.get("valence"), D=d.get("dominance"))
    reasons, level = [], 0        # 0=pass 1=warn 2=fail

    if emo is None:
        # 无目标情绪：只报是否「有表演」——跨度 <70 视为平淡
        out["verdict"] = "pass" if span >= 70 else "warn"
        reasons.append("未指定目标情绪；F0 跨度 %.0fHz %s" %
                       (span, "正常" if span >= 70 else "偏平（<70）"))
        out["reasons"] = reasons
        return out

    lo, hi = SPAN_RANGE[emo]
    # ★ 绝对跨度受 seed 影响很大：C_normal 的 base 在 seed 2051/2053/2054/2052 上
    #   实测 56 / 55 / 69 / 98Hz（近 2 倍差距）。所以有 base 时优先判 Δspan，
    #   绝对区间只作兜底 —— 否则同一段文本换个 seed 就判反。
    dspan = None
    if base:
        try:
            dspan = span - (phys(base)["f0_p90"] - phys(base)["f0_p10"])
            out["d_span"] = round(dspan, 1)
        except Exception:
            dspan = None
    if dspan is not None:
        if emo in ("happy", "angry", "afraid"):
            if dspan < 18:
                level = max(level, 2)
                reasons.append("F0 跨度只变 %+.0fHz（需要 ≥18）：语调没拉开" % dspan)
            elif dspan > 150:
                level = max(level, 1)
                reasons.append("F0 跨度 +%.0fHz 过大：过冲" % dspan)
        else:   # sad / calm 要更平
            if dspan > 25:
                level = max(level, 2)
                reasons.append("F0 跨度 +%.0fHz：sad/calm 要求更平，反而拉宽了" % dspan)
    else:
        if span < lo:
            level = max(level, 2)
            reasons.append("F0 跨度 %.0fHz < %d：语调没拉开，情绪没演出来" % (span, lo))
        elif span > hi:
            level = max(level, 1)
            reasons.append("F0 跨度 %.0fHz > %d：过冲，像喊" % (span, hi))

    # 相对 base 的 arousal 方向
    if base:
        try:
            bd = dim(base)
            pb = phys(base)
            if bd and d.get("arousal") is not None:
                dA = (d["arousal"] - bd["arousal"]) / SD_A
                out["dA_sigma"] = round(dA, 2)
                out["d_db"] = round(p["speech_db"] - pb["speech_db"], 1)
                if np.sign(dA) != EXP_DIR[emo]:
                    level = max(level, 2)
                    reasons.append("arousal 方向反了：ΔA=%+.2fσ，期望 %+d" % (dA, EXP_DIR[emo]))
                elif abs(dA) < 0.5:
                    level = max(level, 1)
                    reasons.append("arousal 只动 %+.2fσ（<0.5σ），作用很弱" % dA)
                if out["d_db"] > DB_OVER:
                    level = max(level, 1)
                    reasons.append("音量 +%.1fdB 超过 %.0fdB：靠音量顶上去，不是表演"
                                   % (out["d_db"], DB_OVER))
        except Exception as e:
            reasons.append("baseline 读不出：%s" % e)

    if d.get("arousal") and d["arousal"] > A_LIMIT:
        level = max(level, 1)
        reasons.append("arousal=%.2f 超出模型观测区间上限 %.2f（该头结构上到不了 1.0），"
                       "此分数属外推，按 ΔdB 判断是否喊" % (d["arousal"], A_LIMIT))

    # 绝对落点：方向对但停在错误的位置，等于没做到
    alo, ahi = A_RANGE[emo]
    if d.get("arousal") is not None:
        A = d["arousal"]
        if A < alo:
            level = max(level, 1)
            reasons.append("arousal=%.2f 低于 %s 的落点区间 [%.2f,%.2f]：强度不够"
                           % (A, emo, alo, ahi))
        elif A > ahi:
            level = max(level, 2)
            reasons.append("arousal=%.2f 高于 %s 的落点区间 [%.2f,%.2f]：还停在激动区"
                           % (A, emo, alo, ahi))
    # ★ 阈值原为 1.0dB，源自一个口径错误：旧实现把 harmonicity 在**整条**
    #   音频上取中位，静音帧（Praat 返回 -200）占多数时整块塌成 -200，
    #   于是 48 条里 10 条报「气声」。改为只用浊音帧后，真人中性 13.5dB、
    #   生成侧中位 13.8dB、最低 9.9dB、真耳语 5.3dB ⇒ 1.0dB 等于永不触发。
    if p["hnr"] < 9.5:
        reasons.append("HNR %.1fdB 偏低（真人中性 13.5，耳语 5.3），听感可能发虚" % p["hnr"])

    out["verdict"] = ["pass", "warn", "fail"][level]
    out["reasons"] = reasons or ["跨度和方向都在目标区间内"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--ref")
    ap.add_argument("--emo")
    ap.add_argument("--base")
    ap.add_argument("--dir")
    ap.add_argument("--job", default=None, help="本地：json 文件或内联 json 字符串")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    # 供上层编排调用：一次判一批
    if a.job:
        raw = a.job
        if os.path.exists(raw):
            raw = open(raw, encoding="utf-8").read()
        items = json.loads(raw)
        res = [check(it["wav"], it.get("ref"), it.get("emo"), it.get("base")) for it in items]
        blob = json.dumps(dict(results=res, n=len(res),
                               n_fail=sum(1 for r in res if r["verdict"] == "fail"),
                               n_warn=sum(1 for r in res if r["verdict"] == "warn")),
                          ensure_ascii=False, indent=1)
        if a.out:
            open(a.out, "w", encoding="utf-8").write(blob)
        print(blob)
        return

    if a.dir:
        idx = {}
        p = os.path.join(HERE, "out", "gen_index.jsonl")
        for ln in open(p, encoding="utf-8"):
            r = json.loads(ln)
            # ★ index 里存的是绝对路径（G:\...），传进来的 --dir 常是相对路径，
            #   不归一化就会一条都匹配不上、静默输出空表。
            idx[os.path.normcase(os.path.abspath(r["path"]))] = r
        rows = []
        for f in sorted(os.listdir(a.dir)):
            if not f.endswith(".wav"):
                continue
            full = os.path.abspath(os.path.join(a.dir, f))
            m = idx.get(os.path.normcase(full))
            if not m:
                continue
            bp = os.path.join(os.path.dirname(full), "%s__base__s%d.wav" % (m["pid"], m["seed"]))
            if not os.path.exists(bp):
                bp = os.path.join(os.path.dirname(full), "%s__base__s2051.wav" % m["pid"])
            rows.append(check(full, m["pid"],
                              None if m["cond"] == "base" else m["cond"],
                              bp if (m["cond"] != "base" and os.path.exists(bp)) else None))
        for r in rows:
            print("%-6s %-11s %-7s span=%5.0f A=%.2f %s"
                  % (r["verdict"], r["ref"], r["emo"], r["span"], r["A"] or 0,
                     " | ".join(r["reasons"])[:90]))
        if a.out:
            json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return

    r = check(a.wav, a.ref, a.emo, a.base)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print("%s  span=%.0fHz  A=%.3f  dBFS=%.1f"
              % (r["verdict"].upper(), r["span"], r["A"] or 0, r["db"]))
        for x in r["reasons"]:
            print("  " + x)


if __name__ == "__main__":
    main()
