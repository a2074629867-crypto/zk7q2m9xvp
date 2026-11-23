# -*- coding: utf-8 -*-
"""词间停顿移植 / 标点停顿注入

移植脚本 v2 只搬了 F0 轮廓和词内时长，**完全没碰词间 gap** —— 这是"逗号没停顿"的根因。
本模块直接改音频：在词间低能量处切一刀、插入静音，把 gap 补到目标长度。

两种模式：
  A) donor 模式：--donor real.wav   把真实录音的逗号/句末停顿照搬过来（同文本场景）
  B) 原型模式：--proto bank.json   无 donor 时，按前一词的结尾标点从语料统计里取停顿（真实场景）

用法:
  python -u insert_pauses.py --in gen.wav --out out.wav --donor real.wav --strength 1.0
  python -u insert_pauses.py --in gen.wav --out out.wav --proto G:/_setup/pause_bank.json
"""
import argparse
import difflib
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, r'G:/_setup')
from transplant_prosody2 import word_times  # noqa: E402

# 兜底原型（被 --proto 覆盖）。单位秒。
DEFAULT_PROTO = {
    ',': 0.55, ';': 0.55, ':': 0.50,
    '.': 0.85, '?': 0.85, '!': 0.85,
    '\u2014': 0.45, '\u2013': 0.45,  # — –
}


def rms_frames(x, sr, win=0.01):
    n = max(1, int(win * sr))
    k = len(x) // n
    if k == 0:
        return np.array([0.0]), n
    y = x[:k * n].reshape(k, n)
    return np.sqrt((y ** 2).mean(1)), n


