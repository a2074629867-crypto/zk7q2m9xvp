# -*- coding: utf-8 -*-
"""逗号分级：不是所有逗号都该停 1.16s。

为什么必须从原文读标点
  实测（_pause_probe.py）：
    L005 "All he looks like, is one of his dead old moths."
         whisper 只找回句末句号，**逗号丢失** → plan 0 处，一个字都没插
    L084 "When did he die, I said."
         whisper 把逗号认成 **问号** → 走 0.24s 档，实际只补 0.06s
  ⇒ ASR 标点不可信。标点一律取原文，ASR 只负责给时间点（difflib 对齐）。

六档（先验值，可用 --tiers 覆盖；标定状态见 pause_tiers.json 的 note）
  zero    语法性逗号，朗读几乎不停   "All he looks like, is ..."      0.00s
  marker  话语标记/应答词后           "Anyway, / Oh, / Well, / Nothing," 0.30s
  list    列举，短语并列              "a, b, c"（同段 ≥3 逗号且每段 ≤3 词）0.40s
  short   一侧从句很短                "Not very long ago, either."      0.70s
  mid     从句边界（默认，= 库中位）   "When my father dies, ..."        1.16s
  long    长从句前（= 库 p75）                                        1.53s

  句号 1.56s（库中位，不改）；问号 0.24s（n=1，用户明确要求不动，报告里标 ⚠）。

用法
  python -u mt_pause_rules.py --dry --only L005,L046,L084
"""
import argparse
import difflib
import json
import os
import sys

sys.path.insert(0, r'G:/_setup')

STRONG = '.?!;:'
MARKER = set('''well oh yes no now so then here look anyway right okay ok
dear please sir madam but and or nothing hello hi ah eh hmm why what how
when where who whom whose i mean you know think suppose see come good
my dear of course'''.split())
# 语法性逗号：这些词后面紧跟谓语时，朗读基本不停
CONJ_INSERT = set('''like as than that which who whom whose because if when
while though although since whether unless whereas'''.split())

TIERS_DEFAULT = {
    'zero': 0.00,
    'marker': 0.30,
    'list': 0.40,
    'short': 0.70,
    'mid': 1.16,      # pause_bank[','] median
    'long': 1.53,     # pause_bank[','] p75
    'dot_inner': 0.85,  # 条内句号：同一句台词里的分句
    '.': 1.56,        # pause_bank['.'] median —— 这是**条间**值，留给拼接器
    '?': 0.24,        # pause_bank['?'] n=1 —— 用户要求不动
}

# ★ 2026-11-11：**分角色档位**。默认那套 1.16/1.53 是马修旁白母带（wonder_train.wav，
#   97wpm 睡前朗读）的实测量。它拿来给情绪化对白用会长出 2~3 倍：
#   夏尔真人 62 处实测中位 0.43（p25 0.35 / p75 0.60 / **本人最大 0.76**），
#   而 1.16/0.43 = 2.70×。所以对白必须有自己的档位，且上限硬压 0.76。
#   出处：REQUIREMENTS 19-0 / 19b；_annot_task.md（对白 kind 表）；日志 2026-10-30
#   「比值不可跨体裁迁移：旁白 1.25 / 对白 0.59 / 我们 0.40」。
TIERS_DIALOG = {
    'zero': 0.00,
    'marker': 0.15,
    'list': 0.25,
    'short': 0.30,
    'mid': 0.43,       # 夏尔真人停顿中位 n=62
    'long': 0.60,      # 夏尔 p75
    'dot_inner': 0.55,  # 条内句号，上限 0.76 以内
    '.': 0.76,         # 条间封顶（夏尔本人实测最大 0.76，绝不能给 1.56）
    '?': 0.24,         # 用户要求保留不动
}
DIALOG_CAP = 0.76      # 硬上限：任何档位、任何 LLM 判定都不许超过
NARR_ROLES = ('narr', 'narrator', 'narr_sliced')


def tiers_for(role=None):
    """按声道取档位。旁白/未知 → 默认（马修母带）；对白角色 → 夏尔档。"""
    if role is None or str(role).lower() in NARR_ROLES:
        return dict(TIERS_DEFAULT)
    return dict(TIERS_DIALOG)

