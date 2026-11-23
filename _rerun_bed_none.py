# -*- coding: utf-8 -*-
"""补跑：把主轮里「测不出自底噪」的条目用补丁后的代码重做一遍。

背景：2026-11-16 02:2x 启动主轮时，`mt_final_pause.py` 在 `bed_from_self()` 返回 None
时是「不铺底噪」⇒ 停顿处插**数字零**，违反 REQUIREMENTS 25a。
打完补丁（改铺 room_tone_panel.wav）后主轮进程仍在跑旧代码，所以要按日志挑出来重做。
重做写入同一个输出目录，文件名相同，直接覆盖。

用法（cwd = G:/_setup，主轮跑完之后）：
    G:/Python310/python.exe -u _rerun_bed_none.py
    G:/Python310/python.exe -u _rerun_bed_none.py --log _pause_narr_run.log --dry
"""
import argparse
import os
import re
import sys

BASE = r'G:/_setup'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', default=os.path.join(BASE, '_pause_narr_run.log'))
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    ids, seen = [], set()
    for ln in open(a.log, encoding='utf-8', errors='replace'):
        if '纹理none' not in ln:
            continue
        m = re.match(r'^(c\d_\d{4})\b', ln.strip())
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            ids.append(m.group(1))
    print('[rerun] 日志里测不出自底噪的条目：%d 条' % len(ids))
    if not ids:
        return 0
    if a.dry:
        print('  前 10 条：', ids[:10])
        return 0

    sys.argv = [
        'mt_final_pause.py',
        '--in', os.path.join(BASE, '_audio_ch123', 'out'),
        '--out', os.path.join(BASE, '_audio_ch123', 'out_paused_narr'),
        '--llm', os.path.join(BASE, 'pause_llm_narr_v3.json'),
        '--texts', os.path.join(BASE, '_narr_plan_for_pause.jsonl'),
        '--who', 'narrator',
        '--bed-self',
        '--only', ','.join(ids),
        '--report', os.path.join(BASE, '_pause_narr_report_bedfix.json'),
    ]
    src = open(os.path.join(BASE, 'mt_final_pause.py'), encoding='utf-8').read()
    exec(compile(src, 'mt_final_pause.py', 'exec'),
         {'__name__': '__main__', '__file__': os.path.join(BASE, 'mt_final_pause.py')})


if __name__ == '__main__':
    sys.exit(main())
