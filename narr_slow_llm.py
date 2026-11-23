# -*- coding: utf-8 -*-
"""narr_slow_llm.py —— 旁白「特定情节减速」的 LLM 标定与校验。

为什么要 LLM：`mt_scene.py` 靠关键词正则（dead|afraid|cold|kill × 1.25），
抓不到「父亲刚拒绝他，这段其实是屈辱」这类。而情节重要性是语义判断。

为什么要校验：rate 是硬约束，不是提示词能保证的。实测（_rate_calib/CONCLUSION.md）：
  - 按句挂 span 时 rate 0.76 兑现 100%、0.72 兑现 108%
  - **0.70 断崖：直接丢整句**（ASR 只转出第一句）
  - 减速还需要按 1/rate 放宽 max_tokens，否则长块必截断

用法：
  # ① 列出带编号的句子（喂给 LLM 判定用）
  python narr_slow_llm.py --list ch1

  # ② 校验 LLM 给的方案（不写盘）
  python narr_slow_llm.py --validate _narr_rate_raw.json

  # ③ 校验通过后落地
  python narr_slow_llm.py --validate _narr_rate_raw.json --apply
"""
import argparse
import json
import math
import os
import re
import sys

BASE_RATE = 0.80
RATE_MIN, RATE_MAX = 0.72, 0.84
RATE_HARD_FLOOR = 0.72          # 0.70 实测丢整句
ADJ_DELTA_MAX = 0.06            # 相邻段 rate 差上限（避免突兀跳变）
SLOW_COVER_MAX = 0.20           # 减速段词数占比上限（否则整章都慢 = 没有对比）
EXTREME_MAX_N = 1               # rate<=0.72 的段最多 1 段
SEG_WORDS_MIN, SEG_WORDS_MAX = 25, 160
# token 估算锚点（实测，不要拍）：
#   chapter1/audio/fix/c04.wav = 146 词 @ rate 0.78 → 71.0s，max_tokens 900 完整无截断
#   ⇒ 12.7 token/秒语音；rate=1.0 时语速 158 wpm（由 146/71.0 @0.78 反推）
TOK_PER_SEC = 12.7
WPM_AT_1 = 158.0
TOKEN_SAFETY = 1.08

CH_TEXT = {
    "ch1": r"G:/_setup/chapter1/chapter1_narration.txt",
}
OUT_DEFAULT = r"G:/_setup/narr_rate_plan.json"


def load_sents(ch):
    p = CH_TEXT.get(ch)
    if not p or not os.path.exists(p):
        raise SystemExit("找不到章节文本: %s" % p)
    t = open(p, encoding="utf-8").read().strip()
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    return sents


def cmd_list(ch):
    sents = load_sents(ch)
    print("# %s  %d 句 / %d 词" % (ch, len(sents), sum(len(s.split()) for s in sents)))
    print()
    for i, s in enumerate(sents):
        print("[%03d] (%2d词) %s" % (i, len(s.split()), s))


def max_tokens_for(words, rate):
    """减速块要放宽 max_tokens：rate 越低，同样文本消耗越多 token。
    实测锚点见 TOK_PER_SEC 注释。1.08 是余量，不是拍脑袋的 1.15。"""
    dur = words / WPM_AT_1 * 60.0 / max(rate, 0.5)
    return int(math.ceil(dur * TOK_PER_SEC * TOKEN_SAFETY / 10.0) * 10)


