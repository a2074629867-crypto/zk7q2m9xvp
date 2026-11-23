# -*- coding: utf-8 -*-
'''_ann_reprompt.py -- 只换任务包里的 prompt 字段，items / batch / track 原样不动。

为什么不用重新 build：build 会重新分批发号，已跑的 pilot 产物就全对不上号了。
用法：python _ann_reprompt.py            # 改写 _ann/tasks_tier_full 全部批次
     python _ann_reprompt.py --dry   # 只看改了什么
'''
import glob
import json
import os
import shutil
import sys

ROOT = 'G:/_setup'
sys.path.insert(0, ROOT)
from ann_spec import prompt_for  # noqa: E402

TASKS = os.path.join(ROOT, '_ann', 'tasks_tier_full')
BAK = os.path.join(ROOT, '_ann', 'tasks_tier_full.bak_reprompt')


def main():
    dry = '--dry' in sys.argv
    files = sorted(glob.glob(os.path.join(TASKS, 'batch_*.json')))
    if not files:
        print('没找到任务包')
        return 1
    if not dry and not os.path.isdir(BAK):
        shutil.copytree(TASKS, BAK)
        print('已备份 ->', BAK)

    changed = 0
    by_track = {}
    for fp in files:
        d = json.load(open(fp, encoding='utf-8'))
        trk = d.get('track', 'narr')
        new = prompt_for(trk, d.get('mode', 'tier') == 'tier')
        if d.get('prompt') == new:
            continue
        changed += 1
        by_track[trk] = by_track.get(trk, 0) + 1
        if not dry:
            d['prompt'] = new
            json.dump(d, open(fp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('%s 改写 %d / %d 批  %s' % ('[dry]' if dry else '[done]', changed, len(files), by_track))
    # 抽验
    d = json.load(open(os.path.join(TASKS, 'batch_0001.json'), encoding='utf-8'))
    p = d['prompt']
    print('batch_0001 track=%s len=%d' % (d['track'], len(p)))
    for k in ('能不能独立成小句', 'after a second stroke', '命中第一条就停'):
        print('  含「%s」: %s' % (k, k in p))
    print('  items 未变: %d 条, items[0].sid=%s' % (len(d['items']), d['items'][0]['sid']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