TIERS_NOTE = {
    'zero': '先验（语言学）· 无真人样本',
    'marker': '先验 · 待从真人原声标定',
    'list': '先验 · 待从真人原声标定',
    'short': '先验 · 待标定',
    'mid': '实测 pause_bank 逗号中位 n=220',
    'long': '实测 pause_bank 逗号 p75 n=220',
    'dot_inner': '⚠ 先验 0.85 · pause_bank 的 1.56 是条间值（含换气），直接用会让 10 词句膨胀 90%',
    '.': '实测 pause_bank 句号中位 n=142 —— 条间用',
    '?': '⚠ n=1 脏值，用户要求不改',
}


def _norm(w):
    return ''.join(c for c in w.lower() if c.isalnum())


def _strong(p):
    return any(c in STRONG for c in p)


def parse_text(text):
    """原文 → [(word, trailing_punct)]。撇号保留在词内，引号/括号剥离。"""
    toks = []
    for raw in text.split():
        w, p = raw, ''
        while w and not w[-1].isalnum():
            ch = w[-1]
            if ch in '"\')]}':
                w = w[:-1]
            else:
                p = ch + p
                w = w[:-1]
        while w and not w[0].isalnum():
            w = w[1:]
        if w:
            toks.append((w, p))
    return toks


def segments(toks):
    """按强标点切段，返回每段的 [start, end] 词下标（含）。"""
    segs, s = [], 0
    for i, (_, p) in enumerate(toks):
        if _strong(p) or i == len(toks) - 1:
            segs.append((s, i))
            s = i + 1
    if s < len(toks):
        segs.append((s, len(toks) - 1))
    return segs


def align_pair(a, b):
    """原文词序列 → ASR 词序列的单调映射，返回 {orig_idx: asr_idx}。

    不能只用 difflib 的 equal 段：实测 ASR 会把词换成近音/变体，
        But→buddy   Well,it→while,i   twenty→20   It'll→it will   all right→alright
    这些位置 difflib 报 replace，严格匹配直接断掉，后面对齐就整片失败
    （全库 70 处标点里有 8 处因此测不了、插不进）。
    ⇒ replace 段内部按顺序配对，多出的原文词落到同一个 ASR 词上。
    """
    pair = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == 'equal':
            for n in range(i2 - i1):
                pair[i1 + n] = j1 + n
        elif tag == 'replace':
            na, nb = i2 - i1, j2 - j1
            for t in range(na):
                pair[i1 + t] = j1 + min(int(t * nb / na), nb - 1)
    return pair


def classify(toks, i, tiers):
    """toks[i] 尾部是逗号。返回 (tier, target, reason)。"""
    j = i
    while j > 0 and not _strong(toks[j - 1][1]):
        j -= 1
    left = [_norm(w) for w, _ in toks[j:i + 1]]

    k = i + 1
    while k < len(toks) - 1 and not _strong(toks[k][1]):
        k += 1
    right = [_norm(w) for w, _ in toks[i + 1:k + 1]]

    if len(left) <= 2 and left and all(w in MARKER for w in left):
        return 'marker', tiers['marker'], '左段全是话语标记: %s' % ' '.join(left)

    if left and left[-1] in CONJ_INSERT and len(left) >= 2:
        return 'zero', tiers['zero'], '语法性逗号（%s 后接从句）' % left[-1]

    # 列举：本段内 ≥3 个逗号，且每个子段 ≤3 词
    for s0, s1 in segments(toks):
        if not (s0 <= i <= s1):
            continue
        subs, cur = [], s0
        for m in range(s0, s1 + 1):
            if toks[m][0] and ',' in toks[m][1]:
                subs.append(m - cur + 1)
                cur = m + 1
        if len(subs) >= 3 and max(subs) <= 3:
            return 'list', tiers['list'], '列举（本段 %d 逗号，最长子段 %d 词）' % (
                len(subs), max(subs))
        break

    if len(left) <= 3 or len(right) <= 2:
        return 'short', tiers['short'], '短从句（左%d 右%d 词）' % (len(left), len(right))
    if len(left) >= 9:
        return 'long', tiers['long'], '长从句（左 %d 词）' % len(left)
    return 'mid', tiers['mid'], '默认（左%d 右%d 词）' % (len(left), len(right))


