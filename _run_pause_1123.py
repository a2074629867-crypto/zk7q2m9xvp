# -*- coding: utf-8 -*-
"""旁白 716 条三档停顿注入（新库版，2026-11-23）。

与 `_run_pause_narr.py` 唯一差别：输入换成新标准重生成的干声 `_regen_1123/`，
输出写 `_regen_1123_paused/`，**不覆盖** `_audio_ch123/out_paused_narr`（现役页仍指着它）。

为什么要 wrapper：--only 要 716 个 id 拼成约 5.7KB 的逗号串，直接写命令行贴 8191 上限，
再加参数就炸；这里从 `_narr_ids716.json` 读。

三档口径（REQUIREMENTS，旁白专用）：
    inner 0.51s / bound 1.135s / clause 1.695s
停顿处**不许数字零**，底噪取自本条静音段（`--bed-self`）。

用法（cwd 必须是 G:/_setup）：
    G:/Python310/python.exe -u _run_pause_1123.py
"""
import json
import os
import sys

BASE = r'G:/_setup'
IN = os.path.join(BASE, '_regen_1123')
OUT = os.path.join(BASE, '_regen_1123_paused')

ids = json.load(open(os.path.join(BASE, '_narr_ids716.json'), encoding='utf-8'))
ids = [str(i) for i in dict.fromkeys(ids)]
if '--only' in sys.argv:
    # ★ 显式 --only 时不再与 716 集求交：历史缺口那 10 句（带内嵌引号）本来就不在 716 里，
    #   求交会把它们过滤成空集。
    k = sys.argv.index('--only')
    ids = [x.strip() for x in sys.argv[k + 1].split(',') if x.strip()]
    del sys.argv[k:k + 2]
print('[runner-1123] narrator ids = %d -> %s' % (len(ids), OUT), flush=True)

sys.argv = [
    'mt_final_pause.py',
    '--in', IN,
    '--out', OUT,
    '--llm', os.path.join(BASE, 'pause_llm_narr_v3.json'),
    '--texts', os.path.join(BASE, '_narr_plan_for_pause.jsonl'),
    '--who', 'narrator',
    '--bed-self',
    '--only', ','.join(ids),
    '--report', os.path.join(BASE, '_pause_regen1123_report.json'),
]

src = open(os.path.join(BASE, 'mt_final_pause.py'), encoding='utf-8').read()
g = {'__name__': '__main__', '__file__': os.path.join(BASE, 'mt_final_pause.py')}
exec(compile(src, 'mt_final_pause.py', 'exec'), g)
