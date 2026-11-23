# -*- coding: utf-8 -*-
"""韵律对比试听页：原声 / 生成 / 移植 / 移植+句末延长

离线单文件、音频内嵌（mp3 base64）。
"""
import base64
import html
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, r'G:/_setup')
from prosody_arc import analyze  # noqa: E402

FFMPEG = r'E:/tool/oopz/ffmpeg.exe'
SP = '▁▂▃▄▅▆▇█'


def spark(vals):
    if not vals:
        return ''
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-6:
        return SP[3] * len(vals)
    return ''.join(SP[int(round((v - lo) / (hi - lo) * 7))] for v in vals)


def mp3_b64(wav):
    tmp = tempfile.mktemp(suffix='.mp3')
    subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error',
                    '-i', wav, '-codec:a', 'libmp3lame', '-b:a', '96k', tmp],
                   check=True)
    with open(tmp, 'rb') as f:
        data = f.read()
    os.remove(tmp)
    return base64.b64encode(data).decode('ascii')


def summarize(wav):
    """取最长短语段的轮廓统计。"""
    r = analyze(wav)
    if not r['segs']:
        return None
    s = max(r['segs'], key=lambda x: x['dur'])
    return dict(dur=r['dur'], span=s['span_st'], std=s['std_st'],
                prof=s['prof'], tail=s['tail_slope_st_s'], arc=s['arc_st'],
                f0=s['f0_med'], seg_dur=s['dur'])


GROUPS = [
    # (组名, 说明, [(标签, wav, 备注), ...])
]

PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>韵律移植对比</title>
<style>
:root{--bg:#12141a;--card:#1b1e26;--fg:#e8eaf0;--dim:#9aa3b2;--ac:#5cc8ff;--good:#39d98a;--warn:#ffb454;--star:#ffd166}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;padding:20px 16px 60px}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:22px;line-height:1.7}
.grp{margin:26px 0 10px;font-size:16px;font-weight:600;border-left:3px solid var(--ac);padding-left:10px}
.gnote{color:var(--dim);font-size:12.5px;margin:0 0 12px 13px}
.card{background:var(--card);border-radius:12px;padding:13px 15px;margin:9px 0;border:1px solid #262a35}
.card.real{border-color:#3a4a63}
.card.best{border-color:var(--star);box-shadow:0 0 0 1px rgba(255,209,102,.25)}
.tt{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:5px}
.nm{font-weight:600}
.tag{font-size:11.5px;padding:1px 7px;border-radius:20px;background:#2a2f3d;color:var(--dim)}
.tag.star{background:rgba(255,209,102,.16);color:var(--star)}
.meta{font-size:12.5px;color:var(--dim);font-family:ui-monospace,Menlo,Consolas,monospace;margin:4px 0 7px;word-break:break-all}
.spark{font-size:15px;letter-spacing:1px;color:var(--ac)}
audio{width:100%;height:34px;margin-top:3px}
table{width:100%;border-collapse:collapse;margin:10px 0 4px;font-size:13px}
th,td{padding:6px 7px;border-bottom:1px solid #262a35;text-align:left}
th{color:var(--dim);font-weight:500;font-size:12px}
td.num{font-family:ui-monospace,Menlo,Consolas,monospace;text-align:right}
.big{font-weight:700;color:var(--good)}
.hint{color:var(--dim);font-size:12.5px;margin-top:18px;line-height:1.75}
code{background:#22262f;padding:1px 5px;border-radius:4px;font-size:12.5px}
</style></head><body><div class="wrap">
<h1>{{TITLE}}</h1>
<div class="sub">{{HEAD}}</div>
{{BODY}}
<div class="hint">{{HINT}}</div>
</div></body></html>"""


def card(label, wav, note, cls='', tag=''):
    st = summarize(wav)
    if st is None:
        return ''
    meta = ('时长 %.2fs · F0 %.0fHz · 跨度 <b>%.2f</b>半音 · 起伏 %.2f · 末斜率 %+.1f st/s'
            % (st['dur'], st['f0'], st['span'], st['std'], st['tail']))
    sp = spark(st['prof'])
    t = '<span class="tag %s">%s</span>' % ('star' if cls == 'best' else '', tag) if tag else ''
    nt = '<div class="meta">%s</div>' % note if note else ''
    return ('<div class="card %s"><div class="tt"><span class="nm">%s</span>%s</div>'
            '%s<div class="meta">%s</div><div class="spark">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (cls, html.escape(label), t, nt, meta, sp, mp3_b64(wav)))


def main():
    import json
    spec = json.load(open(sys.argv[1], encoding='utf-8'))
    out = sys.argv[2]

    body = []
    for g in spec['groups']:
        body.append('<div class="grp">%s</div>' % html.escape(g['name']))
        if g.get('note'):
            body.append('<div class="gnote">%s</div>' % html.escape(g['note']))
        for it in g['items']:
            if not os.path.exists(it['wav']):
                body.append('<div class="card"><div class="tt"><span class="nm">%s</span>'
                            '<span class="tag">缺失</span></div></div>' % html.escape(it['label']))
                continue
            body.append(card(it['label'], it['wav'], it.get('note', ''),
                             it.get('cls', ''), it.get('tag', '')))
    hint = spec.get('hint', '<b>看什么：</b>「轮廓」是句级 F0 弧线（半音，21 点，时间 0→100%），'
                            '「跨度」= P95−P5 半音，「末斜率」= 句末 300ms 走向（正=上扬）。<br>'
                            '生成端原始轮廓常是<b>对称拱形</b>（模型默认语调），移植后应变成原声那种'
                            '<b>不规则、带句中突出与句末走向</b>的形状。')
    htmlstr = (PAGE.replace('{{TITLE}}', spec.get('title', '韵律移植对比'))
                   .replace('{{HEAD}}', spec.get('head', ''))
                   .replace('{{HINT}}', hint)
                   .replace('{{BODY}}', '\n'.join(body)))
    with open(out, 'w', encoding='utf-8') as f:
        f.write(htmlstr)
    print('写出 %s  (%.2f MB)' % (out, os.path.getsize(out) / 1048576))


if __name__ == '__main__':
    main()
