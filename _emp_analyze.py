# -*- coding: utf-8 -*-
"""_emp_analyze.py —— EmphaClass 全量结果分析（旁白 716）

口径铁律（2026-11-14 首批 120 条得出）：
  emph_rate 有强时长伪影（rho=-0.62），**不得跳句比较**。
  候选筛选只在 >=MIN_DUR 秒的句子里做，并把每词强调帧数校准掉。
"""
import json, statistics as st, csv, argparse

MIN_DUR = 5.0
LOW_PER_WORD = 2.0


def load(emp_p, phys_p):
    emp = {x['id']: x for x in json.load(open(emp_p, encoding='utf-8'))}
    phys = {x['id']: x for x in json.load(open(phys_p, encoding='utf-8'))}
    rows = []
    for u, e in emp.items():
        p = phys.get(u)
        if not p:
            continue
        ef = sum(1 for v in e['p'] if v > 0.5)
        rows.append(dict(
            unit=u, dur=e['dur'], words=p.get('words') or 0, wpm=p.get('wpm'),
            verdict=p.get('verdict'), frames=e['frames'], emph_frames=ef,
            emph_rate=e['emph_rate'],
            per_word=(ef / p['words']) if p.get('words') else None))
    return rows


def q(v, p):
    v = sorted(v)
    return v[int(p * (len(v) - 1))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--emp', default='G:/_setup/_emp_narr_all.json')
    ap.add_argument('--phys', default='G:/_setup/_narr_phys.json')
    ap.add_argument('--out', default='G:/_setup/_emp_narr_all_report.md')
    ap.add_argument('--csv', default='G:/_setup/_emp_narr_all.csv')
    a = ap.parse_args()

    rows = load(a.emp, a.phys)
    print('n =', len(rows))
    er = [r['emph_rate'] for r in rows]
    print('emph_rate 中位 %.3f  q1 %.3f  q3 %.3f  min %.3f  max %.3f' % (
        st.median(er), q(er, .25), q(er, .75), min(er), max(er)))

    with open(a.csv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    long = [r for r in rows if r['dur'] >= MIN_DUR and r['words']]
    print('>=%.0fs 的句子 %d 条' % (MIN_DUR, len(long)))
    pw = [r['per_word'] for r in long]
    thr = q(pw, .10)
    print('>=%.0fs 内 每词强调帧 p10 = %.2f（候选线）' % (MIN_DUR, thr))

    cand = sorted([r for r in long if r['per_word'] <= max(LOW_PER_WORD, thr)],
                  key=lambda r: r['per_word'])[:40]
    zero = [r for r in rows if r['emph_frames'] == 0]
    print('零强调 %d 条；候选 %d 条' % (len(zero), len(cand)))

    lines = ['# EmphaClass 全量 %d 条结果\n' % len(rows),
             '## 分布\n',
             '| 量 | 值 |', '|---|---|',
             '| n | %d |' % len(rows),
             '| emph_rate 中位 | %.3f |' % st.median(er),
             '| q1 / q3 | %.3f / %.3f |' % (q(er, .25), q(er, .75)),
             '| min / max | %.3f / %.3f |' % (min(er), max(er)),
             '| 零强调 | %d 条 |' % len(zero), '',
             '## 候选（>=%.0fs，每词强调帧 <= %.2f）\n' % (MIN_DUR, max(LOW_PER_WORD, thr)),
             '| unit | 时长 | 词数 | wpm | 每词强调帧 | emph_rate | 物理闸 |',
             '|---|---|---|---|---|---|---|']
    for r in cand[:25]:
        lines.append('| %s | %.2fs | %d | %.0f | %.2f | %.3f | %s |' % (
            r['unit'], r['dur'], r['words'], r['wpm'] or 0, r['per_word'],
            r['emph_rate'], r['verdict']))
    open(a.out, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('报告 ->', a.out, '| 表 ->', a.csv)


if __name__ == '__main__':
    main()