def find_cut(x, sr, lo, hi):
    """在 [lo, hi] 秒内找能量最低处作为切点，返回样本索引。"""
    a = max(0, int(lo * sr))
    b = min(len(x), int(hi * sr))
    if b - a < int(0.004 * sr):
        return max(0, (a + b) // 2)
    r, n = rms_frames(x[a:b], sr)
    i = int(np.argmin(r))
    return a + i * n + n // 2


def apply_cuts(x, sr, cuts, fade=0.010):
    """cuts = [(cut_sample_idx, add_sec)]，从后往前插入静音。"""
    out = x.copy()
    for c, add in sorted(cuts, key=lambda p: -p[0]):
        c = int(np.clip(c, 1, len(out) - 1))
        nf = max(1, int(fade * sr))
        head, tail = out[:c].copy(), out[c:].copy()
        if len(head) > nf and len(tail) > nf:
            head[-nf:] *= np.linspace(1.0, 0.0, nf, dtype=out.dtype)
            tail[:nf] *= np.linspace(0.0, 1.0, nf, dtype=out.dtype)
        sil = np.zeros(int(add * sr), dtype=out.dtype)
        out = np.concatenate([head, sil, tail])
    return out


def tail_punct(w):
    t = w.strip().strip('"\'')[:]
    for ch in reversed(t):
        if ch in ',;:.?!\u2014\u2013':
            return ch
        if ch.isalnum():
            return ''
    return ''


def _nw(w):
    return ''.join(ch for ch in w.lower() if ch.isalnum())


def align_donor(dw, rw):
    """用 difflib 对齐 donor / recv 的词序列，容忍 ASR 的插入删除。
    返回 [(donor_idx, recv_idx)]，只含匹配上的对。"""
    a = [_nw(w[2]) for w in dw]
    b = [_nw(w[2]) for w in rw]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    pairs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                pairs.append((i1 + k, j1 + k))
    return pairs


def plan_from_donor(dw, rw, strength=1.0, min_keep=0.08, max_gap=2.5):
    """用真实录音的 gap 作为目标（difflib 对齐，容忍 ASR 词数差异）。
    返回 [(cut_time_sec, add_sec, word, tgt, cur)]"""
    pairs = align_donor(dw, rw)
    out = []
    for n in range(len(pairs) - 1):
        di, ri = pairs[n]
        di2, ri2 = pairs[n + 1]
        # donor 侧必须相邻（跨词则 gap 不可比）；recv 侧允许跨未匹配词
        # （ASR 漏词时 r_gap 会被算大，add 自然收敛，不会过度插入）
        if di2 != di + 1:
            continue
        d_gap = dw[di2][0] - dw[di][1]
        r_gap = rw[ri2][0] - rw[ri][1]
        if d_gap < min_keep:
            continue
        tgt = min(d_gap * strength, max_gap)
        add = tgt - max(r_gap, 0.0)
        if add < 0.03:
            continue
        cut = (rw[ri][1] + rw[ri2][0]) / 2.0
        out.append((cut, add, rw[ri][2], tgt, r_gap))
    return out


def plan_from_proto(rw, proto, strength=1.0, max_gap=2.5):
    """按前一词结尾标点取停顿。返回 [(cut_time_sec, add_sec, word, tgt, cur)]"""
    out = []
    for i in range(len(rw) - 1):
        p = tail_punct(rw[i][2])
        if p not in proto:
            continue
        tgt = min(float(proto[p]) * strength, max_gap)
        r_gap = rw[i + 1][0] - rw[i][1]
        add = tgt - max(r_gap, 0.0)
        if add < 0.03:
            continue
        cut = (rw[i][1] + rw[i + 1][0]) / 2.0
        out.append((cut, add, rw[i][2], tgt, r_gap))
    return out


def merge_plans(primary, fallback, tol=0.35):
    """primary（donor，真人实际停顿）优先；fallback（原型中位数）只补 primary 没覆盖的位置。"""
    out = list(primary)
    cov = [p[0] for p in primary]
    for p in fallback:
        if any(abs(p[0] - c) < tol for c in cov):
            continue
        out.append(p)
    out.sort(key=lambda x: x[0])
    return out


def insert(in_wav, out_wav, plan, fade=0.010, dry=None):
    x, sr = sf.read(in_wav, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    x = np.ascontiguousarray(x, dtype=np.float32)
    if dry:
        cuts = [(int(t * sr), add) for t, add, *_ in plan]
    else:
        cuts = [(find_cut(x, sr, t - 0.06, t + 0.06), add) for t, add, *_ in plan]
    y = apply_cuts(x, sr, cuts, fade=fade)
    # 防削波
    peak = float(np.abs(y).max())
    if peak > 0.99:
        y *= 0.99 / peak
    sf.write(out_wav, y, sr)
    return len(x) / sr, len(y) / sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--donor', default='')
    ap.add_argument('--proto', default='')
    ap.add_argument('--strength', type=float, default=1.0)
    ap.add_argument('--fade', type=float, default=0.010)
    ap.add_argument('--dry', action='store_true', help='切点取词边界中点，不做能量搜索')
    ap.add_argument('--proto-fallback', action='store_true',
                    help='donor 模式下，未覆盖的标点位置用 --proto 兜底')
    ap.add_argument('--report', default='')
    a = ap.parse_args()

    rw = word_times(a.inp)
    if len(rw) < 2:
        raise SystemExit('词数不足: %s' % a.inp)

    if a.donor:
        dw = word_times(a.donor)
        pairs = align_donor(dw, rw)
        base = min(len(dw), len(rw))
        if len(pairs) < 0.6 * base:
            print('[warn] 对齐率过低 %d/%d，退回原型模式' % (len(pairs), base))
            proto = DEFAULT_PROTO
            plan = plan_from_proto(rw, proto, a.strength)
            mode = 'proto(fallback)'
        else:
            plan = plan_from_donor(dw, rw, a.strength)
            mode = 'donor(对齐 %d/%d, 插 %d 处)' % (len(pairs), base, len(plan))
            if a.proto_fallback and a.proto and os.path.exists(a.proto):
                bank = json.load(open(a.proto, encoding='utf-8'))
                proto = dict(DEFAULT_PROTO)
                for k, v in bank.items():
                    proto[k] = float(v['median']) if isinstance(v, dict) else float(v)
                n0 = len(plan)
                plan = merge_plans(plan, plan_from_proto(rw, proto, a.strength))
                mode += ' +原型补%d处' % (len(plan) - n0)
    else:
        proto = dict(DEFAULT_PROTO)
        if a.proto and os.path.exists(a.proto):
            bank = json.load(open(a.proto, encoding='utf-8'))
            for k, v in bank.items():
                proto[k] = float(v['median']) if isinstance(v, dict) else float(v)
            # 语料里没出现的标点，用逗号/句号的值按比例兜底
            c = proto.get(',', 0.55)
            p = proto.get('.', 0.85)
            for k, frac in ((';', 0.85), (':', 0.75), ('!', 1.0), ('?', 1.0),
                            ('\u2014', 0.75), ('\u2013', 0.75)):
                proto.setdefault(k, c + (p - c) * frac)
        plan = plan_from_proto(rw, proto, a.strength)
        mode = 'proto'

    if not plan:
        print('[skip] %-24s 无需插入停顿' % os.path.basename(a.inp), flush=True)
        x, sr = sf.read(a.inp, dtype='float32')
        sf.write(a.out, x, sr)
        return

    d0, d1 = insert(a.inp, a.out, plan, fade=a.fade, dry=a.dry)
    print('[ok] %-24s %s  插入 %d 处  时长 %.2fs → %.2fs (%+.2fs)' %
          (os.path.basename(a.inp), mode, len(plan), d0, d1, d1 - d0), flush=True)
    for t, add, w, tgt, cur in plan:
        print('       %-14s 目标%.3fs 现有%.3fs 补%.3fs' % (w, tgt, cur, add))

    if a.report:
        json.dump([dict(cut=t, add=add, word=w, target=tgt, cur=cur)
                   for t, add, w, tgt, cur in plan],
                  open(a.report, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
