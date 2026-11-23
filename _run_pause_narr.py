# -*- coding: utf-8 -*-
"""旁白 716 条三档停顿注入 runner（2026-11-16 02:2x）。

为什么要有这个 wrapper：--only 要 716 个 id 拼成逗号串（约 5.7KB），
直接写命令行贴着 8191 上限，一旦加参数就炸；这里从 _narr_ids716.json 读。

用法（cwd 必须是 G:/_setup）：
    G:/Python310/python.exe -u _run_pause_narr.py
"""
import json
import os
import sys

BASE = r'G:/_setup'
OUT = r'G:/_setup/_audio_ch123/out_paused_narr'

ids = json.load(open(os.path.join(BASE, '_narr_ids716.json'), encoding='utf-8'))
ids = [str(i) for i in dict.fromkeys(ids)]          # 去重但保序
print('[runner] narrator ids = %d -> %s' % (len(ids), OUT), flush=True)

sys.argv = [
    'mt_final_pause.py',
    '--in', os.path.join(BASE, '_audio_ch123', 'out'),
    '--out', OUT,
    '--llm', os.path.join(BASE, 'pause_llm_narr_v3.json'),
    '--texts', os.path.join(BASE, '_narr_plan_for_pause.jsonl'),
    '--who', 'narrator',
    '--bed-self',                      # 底噪取自本条静音段，避免数字零（REQUIREMENTS 25a）
    '--only', ','.join(ids),
    '--report', os.path.join(BASE, '_pause_narr_report.json'),
]

src = open(os.path.join(BASE, 'mt_final_pause.py'), encoding='utf-8').read()
g = {'__name__': '__main__', '__file__': os.path.join(BASE, 'mt_final_pause.py')}
exec(compile(src, 'mt_final_pause.py', 'exec'), g)
