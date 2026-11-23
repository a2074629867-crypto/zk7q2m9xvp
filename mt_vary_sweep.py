# -*- coding: utf-8 -*-
"""mt_vary_sweep.py —— 扫 (shape_alpha, vary_sigma)，按「跨度是否接近真人」选参数。

为什么不用生成音频来比：插多少、留给谁，在 plan 阶段就定了；
`--dry` 的输出里 `bounds.after` 就是最终的 gap 目标值，误差只来自切点 ±1 帧。
真/假对比用相对跨度（IQR/中位），因为两边语速不同，绝对值不可比。

真人基准（马修母带标点级）：句号 IQR/中位 = 0.34，逗号 0.58。

用法: python mt_vary_sweep.py
"""
import json
import os
import subprocess
import sys

import numpy as np

PY = r'G:/Python310/python.exe'
HUMAN = {'.': 0.34, ',': 0.58}
GRID = [(0.0, 0.27), (0.0, 0.20), (0.4, 0.18), (0.6, 0.10), (0.8, 0.10),
        (1.0, 0.08), (1.0, 0.00), (0.6, 0.00)]


def run(alpha, sigma):
    out = r'G:/_setup/_tiers_probe.json'
    cmd = [PY, '-u', 'mt_final_pause.py', '--dry', '--out', r'G:/_setup/_vary_probe',
           '--shape-alpha', str(alpha), '--vary', str(sigma), '--report', out]
    env = os.environ.copy()
    env['HF_HOME'] = r'C:/Users/86178/.cache/huggingface'
    env['HF_HUB_OFFLINE'] = '1'
    r = subprocess.run(cmd, cwd=r'G:/_setup', capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(r.stderr[-800:])
        return None
    rows = json.load(open(out, encoding='utf-8'))
    gaps = []
    for x in rows:
        for b in (x.get('bounds') or []):
            if b['op'] == 'ins':
                gaps.append((b['after'], b['tier']))
    return gaps


def stats(gaps):
    """按档位分组算相对跨度 —— 混在一起算会把「档位差」当成「同档抖动」。"""
    res = {}
    for tier in sorted(set(t for _, t in gaps)):
        v = np.array([g for g, t in gaps if t == tier])
        if len(v) < 4:
            continue
        med = float(np.median(v))
        iqr = float(np.percentile(v, 75) - np.percentile(v, 25))
        res[tier] = (len(v), med, iqr / med if med else 0.0, float(v.max()))
    return res


def main():
    print('真人基准：句号 IQR/中位 0.34；逗号 0.58（马修母带，n=234/136）')
    print()
    print('%-6s %-6s %-10s %4s %6s %9s %6s' % ('alpha', 'sigma', '档位', 'n', '中位', 'IQR/中位', 'max'))
    for a, s in GRID:
        g = run(a, s)
        if not g:
            print('%.1f    %.2f   FAIL' % (a, s))
            continue
        res = stats(g)
        for i, (tier, (n, med, rel, mx)) in enumerate(sorted(res.items(),
                                                             key=lambda kv: -kv[1][0])):
            flag = ''
            if tier == 'dot_inner' and abs(rel - HUMAN['.']) < 0.06:
                flag = ' ← 命中句号 0.34'
            print(('%-6.1f' if i == 0 else '%-6s') % (a if i == 0 else '')
                  + (' %-6.2f' if i == 0 else ' %-6s') % (s if i == 0 else '')
                  + ' %-10s %4d %6.2f %9.2f %6.2f%s'
                  % (tier, n, med, rel, mx, flag))
        print()


if __name__ == '__main__':
    main()