def validate(plan, sents):
    errs, warns = [], []
    ch = next(iter(plan.keys()))
    paras = plan[ch].get("paras") or []
    if not paras:
        return ["paras 为空"], []

    n = len(sents)
    wcum = [0]
    for s in sents:
        wcum.append(wcum[-1] + len(s.split()))

    # ---- 覆盖：从 0 开始、连续、无重叠、到 n-1 结束
    cur = 0
    for k, p in enumerate(paras):
        s0, s1 = int(p.get("s0", -1)), int(p.get("s1", -1))
        if s0 != cur:
            errs.append("段#%d s0=%d 应为 %d（必须连续覆盖）" % (k, s0, cur))
        if s1 < s0:
            errs.append("段#%d s1=%d < s0=%d" % (k, s1, s0))
        cur = s1 + 1
    if cur != n:
        errs.append("段落到 s1=%d 结束，但共 %d 句（0..%d）" % (cur - 1, n, n - 1))

    # ---- rate 约束
    total_words = wcum[-1]
    slow_words = 0
    n_extreme = 0
    rates = []
    for k, p in enumerate(paras):
        r = float(p.get("rate", BASE_RATE))
        rates.append(r)
        if r < RATE_HARD_FLOOR - 1e-9:
            errs.append("段#%d rate=%.2f < 硬下限 %.2f（实测会丢整句）"
                        % (k, r, RATE_HARD_FLOOR))
        if r > RATE_MAX + 1e-9:
            errs.append("段#%d rate=%.2f > 上限 %.2f（只降不升）" % (k, r, RATE_MAX))
        if r <= 0.72 + 1e-9:
            n_extreme += 1
        if r < BASE_RATE - 1e-9:
            s0, s1 = int(p.get("s0", 0)), int(p.get("s1", 0))
            slow_words += wcum[min(s1 + 1, n)] - wcum[min(s0, n)]
        w = wcum[min(int(p.get("s1", 0)) + 1, n)] - wcum[min(int(p.get("s0", 0)), n)]
        if w < SEG_WORDS_MIN:
            warns.append("段#%d 只有 %d 词（< %d，太碎）" % (k, w, SEG_WORDS_MIN))
        if w > SEG_WORDS_MAX:
            errs.append("段#%d 有 %d 词（> %d，减速时会超 token）"
                        % (k, w, SEG_WORDS_MAX))
        if not p.get("why"):
            errs.append("段#%d 缺 why（理由必填）" % k)

    for k in range(len(rates) - 1):
        d = abs(rates[k] - rates[k + 1])
        if d > ADJ_DELTA_MAX + 1e-9:
            errs.append("段#%d→#%d rate 跳 %.2f（> %.2f，听感会突兀）"
                        % (k, k + 1, d, ADJ_DELTA_MAX))

    if n_extreme > EXTREME_MAX_N:
        errs.append("rate<=0.72 的段有 %d 个（最多 %d）" % (n_extreme, EXTREME_MAX_N))

    cov = slow_words / total_words if total_words else 0.0
    if cov > SLOW_COVER_MAX + 1e-9:
        errs.append("减速段占 %.0f%% 词数（> %.0f%%，整章会显得拖）"
                    % (cov * 100, SLOW_COVER_MAX * 100))
    return errs, warns


def cmd_validate(path, apply):
    sents_map = {}
    for ch in CH_TEXT:
        try:
            sents_map[ch] = load_sents(ch)
        except SystemExit:
            pass
    raw = json.load(open(path, encoding="utf-8"))
    ok = True
    for ch, body in raw.items():
        if ch.startswith("_") or ch not in sents_map:
            continue
        errs, warns = validate({ch: body}, sents_map[ch])
        n = len(sents_map[ch])
        wcum = [0]
        for s in sents_map[ch]:
            wcum.append(wcum[-1] + len(s.split()))
        print("== %s  %d 句 / %d 词 / %d 段" % (ch, n, wcum[-1], len(body.get("paras") or [])))
        for p in body.get("paras") or []:
            s0, s1 = int(p["s0"]), int(p["s1"])
            w = wcum[min(s1 + 1, n)] - wcum[min(s0, n)]
            print("  #%02d 句 %3d~%-3d  %3d词  rate %.2f  tok≤%4d  %s"
                  % (p.get("idx", 0), s0, s1, w, float(p["rate"]),
                     max_tokens_for(w, float(p["rate"])), str(p.get("why", ""))[:46]))
        if warns:
            print("  [warn] " + " / ".join(warns))
        if errs:
            ok = False
            print("  [FAIL]")
            for e in errs:
                print("    - " + e)
        else:
            print("  [PASS]")
        print()

    if not ok:
        print("校验未通过，不落地。")
        return 1
    if not apply:
        print("校验通过（未加 --apply，不写盘）。")
        return 0
    dst = OUT_DEFAULT
    json.dump(raw, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已写 %s" % dst)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", metavar="CH", help="列出章节带编号的句子")
    ap.add_argument("--validate", metavar="JSON", help="校验 LLM 方案")
    ap.add_argument("--apply", action="store_true", help="校验通过后写 narr_rate_plan.json")
    a = ap.parse_args()
    if a.list:
        cmd_list(a.list)
    elif a.validate:
        sys.exit(cmd_validate(a.validate, a.apply))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