def plan_from_text(rw, text, tiers=None, max_add=3.0):
    """原文标点 + ASR 时间 → 插入计划。
    rw = word_times(wav)；返回 [(cut_sec, add_sec, word, target, cur_gap, tier, reason)]"""
    tiers = dict(TIERS_DEFAULT, **(tiers or {}))
    toks = parse_text(text)
    if len(toks) < 2 or len(rw) < 2:
        return [], toks

    a = [_norm(w) for w, _ in toks]
    b = [_norm(w[2]) for w in rw]
    pair = align_pair(a, b)

    hit = len(pair)
    plan = []
    for i in range(len(toks) - 1):
        p = toks[i][1]
        if ',' not in p:
            continue
        if i not in pair or (i + 1) not in pair:
            continue
        ia, ib = pair[i], pair[i + 1]
        end = rw[ia][1]
        nxt = rw[ib][0]
        tier, tgt, why = classify(toks, i, tiers)
        if tgt <= 0:
            plan.append((0.0, 0.0, toks[i][0], 0.0, max(nxt - end, 0.0), tier, why, i))
            continue
        cur = max(nxt - end, 0.0)
        add = min(tgt, max_add) - cur
        plan.append(((end + nxt) / 2.0, max(add, 0.0), toks[i][0], tgt, cur, tier, why, i))

    # 句末强标点（句内多句时才有意义）：i 尾部是 .?! 且 i 不是最后一个词
    for i in range(len(toks) - 1):
        p = toks[i][1]
        if not _strong(p) or ',' in p:
            continue
        if i not in pair or (i + 1) not in pair:
            continue
        key = '?' if '?' in p else ('.' if '.' in p else None)
        if key is None:
            continue
        ia, ib = pair[i], pair[i + 1]
        end, nxt = rw[ia][1], rw[ib][0]
        cur = max(nxt - end, 0.0)
        tgt = tiers[key] if key == '?' else tiers['dot_inner']
        plan.append(((end + nxt) / 2.0, max(tgt - cur, 0.0), toks[i][0], tgt, cur,
                     'dot_inner' if key == '.' else key,
                     '条内句%s（%s）' % (key, TIERS_NOTE.get(
                         'dot_inner' if key == '.' else '?')), i))

    plan.sort(key=lambda x: x[0])
    return plan, toks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--dir', default=r'G:/_setup/ch123_final')
    ap.add_argument('--tiers', default=r'G:/_setup/pause_tiers.json')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    import glob

    import numpy as np
    import soundfile as sf

    from _wtlib import word_times_cached as word_times
    from ch123_plan import INNER, PLAN

    tiers = {}
    if os.path.exists(a.tiers):
        tiers = json.load(open(a.tiers, encoding='utf-8'))

    text = {'L%03d' % i: t for i, _, _, t in PLAN}
    text.update({'I%02d' % i: t for i, (_, _, _, t) in enumerate(INNER)})
    files = sorted(glob.glob(os.path.join(a.dir, '*.wav')))
    if a.only:
        keep = set(a.only.split(','))
        files = [f for f in files if os.path.basename(f)[:-4] in keep]

    for f in files:
        k = os.path.basename(f)[:-4]
        if k not in text:
            continue
        rw = word_times(f)
        plan, toks = plan_from_text(rw, text[k], tiers)
        tot = sum(p[1] for p in plan)
        print('%-5s | %s' % (k, text[k][:100]))
        print('        原文%d词 ASR%d词  插%d处 共+%.2fs' % (len(toks), len(rw), len(plan), tot))
        for t, add, w, tgt, cur, tier, why, _i in plan:
            if tgt <= 0:
                print('        [%s] %-12s 目标0（不停） 现有%.3f  %s' % (tier, w + ',', cur, why))
            else:
                print('        [%-6s] %-12s 目标%.2f 现有%.3f 补%.2f  %s'
                      % (tier, w + ',', tgt, cur, add, why))
        print()


if __name__ == '__main__':
    main()
