# -*- coding: utf-8 -*-
"""mt_expect_merge.py —— 合成三方判档结果，产出生产链可用的期望表。

产出格式与 pause_llm.json 兼容：
  {seg_id: {pause_idx: {"d": 秒, "tier": "bound", "rel": 1.0, "why": "..."}}}
生产链 mt_final_pause.py 读 d 和 kind；这里额外给 tier 便于追溯。

三方不一致的处理（不许和稀泥）：
- 2:1 → 取多数，标 `_split=True`，并把少数意见记在 `_minor`
- 1:1:1（不可能，只有两档）→ 不会出现
- 全不一致只可能是有人用了非法档位 → 报错并列出

同时算：每句总停顿、全章总停顿占估算语音时长的比例，与马修母带对照。
"""
import argparse
import collections
import json

TIER_BASE = {'inner': 0.51, 'bound': 1.135, 'clause': 1.695, 'para': 1.855}
# 马修母带对照（1615s / 2549 词 / 361 标点）
MATT = dict(dur=1615.0, words=2549, punct=361, pause_total=505.0, pause_pct=0.313)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skel', default=r'G:/_setup/_ch1_expect_skel.json')
    ap.add_argument('--src', default=r'G:/_setup/_ch1_sents.txt')
    ap.add_argument('--ann', nargs='+', default=[
        r'G:/_setup/_ch1_expect_main.json',
        r'G:/_setup/_ch1_expect_hy4.json',
        r'G:/_setup/_ch1_expect_ds.json'])
    ap.add_argument('--out', default=r'G:/_setup/_ch1_pause_expect.json')
    ap.add_argument('--report', default=r'G:/_setup/_ch1_pause_expect.md')
    a = ap.parse_args()

    skel = json.load(open(a.skel, encoding='utf-8'))
    anns = {}
    for p in a.ann:
        try:
            anns[p.split('_')[-1].split('.')[0]] = json.load(open(p, encoding='utf-8'))
        except Exception as e:
            print('跳过 %s: %s' % (p, e))
    print('参与合成 %d 方: %s' % (len(anns), list(anns)))
    if not anns:
        raise SystemExit('没有可用的标注文件')

    out = {}
    stat = collections.Counter()
    splits = []
    bad = []
    for sid, items in skel.items():
        out[sid] = {}
        for k in items:
            votes = []
            for name, ann in anns.items():
                v = (ann.get(sid) or {}).get(k) or {}
                t = v.get('tier')
                if t in TIER_BASE:
                    votes.append((name, t, v.get('why', '')))
                else:
                    bad.append((sid, k, name, t))
            if not votes:
                continue
            cnt = collections.Counter(v[1] for v in votes)
            tier, n = cnt.most_common(1)[0]
            stat[tier] += 1
            rec = {'tier': tier, 'kind': tier, 'd': round(TIER_BASE[tier], 3),
                   'why': next(v[2] for v in votes if v[1] == tier)}
            if n < len(votes):
                rec['_split'] = True
                rec['_minor'] = [{'by': v[0], 'tier': v[1], 'why': v[2]}
                                 for v in votes if v[1] != tier]
                splits.append((sid, k, tier, n, len(votes)))
            out[sid][k] = rec
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n_pause = sum(len(v) for v in out.values())
    print('合成 %d 句 / %d 逗号  %s' % (len(out), n_pause, dict(stat)))
    print('三方分歧 %d 处 (%.0f%%)' % (len(splits), 100.0 * len(splits) / max(1, n_pause)))
    if bad:
        print('!! 非法档位 %d 条（已丢弃）:' % len(bad))
        for b in bad[:10]:
            print('   ', b)

    # ---- 全章停顿预算
    n_sent = sum(1 for l in open(a.src, encoding='utf-8') if l.startswith('['))
    words = 0
    for l in open(a.src, encoding='utf-8'):
        if l.startswith('['):
            try:
                words += int(l.split('词')[0].split('(')[-1])
            except Exception:
                pass
    t_comma = sum(TIER_BASE[r['tier']] for s in out.values() for r in s.values())
    t_period = n_sent * TIER_BASE['clause']
    total_pause = t_comma + t_period
    wpm = 150.0
    speech = words / wpm * 60
    print('\n=== 全章停顿预算 ===')
    print('  词数 %d，句数 %d，逗号 %d' % (words, n_sent, n_pause))
    print('  逗号停顿 %.0fs + 句号停顿 %.0fs = %.0fs' % (t_comma, t_period, total_pause))
    print('  估算语音 %.0fs（按 %dwpm）' % (speech, wpm))
    print('  停顿占比 %.1f%%' % (100.0 * total_pause / (speech + total_pause)))
    print('  马修母带对照：%.1f%%（%d 词 / %.0fs / %.0fs 停顿）' % (
        MATT['pause_pct'] * 100, MATT['words'], MATT['dur'], MATT['pause_total']))

    # ---- 报告
    L = ['# ch1 停顿期望表\n',
         '三方判档合成（main / hy4 / ds），只判逗号；句末默认 clause。\n',
         '## 统计\n',
         '| 档位 | base(s) | 条数 |', '|---|---|---|']
    for t in ['inner', 'bound', 'clause']:
        L.append('| %s | %.3f | %d |' % (t, TIER_BASE[t], stat.get(t, 0)))
    L += ['', '三方分歧 %d 处（%.0f%%）。分歧项已取多数并在 JSON 里标 `_split`。\n' % (
        len(splits), 100.0 * len(splits) / max(1, n_pause)),
          '## 全章停顿预算\n',
          '- 逗号停顿 %.0fs + 句号停顿 %.0fs = **%.0fs**' % (t_comma, t_period, total_pause),
          '- 估算语音 %.0fs（%dwpm，%d 词）' % (speech, wpm, words),
          '- 停顿占比 **%.1f%%**，马修母带 31.3%%\n' % (100.0 * total_pause / (speech + total_pause))]
    if splits:
        L.append('## 三方分歧明细\n')
        L.append('| 句 | 逗号 | 多数 | 票数 |')
        L.append('|---|---|---|---|')
        for s, k, t, n, tot in splits:
            L.append('| %s | %s | %s | %d/%d |' % (s, k, t, n, tot))
    open(a.report, 'w', encoding='utf-8').write('\n'.join(L))
    print('\n期望表 → %s\n报告 → %s' % (a.out, a.report))


if __name__ == '__main__':
    main()
