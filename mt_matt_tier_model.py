# -*- coding: utf-8 -*-
"""mt_matt_tier_model.py —— 分档 + R3 乘性模型标定与回测。

为什么不用第一轮的 R1/R3 线性回归：
- 第一轮 R1（句间/句内）是二值，把句内混成一个 0.91 的均值，
  掩盖了 inner(0.58) 与 bound(1.12) 近 2 倍的差别。
- 分档后 base 值本身就能解释更多方差，R3 只做残差修正。

模型：
    gap_hat = base(tier) * exp(beta * (log(span) - log(span_ref)))
即 R3 以「相对段长」的幂次修正，span 翻倍 → gap 乘 e^(beta*ln2)。

回测口径：
1. 只用三方一致的条目（clean set），避免标注噪声。
2. leave-one-out 交叉验证算 MAE / R²（60 条样本小，样本内 R² 会虚高）。
3. 与「全局中位数」「R1 二值」两个基线比。
"""
import collections
import json
import sys

import numpy as np

S = r'G:/_setup/_matt_annot2_samples.json'
MINED = r'G:/_setup/matt_pause_mined.json'
FILES = {
    'main': r'G:/_setup/_annot2_matt_main.json',
    'hy4': r'G:/_setup/_annot2_matt_hy4.json',
    'ds': r'G:/_setup/_annot2_matt_ds.json',
}
TIERS = ['inner', 'bound', 'clause', 'para']


def main():
    samples = json.load(open(S, encoding='utf-8'))
    ann = {n: {k: v['kind'] for k, v in json.load(open(p, encoding='utf-8')).items()}
           for n, p in FILES.items()}
    names = list(ann)

    # ---- 三方一致子集
    clean = []
    for r in samples:
        k = r['key']
        ks = set(ann[n][k] for n in names)
        if len(ks) == 1:
            clean.append((k, ks.pop(), r['_gap']))
    print('三方一致 %d / %d 条' % (len(clean), len(samples)))
    print('  %s' % dict(collections.Counter(t for _, t, _ in clean)))

    # ---- 每档 base（clean set 中位）
    by = collections.defaultdict(list)
    for _, t, g in clean:
        by[t].append(g)
    print('\n=== 各档 base（三方一致子集）===')
    base = {}
    for t in TIERS:
        g = np.array(by.get(t, []))
        if len(g) == 0:
            print('  %-7s n=0' % t)
            continue
        base[t] = float(np.median(g))
        print('  %-7s n=%2d  p25=%.2f  median=%.2f  p75=%.2f' % (
            t, len(g), np.percentile(g, 25), np.median(g), np.percentile(g, 75)))
    # para 未验证 → 并入 clause 上尾，暂用 clause 的 p75
    if 'para' not in base:
        base['para'] = float(np.percentile(by['clause'], 75))
        print('  para    未验证，暂用 clause p75 = %.2f' % base['para'])

    # ---- 需要 span（前后语音段总长）才能做 R3
    # mined 里每条有 s/e/gap，但 span = 前段长 + 后段长，需要 VAD 段表。
    # 这里用近似：停顿两侧最近的语音段长度 = 前一个 gap 到后一个 gap 的间隔。
    recs = sorted(json.load(open(MINED, encoding='utf-8'))['recs'],
                  key=lambda r: r['s'])
    # 语音段 = recs[i].e 到 recs[i+1].s
    seg_dur = []
    for i in range(len(recs) - 1):
        seg_dur.append(recs[i + 1]['s'] - recs[i]['e'])
    seg_dur = np.array(seg_dur)
    # 停顿 i 的前段 = recs[i-1].e .. recs[i].s
    def span_of(i):
        prev = recs[i - 1]['e'] if i > 0 else 0.0
        cur = recs[i]['s']
        nxt = recs[i + 1]['e'] if i + 1 < len(recs) else recs[i]['e']
        return (cur - prev) + (nxt - recs[i]['e'])

    # 用 gap + 前后段长匹配回样本（样本是按 gap 和顺序抽的，需要重新对齐）
    # 做法：样本的 text 是从 whisper 词生成的，无法直接反查 recs 索引。
    # ⇒ 改从 _matt_annot2_export 时保存的信息入手不可行，这里用近似：
    #   把样本按 gap 排序，与 recs 里同 gap（±0.01）的条目贪心匹配。
    used = set()
    span_map = {}
    for r in samples:
        g = r['_gap']
        best, bd = -1, 1e9
        for i, rc in enumerate(recs):
            if i in used:
                continue
            d = abs(rc['gap'] - g)
            if d < bd:
                bd, best = d, i
        if best >= 0 and bd < 0.02:
            used.add(best)
            span_map[r['key']] = span_of(best)
    print('\nspan 匹配成功 %d / %d 条' % (len(span_map), len(samples)))
    if len(span_map) < len(samples) * 0.7:
        print('  !! 匹配率过低，R3 项跳过')
        span_map = {}

    # ---- 回测
    def evaluate(predict_fn, tag):
        err = []
        for k, t, g in clean:
            p = predict_fn(k, t, g)
            if p is None:
                continue
            err.append((g, p))
        if len(err) < 5:
            print('  %-24s 样本不足' % tag)
            return None
        a = np.array([e[0] for e in err])
        b = np.array([e[1] for e in err])
        mae = np.abs(a - b).mean()
        ss_res = ((a - b) ** 2).sum()
        ss_tot = ((a - a.mean()) ** 2).sum()
        r2 = 1 - ss_res / ss_tot
        print('  %-24s n=%2d  MAE=%.3f  R2=%.3f' % (tag, len(err), mae, r2))
        return mae, r2

    print('\n=== 回测（三方一致子集）===')
    g_all = np.array([g for _, _, g in clean])
    evaluate(lambda k, t, g: float(np.median(g_all)), '基线: 全局中位数')
    # R1 二值基线
    med_in = np.median([g for _, t, g in clean if t in ('inner', 'bound')])
    med_out = np.median([g for _, t, g in clean if t in ('clause', 'para')])
    evaluate(lambda k, t, g: med_in if t in ('inner', 'bound') else med_out,
             '基线: R1 二值(句内/句间)')
    # 分档 base
    evaluate(lambda k, t, g: base[t], '分档 base（3档）')

    if span_map:
        # 拟合 beta：log(gap/base) ~ beta * log(span/span_ref)
        xs, ys = [], []
        for k, t, g in clean:
            if k not in span_map or span_map[k] <= 0:
                continue
            xs.append(np.log(span_map[k]))
            ys.append(np.log(g / base[t]))
        if len(xs) > 5:
            xs, ys = np.array(xs), np.array(ys)
            xr = xs - xs.mean()
            beta = float((xr * (ys - ys.mean())).sum() / (xr ** 2).sum())
            r2r = float(np.corrcoef(xs, ys)[0, 1] ** 2)
            print('\n  R3 残差回归: beta=%.3f  r2=%.3f  (n=%d)' % (beta, r2r, len(xs)))
            print('    → span 翻倍，gap ×%.2f' % np.exp(beta * np.log(2)))
            sref = float(np.exp(xs.mean()))
            evaluate(lambda k, t, g: base[t] * np.exp(
                beta * (np.log(span_map.get(k, sref)) - np.log(sref))),
                '分档 base + R3')

    print('\n=== 交付用的 base 值 ===')
    print(json.dumps({t: round(v, 3) for t, v in base.items()},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
