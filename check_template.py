# -*- coding: utf-8 -*-
"""check_template.py —— 验证模板注入是否生效：测量音频的词级轮廓并与模板对比。

用法: python -u check_template.py <wav> [<wav2> ...]
"""
import json
import sys

import numpy as np

sys.path.insert(0, 'G:/_setup')
from transplant_prosody2 import word_times, f0_points  # noqa: E402
from apply_predicted import sentence_split, pick_template, load_template  # noqa: E402

TM = load_template()


def word_prof(rt, rf, s, e, bins=5):
    m = (rt >= s) & (rt <= e)
    if m.sum() < 3:
        return None
    tt, ff = rt[m], rf[m]
    u = (tt - tt[0]) / max(tt[-1] - tt[0], 1e-6)
    return np.interp(np.linspace(0, 1, bins), u, ff)


def main():
    for wav in sys.argv[1:]:
        rt, rf = f0_points(wav)
        rw = word_times(wav)
        print('==== %s  词数 %d ====' % (wav, len(rw)))
        for si, sent in enumerate(sentence_split(rw)):
            t0, t1 = sent[0][0], sent[-1][1]
            sm = (rt >= t0) & (rt <= t1)
            if sm.sum() < 5:
                continue
            r_med = float(np.median(rf[sm]))
            print(' 句%d [%.2f-%.2f] n=%d  med=%.1fHz' % (si + 1, t0, t1, len(sent), r_med))
            for i, (s, e, txt) in enumerate(sent):
                f5 = word_prof(rt, rf, s, e)
                tail = txt.strip()[-1:]
                tmpl = pick_template(TM, i, len(sent), tail)
                if f5 is None:
                    print('   %-12s (无浊音)' % txt)
                    continue
                st = 12 * np.log2(f5 / r_med)
                tm = np.asarray(tmpl)
                dev = st - tm
                print('   %-14s 实测 %s | 模板 %s | 均偏 %+.2f' % (
                    txt[:14], ' '.join('%+.1f' % x for x in st),
                    ' '.join('%+.1f' % x for x in tm), float(dev.mean())))


if __name__ == '__main__':
    main()
