# -*- coding: utf-8 -*-
"""apply_predicted.py —— 无 donor 场景的韵律注入，两种模式：

1) --pred pred.json   模型预测的逐词轮廓（路线 A，实测泛化提升≈0，保留作对照）
2) --template         词位模板（从 Wonder 真实录音统计：句首高开 +1.57 → 句末 -0.07 的
                      句级下降弧线；逗号词尾段上扬）。无需 donor、无需训练，纯统计注入。

流程：whisper 词时间轴对齐 -> 按句切分 -> 逐词展开 5 点模板 -> 平滑
      -> PitchTier 替换（Praat overlap-add 重合成）

用法:
  python -u apply_predicted.py --recv gen.wav --template --out out.wav --alpha 0.8 --gain 1.0
  python -u apply_predicted.py --recv gen.wav --pred pred.json --out out.wav --alpha 1.0
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, 'G:/_setup')
from transplant_prosody2 import f0_points, word_times, write_pitchtier, resynth  # noqa: E402
from prosody_model_a import clean as _clean  # noqa: E402
from difflib import SequenceMatcher  # noqa: E402

TEMPLATE_PATH = 'G:/_setup/route_a/word_template.json'


def load_template(path=TEMPLATE_PATH):
    t = json.load(open(path, encoding='utf-8'))
    for k in ('word_first', 'word_mid', 'word_last', 'word_comma'):
        if k not in t:
            raise SystemExit('模板缺少 %s: %s' % (k, path))
    return t


def sentence_split(rw):
    """rw: [(s,e,text)] -> [sentence_words, ...]，按句末标点 .!? 切分。"""
    sents, cur = [], []
    for item in rw:
        cur.append(item)
        t = item[2].strip()
        if t and t[-1] in '.!?':
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    return sents


def pick_template(tmpl, i, n, tail):
    if i == 0:
        return tmpl['word_first']['st']
    if i == n - 1:
        if tail in '.!?':
            return tmpl['word_last']['st']
        return tmpl['word_comma']['st']
    if tail == ',':
        return tmpl['word_comma']['st']
    q = 1 + min(2, int(3.0 * i / max(1, n)))
    return tmpl.get('mid_q%d' % q, tmpl['word_mid'])['st']


def _smooth_inplace(rt, st, mask, smooth, step):
    n = len(rt)
    if smooth <= 0 or mask.sum() < 3:
        return st
    w = max(1, int(smooth / step))
    if w < 3:
        return st
    k = np.hanning(w)
    k /= k.sum()
    pad = w // 2
    sm = np.convolve(np.pad(st, pad, mode='edge'), k, mode='valid')[:n]
    bl = np.convolve(np.pad(mask.astype(float), pad, mode='edge'), k, mode='valid')[:n]
    return np.where(bl > 0.5, sm, st)


def build_from_template(rt, rf, rw, tmpl, alpha=1.0, gain=1.0, smooth=0.10, step=0.01,
                        mode='rank', mix='add'):
    """逐句按词位模板注入句级弧线（相对句内中位，去全局均值后叠加）。

    mode='rank'  帧序百分位把词内浊音帧序列映射到 5 点模板（推荐，免疫词边界误差）
    mode='mean'  每词一个偏移（模板 5 点均值）——最保守
    mode='shape' 逐点按词内时间插值 5 点形状——需精确词边界
    mix='add'    原轮廓 + α·模板偏移（保留生成端自身起伏）
    mix='replace' (1-α)·原轮廓 + α·模板偏移（α=1 为纯模板形状）
    """
    gmean = float(tmpl['global_mean'])
    st_out = 12.0 * np.log2(rf / float(np.median(rf)))
    hit = np.zeros(len(rt), dtype=bool)
    n_sent = 0
    for sent in sentence_split(rw):
        t0 = sent[0][0]
        t1 = sent[-1][1]
        smask = (rt >= t0) & (rt <= t1)
        if smask.sum() < 5:
            continue
        r_med_s = float(np.median(rf[smask]))
        st_orig = 12.0 * np.log2(rf[smask] / r_med_s)
        st_inc = np.zeros_like(st_orig)          # 模板增量（去全局均值后）
        for i, (ws_, we_, txt) in enumerate(sent):
            tail = txt.strip()[-1:] if txt.strip() else ''
            st5 = np.asarray(pick_template(tmpl, i, len(sent), tail), dtype=np.float64)
            m = (rt[smask] >= ws_) & (rt[smask] <= we_)
            if m.sum() < 2 or we_ - ws_ < 0.05:
                continue
            if mode == 'mean':
                st_inc[m] = float(st5.mean()) - gmean
            elif mode == 'rank':
                # 帧序百分位：把词内浊音帧序列均匀映射到 5 点模板，
                # 不受 whisper 词边界 ±100ms 误差影响
                vi = np.where(m)[0]
                k = len(vi)
                u = (np.arange(k) + 0.5) / k if k > 1 else np.array([0.5])
                st_inc[vi] = np.interp(u, np.linspace(0, 1, len(st5)), st5) - gmean
            else:
                u = (rt[smask][m] - ws_) / max(we_ - ws_, 1e-6)
                st_inc[m] = np.interp(u, np.linspace(0, 1, len(st5)), st5) - gmean
        st_inc = _smooth_inplace(rt[smask], st_inc, np.ones(smask.sum(), dtype=bool), smooth, step)
        if mix == 'replace':
            st_new = (1.0 - alpha) * st_orig + alpha * st_inc
        else:
            st_new = st_orig + alpha * gain * st_inc
        idx = np.where(smask)[0]
        st_out[idx] += (st_new - st_orig)        # 增量叠加到全文件中位基准上
        hit[idx] = True
        n_sent += 1
    r_med = float(np.median(rf))
    f_new = r_med * np.power(2.0, st_out / 12.0)
    return rt, f_new, r_med, int(hit.sum()), n_sent


def load_pred(path):
    """接受两种格式：顶层 list（predict 直接输出）或 {"words":[...]}。"""
    d = json.load(open(path, encoding='utf-8'))
    if isinstance(d, dict):
        d = d.get('words') or d.get('result') or []
    return [w for w in d if w.get('word')]


def match_words(pred, rw, min_ratio=0.75):
    """预测词序列 vs 识别词序列对齐。数量一致直接 zip；否则用 SequenceMatcher 只取共同块。"""
    pw = [_clean(p['word']) for p in pred]
    gw = [_clean(t) for _, _, t in rw]
    if len(pw) == len(gw):
        return list(zip(pred, rw))
    sm = SequenceMatcher(None, pw, gw)
    ratio = sm.ratio()
    if ratio < min_ratio:
        print('[warn] 预测词与识别词差异较大 ratio=%.2f (%d vs %d)' % (ratio, len(pw), len(gw)))
    pairs = []
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            pairs.append((pred[blk.a + k], rw[blk.b + k]))
    return pairs


def build_target(rt, rf, pairs, gain=1.0, smooth=0.12, step=0.01):
    """逐词把预测轮廓展开到 receiver 时间轴。返回 (rt, f_new, med, hit)。"""
    r_med = float(np.median(rf))
    st_src = 12.0 * np.log2(rf / r_med)
    st_tgt = st_src.copy()          # 未命中词保留原样
    hit_mask = np.zeros(len(rt), dtype=bool)
    for p, (rs, re_, _) in pairs:
        pts = np.asarray(p.get('f0_st') or [], dtype=np.float64)
        if len(pts) < 2 or re_ - rs < 0.06:
            continue
        m = (rt >= rs) & (rt <= re_)
        if m.sum() < 2:
            continue
        u = (rt[m] - rs) / max(re_ - rs, 1e-6)
        st_tgt[m] = np.interp(u, np.linspace(0, 1, len(pts)), pts) * gain
        hit_mask[m] = True
    n = len(rt)
    if hit_mask.sum() >= 3:
        # 只在命中区域做平滑，避免把保留区拉过去
        w = max(1, int(smooth / step))
        if w >= 3:
            k = np.hanning(w)
            k /= k.sum()
            pad = w // 2
            x = np.pad(st_tgt, pad, mode='edge')
            sm = np.convolve(x, k, mode='valid')[:n]
            bl = np.pad(hit_mask.astype(float), pad, mode='edge')
            bl = np.convolve(bl, k, mode='valid')[:n]
            st_tgt = np.where(bl > 0.5, sm, st_tgt)
    f_new = r_med * np.power(2.0, st_tgt / 12.0)
    return rt, f_new, r_med, int(hit_mask.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--recv', required=True)
    ap.add_argument('--pred', default='')
    ap.add_argument('--template', action='store_true', help='用词位模板（无需 donor / 预测）')
    ap.add_argument('--template-file', default=TEMPLATE_PATH)
    ap.add_argument('--out', required=True)
    ap.add_argument('--gain', type=float, default=1.0)
    ap.add_argument('--smooth', type=float, default=0.10, help='平滑窗秒数，0 关闭')
    ap.add_argument('--alpha', type=float, default=1.0, help='注入强度；<1 与原轮廓混合')
    ap.add_argument('--mode', default='rank', choices=['rank', 'mean', 'shape'],
                    help='rank=帧序百分位（推荐）；mean=每词一个偏移；shape=按词内时间插值')
    ap.add_argument('--mix', default='add', choices=['add', 'replace'],
                    help='add=叠加模板偏移；replace=按 α 替换为模板形状')
    a = ap.parse_args()
    if not a.template and not a.pred:
        raise SystemExit('需要 --pred 或 --template')

    rt, rf = f0_points(a.recv)
    if len(rf) < 8:
        raise SystemExit('receiver 浊音帧太少: ' + a.recv)
    rw = word_times(a.recv)

    if a.template:
        tmpl = load_template(a.template_file)
        rt, f_new, r_med, hit, n_sent = build_from_template(rt, rf, rw, tmpl,
                                                            alpha=a.alpha, gain=a.gain,
                                                            smooth=a.smooth, mode=a.mode,
                                                            mix=a.mix)
        note = 'template/%s/%s α=%.2f 句=%d' % (a.mode, a.mix, a.alpha, n_sent)
    else:
        pred = load_pred(a.pred)
        if not pred:
            raise SystemExit('预测文件里没有词: ' + a.pred)
        pairs = match_words(pred, rw)
        if len(pairs) < max(3, int(.6 * len(pred))):
            print('[warn] 命中词数偏少: %d / %d' % (len(pairs), len(pred)))
        rt, f_new, r_med, hit = build_target(rt, rf, pairs, a.gain, a.smooth)
        if a.alpha < 1.0:
            st_o = 12.0 * np.log2(rf / r_med)
            st_n = 12.0 * np.log2(f_new / r_med)
            f_new = r_med * np.power(2.0, ((1 - a.alpha) * st_o + a.alpha * st_n) / 12.0)
        note = 'pred α=%.2f' % a.alpha

    work = os.path.dirname(os.path.abspath(a.out)) or '.'
    os.makedirs(work, exist_ok=True)
    pt = os.path.join(work, os.path.splitext(os.path.basename(a.out))[0] + '.PitchTier')
    write_pitchtier(pt, rt, f_new)
    resynth(a.recv, a.out, pt)
    if os.path.exists(pt):
        os.remove(pt)

    st = 12.0 * np.log2(f_new / r_med)
    import parselmouth
    print('[ok] %-24s hit=%d/%d %s 跨度%.2f半音 -> %.2fs  %s' %
          (os.path.basename(a.recv), hit, len(rt), note,
           float(np.percentile(st, 95) - np.percentile(st, 5)),
           parselmouth.Sound(a.out).duration, os.path.basename(a.out)), flush=True)


if __name__ == '__main__':
    main()
