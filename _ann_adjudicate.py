# -*- coding: utf-8 -*-
'''_ann_adjudicate.py -- 分歧仲裁：只把三票不一致的槽位单独提出来再判一次。

为什么要这一步：merge 对分歧只标 `_disputed` 不取平均，但弃用 = 丢掉这处停顿。
1646 个槽位里如果有三成分歧，等于 500 处节奏没定。

链路：
  build  从各路产物算出分歧槽位 → _ann/adjudicate/task_XX.json（可直接给一个模型）
  apply  把模型的仲裁结果合并回 pause_ann.jsonl（保留原 votes，写 final_tier）

建 task 时把候选档位和票数都列给仲裁模型，但**不给它看投票模型的 why**，
防止它只是趋着多数走。
'''
import argparse
import glob
import json
import os

ROOT = 'G:/_setup'
TASKS = os.path.join(ROOT, '_ann', 'tasks_tier_full')
ADJ = os.path.join(ROOT, '_ann', 'adjudicate')
ORD = {'zero': 0, 'short': 1, 'mid': 2, 'long': 3}

HEAD = '''你是《The Castle of the King》有声书的中文韵律仲裁员。

下面每一处都是一个**停顿点多模型意见不一致**的个案。你要独立判一次，不靠多数票。

判定用这个阶梯，**按顺序命中第一条就停**：

1. 标点是 `.` `.’` `?` `!` `...`（句末）→ `long`
2. 右段是**插入性补充**（删了句子骨架不变）：说话／思考动词（`, he thought,` `, said Joseph,`）、同位语、括入的介词短语、分词短语、并列形容词 → `short`
3. 右段首词是 and / but / or / yet / for / then，且后面**有谓语**（主语可承前省略）→ `mid`
4. 右段首词是 when / while / if / though / although / because / till / until / since / after / before / as / unless / whether / where → `mid`
5. 右段首词是 which / who / whom / whose / that（关系从句）→ `mid`
6. 右段**能独立成小句**（自己的主谓）→ `mid`
7. 以上都不命中 → `short`

对白轨另有 `zero` 档（连读／口吃中间／纯填充词 Well·Look·then·Oh）。旁白没有 zero。

输出（只输出 JSON）：
{"items":[{"bid":"c1_0003#1","tier":"short","step":2,"why":"介词短语，删去骨架不变"}]}
`bid` 必须原样抄，每个 bid 出现一次。

## 待仲裁
'''


def load_tasks():
    out = {}
    for fp in glob.glob(os.path.join(TASKS, 'batch_*.json')):
        d = json.load(open(fp, encoding='utf-8'))
        out[os.path.basename(fp)] = d
    return out


def slot_index(d):
    """(sid, bid) -> {track, text, left, right, punct, chapter, prev, next}"""
    idx = {}
    for it in d['items']:
        for s in it['slots']:
            idx[(it['sid'], s['bid'])] = {
                'track': d.get('track', 'narr'),
                'text': it['text'],
                'left': s.get('left', ''),
                'right': s.get('right', ''),
                'punct': s.get('punct', ''),
            }
    return idx


def cmd_build(a):
    dirs = a.dirs
    names = [os.path.basename(d.rstrip('/\\')) for d in dirs]
    tasks = load_tasks()

    # 收集各路投票
    votes = {}          # (sid,bid) -> {model: tier}
    for n, d in zip(names, dirs):
        for fp in glob.glob(os.path.join(d, 'batch_*.json')):
            obj = json.load(open(fp, encoding='utf-8'))
            for it in (obj.get('items') if isinstance(obj, dict) else obj) or []:
                for p in (it.get('pause') or []):
                    b = p.get('bid')
                    t = str(p.get('tier') or '').strip().lower()
                    if b and t:
                        votes.setdefault((it['sid'], b), {})[n] = t

    idx = {}
    for _bn, d in tasks.items():
        idx.update(slot_index(d))

    disputed = []
    for key, v in votes.items():
        if len(v) < 2:
            disputed.append((key, v, 'only_one_vote'))
        elif len(set(v.values())) > 1:
            disputed.append((key, v, 'split'))

    disputed.sort(key=lambda x: (x[0][0], int(x[0][1].split('#')[-1]) if '#' in x[0][1] else 0))
    print('槽位总数 %d，分歧 %d（%.1f%%）'
          % (len(votes), len(disputed), 100.0 * len(disputed) / max(1, len(votes))))
    if not disputed:
        return 0

    os.makedirs(ADJ, exist_ok=True)
    for fp in glob.glob(os.path.join(ADJ, 'task_*.json')):
        os.remove(fp)

    chunks = [disputed[i:i + a.chunk] for i in range(0, len(disputed), a.chunk)]
    for ci, chunk in enumerate(chunks, 1):
        items = []
        for (sid, bid), v, why in chunk:
            m = idx.get((sid, bid), {})
            items.append({
                'bid': bid, 'sid': sid, 'track': m.get('track', 'narr'),
                'punct': m.get('punct', ''),
                'left': m.get('left', ''), 'right': m.get('right', ''),
                'text': m.get('text', ''),
                'votes': dict(sorted(v.items())),
                'n_tier': len({t for t in v.values()}),
            })
        p = os.path.join(ADJ, 'task_%03d.json' % ci)
        json.dump({'chunk': ci, 'n': len(items), 'prompt': HEAD, 'items': items},
                  open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('写出 %d 个仲裁包，每包 ≤%d 条 -> %s' % (len(chunks), a.chunk, ADJ))
    return 0


def cmd_apply(a):
    files = sorted(glob.glob(os.path.join(ADJ, 'ans_*.json')))
    if not files:
        print('没有仲裁结果 ans_*.json')
        return 1
    ans = {}
    for fp in files:
        obj = json.load(open(fp, encoding='utf-8'))
        for it in (obj.get('items') if isinstance(obj, dict) else obj) or []:
            b = it.get('bid')
            t = str(it.get('tier') or '').strip().lower()
            if b and t:
                ans[b] = {'tier': t, 'step': it.get('step'), 'why': it.get('why')}
    print('仲裁结果 %d 条' % len(ans))

    src = os.path.join(ROOT, '_ann', 'merged', 'pause_ann.jsonl')
    dst = os.path.join(ROOT, '_ann', 'merged', 'pause_ann.final.jsonl')
    rows = [json.loads(l) for l in open(src, encoding='utf-8') if l.strip()]
    hit = miss = 0
    for r in rows:
        b = r.get('bid')
        if b in ans:
            r['votes'] = r.get('votes')
            r['final_tier'] = ans[b]['tier']
            r['resolved_by'] = 'adjudicate'
            r['adj_step'] = ans[b].get('step')
            hit += 1
        else:
            r['final_tier'] = r.get('tier') or r.get('final_tier')
            r['resolved_by'] = r.get('resolved_by') or 'vote'
            miss += 1
    with open(dst, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('回填 %d，沿用投票 %d -> %s' % (hit, miss, dst))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')
    b = sub.add_parser('build')
    b.add_argument('--dirs', nargs='+', required=True)
    b.add_argument('--chunk', type=int, default=60)
    b.set_defaults(func=cmd_build)
    p = sub.add_parser('apply')
    p.set_defaults(func=cmd_apply)
    a = ap.parse_args()
    if not getattr(a, 'func', None):
        ap.print_help()
        return 1
    return a.func(a)


if __name__ == '__main__':
    raise SystemExit(main())
