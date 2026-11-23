# -*- coding: utf-8 -*-
"""build_review_page.py —— 标注人工审阅页（单文件离线，内嵌 MP3）

给用户逐条过目：
  · 每条切片：时间/时长/词数/首尾静音/文本/音频
  · 顶部「全文连读」区，便于当作故事通读找错词
  · 筛选：全部 / 有标记 / 句中碎片 / 句末无停顿 / 短文本 / 已改动
"""
import base64
import json
import os
import re
import subprocess
import tempfile

import numpy as np
import soundfile as sf

FFMPEG = 'E:/tool/ozip/ffmpeg.exe'
if not os.path.exists(FFMPEG):
    FFMPEG = 'E:/tool/oopz/ffmpeg.exe'

D = 'G:/GPT-SoVITS/_dataset_v5full'
JSON = D + '/review_labels.json'
OUT = 'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_voice_lab/review_labels.html'
SR = 32000


def mp3_b64(wav, bitrate='32k', ar=24000):
    tmp = tempfile.mktemp(suffix='.mp3')
    subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', wav,
                    '-ac', '1', '-ar', str(ar), '-codec:a', 'libmp3lame', '-b:a', bitrate, tmp],
                   check=True)
    data = open(tmp, 'rb').read()
    os.remove(tmp)
    return base64.b64encode(data).decode('ascii')


def main():
    J = json.load(open(JSON, encoding='utf-8'))
    sl = J['slices']
    n = len(sl)
    print('读入 %d 条' % n)

    # 计算「停顿是否真的存在」：本片尾部 + 下一片头部
    for i, r in enumerate(sl):
        nxt_lead = sl[i + 1]['lead'] if i + 1 < n else 0.0
        r['gap'] = round(r['trail'] + nxt_lead, 2)
        t = r['text']
        tags = []
        if not re.search(r'[.?!]$', t):
            tags.append('frag')
        if re.search(r'[.?!]$', t) and r['gap'] < 0.25:
            tags.append('period_no_pause')
        if re.search(r',$', t) and r['gap'] < 0.15:
            tags.append('comma_no_pause')
        if r['nwords'] < 3:
            tags.append('short')
        if r['changed']:
            tags.append('changed')
        r['tags'] = tags

    from collections import Counter
    c = Counter(t for r in sl for t in r['tags'])
    print('标记统计:', dict(c))

    total_words = sum(r['nwords'] for r in sl)
    total_dur = sum(r['dur'] for r in sl)

    # ---- 全文连读 ----
    full = ' '.join(r['text'] for r in sl)
    full = re.sub(r'\s+', ' ', full).strip()

    rows = []
    for r in sl:
        p = os.path.join(D, 'sliced', r['file']).replace('\\', '/')
        if not os.path.exists(p):
            print('  MISS', p)
            continue
        b64 = mp3_b64(p)
        tag_html = ''
        if 'changed' in r['tags']:
            tag_html += '<span class="tg chg">改</span>'
        if 'frag' in r['tags']:
            tag_html += '<span class="tg frag">碎片</span>'
        if 'period_no_pause' in r['tags']:
            tag_html += '<span class="tg pp">句末无停顿</span>'
        if 'comma_no_pause' in r['tags']:
            tag_html += '<span class="tg cp">逗号无停顿</span>'
        if 'short' in r['tags']:
            tag_html += '<span class="tg sh">短</span>'
        cls = ' warn' if r['tags'] else ''
        rows.append(
            '<tr class="r%s" data-tags="%s"><td class="idx">%03d</td>'
            '<td class="tm">%6.2f</td><td class="num">%.2f</td><td class="num">%d</td>'
            '<td class="num sil">%.2f</td><td class="num sil">%.2f</td>'
            '<td class="tx">%s%s</td>'
            '<td class="au"><audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></td></tr>'
            % (cls, ' '.join(r['tags']), r['i'], r['t0'], r['dur'], r['nwords'],
               r['lead'], r['trail'],
               ('<span class="raw">原: %s</span><br>' % r['raw'].replace('<', '&lt;')) if r['changed'] else '',
               r['text'].replace('<', '&lt;'), b64))

    html = TEMPLATE
    html = html.replace('@@STATS@@', STATS % (n, total_words, total_dur / 60, c.get('frag', 0),
                                              c.get('period_no_pause', 0), c.get('comma_no_pause', 0),
                                              c.get('short', 0), c.get('changed', 0)))
    html = html.replace('@@FULL@@', full.replace('<', '&lt;'))
    html = html.replace('@@ROWS@@', '\n'.join(rows))
    open(OUT, 'w', encoding='utf-8').write(html)
    print('WROTE %s  (%.2f MB)  %d 行' % (OUT, os.path.getsize(OUT) / 1024 / 1024, len(rows)))


STATS = """<div class="stats">
  <div class="st"><b>%d</b><span>切片数</span></div>
  <div class="st"><b>%d</b><span>总词数</span></div>
  <div class="st"><b>%.1f</b><span>总时长(分)</span></div>
  <div class="st w"><b>%d</b><span>句中碎片</span></div>
  <div class="st w"><b>%d</b><span>句末无停顿</span></div>
  <div class="st w"><b>%d</b><span>逗号无停顿</span></div>
  <div class="st w"><b>%d</b><span>短文本(&lt;3词)</span></div>
  <div class="st g"><b>%d</b><span>已规范化</span></div>
</div>"""

TEMPLATE = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>标注审阅 · Wonder 全量 465 条</title>
<style>
:root{--bg:#12141a;--card:#1b1e26;--fg:#e8eaf0;--dim:#9aa3b2;--ac:#5cc8ff;--good:#39d98a;--warn:#ffb454;--bad:#ff7b7b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;padding:18px 14px 60px}
.wrap{max-width:1400px;margin:0 auto}
h1{font-size:21px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:14px;line-height:1.8}
.box{background:var(--card);border:1px solid #2b3140;border-radius:10px;padding:12px 15px;margin:0 0 16px;font-size:12.5px;line-height:1.85}
.box b{color:var(--fg)} .box code{background:#22262f;padding:1px 5px;border-radius:4px}
.stats{display:flex;flex-wrap:wrap;gap:9px;margin:0 0 16px}
.st{background:var(--card);border:1px solid #2b3140;border-radius:9px;padding:8px 13px;min-width:92px}
.st b{display:block;font-size:19px;line-height:1.25}
.st span{font-size:11px;color:var(--dim)}
.st.w b{color:var(--warn)} .st.g b{color:var(--good)}
details.full{background:var(--card);border:1px solid #2b3140;border-radius:10px;padding:10px 14px;margin:0 0 16px}
details.full summary{cursor:pointer;font-weight:600;font-size:14px}
details.full pre{white-space:pre-wrap;font:12.5px/1.9 ui-monospace,Menlo,Consolas,monospace;color:#cfd6e2;max-height:340px;overflow:auto;margin:10px 0 0}
.bar{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 12px}
.bar button{background:#22262f;color:var(--fg);border:1px solid #333a48;border-radius:20px;padding:5px 13px;font-size:12.5px;cursor:pointer}
.bar button.on{background:rgba(92,200,255,.18);border-color:var(--ac);color:var(--ac)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:6px 6px;border-bottom:1px solid #232833;vertical-align:middle;text-align:left}
th{color:var(--dim);font-weight:500;font-size:11.5px;position:sticky;top:0;background:#161922;z-index:2}
td.idx{color:var(--dim);font-family:ui-monospace,monospace;width:42px}
td.tm{font-family:ui-monospace,monospace;color:var(--dim);width:58px}
td.num{font-family:ui-monospace,monospace;text-align:right;width:52px}
td.sil{color:#7d8797}
td.tx{line-height:1.65}
td.au{width:230px}
audio{width:220px;height:30px}
tr.warn td.tx{color:#ffe1b3}
tr.r:has(.tg) {background:rgba(255,180,84,.04)}
.tg{display:inline-block;font-size:10.5px;padding:0 6px;border-radius:9px;margin-right:5px;vertical-align:1px}
.tg.frag{background:rgba(154,163,178,.18);color:#aab3c2}
.tg.pp{background:rgba(255,123,123,.16);color:#ff9d9d}
.tg.cp{background:rgba(255,180,84,.16);color:var(--warn)}
.tg.sh{background:rgba(92,200,255,.14);color:var(--ac)}
.tg.chg{background:rgba(57,217,138,.16);color:var(--good)}
.raw{color:#8b93a3;font-size:11.5px}
.hint{color:var(--dim);font-size:12.5px;margin-top:20px;line-height:1.9}
.hint b{color:var(--fg)}
</style></head><body><div class="wrap">
<h1>标注审阅 · Wonder（Calm）全量</h1>
<div class="sub">26.92 分钟原始录音 → 468 段切片 → 整段转写切分 → 465 条标注。请逐条过目，确认无误后我再开始训练。</div>
<div class="box">
<b>这次标注怎么做的（和上一版的关键区别）：</b><br>
① 切片：<code>slice_audio.py -40 2000 300 10 <b>3000</b> 0.9 0.25</code> —— 保留最多 3s 静音，
所以<b>真实停顿被留在训练数据里</b>（旧版 0.5s 会把停顿剪掉，这正是 GSV 输出"停顿不足"的根因）。<br>
② 标注：<b>整段 26.92min 一次性转写</b>（完整上下文），再用切片帧号把文本切回去 ——
而不是逐片独立转写（那会丢大写、把一句切成两片、逗号误判成句号）。<br>
③ 文本规范化：修连字符空格（<code>seven -year -old</code>→<code>seven-year-old</code>）；
数字保留（实测前端自动转词：<code>16</code>→sixteen、<code>187</code>→one hundred eighty-seven）；
撇号保留（<code>Zoe's</code>/<code>weren't</code> 实测正常）。<br>
④ 丢弃 3 条：频谱实测是<b>低频隆隆声</b>（2–8kHz 仅 −84~−89dB，谱质心 215–276Hz，谱平坦度≈0），非语音。<br><br>
<b>已核对</b>：词数守恒 2579/2580（仅 1 词差）；切片内容与原录音相关系数 = 1.000000；0 条重复词；0 条异常字符。
</div>
@@STATS@@
<details class="full"><summary>▸ 展开全文连读（按顺序拼接，可当故事通读找错词）</summary><pre>@@FULL@@</pre></details>
<div class="bar">
  <button class="on" data-f="all">全部</button>
  <button data-f="tagged">有标记</button>
  <button data-f="frag">句中碎片</button>
  <button data-f="period_no_pause">句末无停顿</button>
  <button data-f="comma_no_pause">逗号无停顿</button>
  <button data-f="short">短文本</button>
  <button data-f="changed">已规范化</button>
</div>
<table><thead><tr><th>#</th><th>起点s</th><th>时长</th><th>词</th><th>首静</th><th>尾静</th><th>文本</th><th>试听</th></tr></thead>
<tbody>
@@ROWS@@
</tbody></table>
<div class="hint">
<b>怎么审：</b><br>
1. 先展开「全文连读」，当故事通读一遍 —— <b>错词/漏词最容易在这一步看出来</b>（例如 ASR 把 weaving 听成 weeding）。<br>
2. 再点「有标记」筛选，重点看这几类：<br>
   · <b>句中碎片</b>（灰）：文本不以 .?! 结尾，是被切片边界截断的（占多数，属正常，GSV 官方流程也这样）。<br>
   · <b>句末无停顿</b>（红）：文本以句号结尾，但本片尾部 + 下一片头部静音合计 &lt;0.25s —— 也就是句号处其实没停顿。<br>
   · <b>逗号无停顿</b>（橙）：同理，逗号处没停顿。<br>
   · <b>短文本</b>（蓝）：少于 3 个词。<br>
3. 随机点几条「试听」，对着文本听，确认<b>音频里说的就是这段文字</b>。<br><br>
<b>「首静/尾静」</b> = 该切片首/尾的静音时长（能量法 −35dB）。数值大说明这条带较长的真实停顿。<br>
<b>「已规范化」</b>（绿）：文本被脚本改过，下方会显示原始 ASR 输出供对比。<br><br>
审完告诉我「开始」，我就跑训练（SoVITS v5turbo LoRA ≈ 23 分钟 + GPT ≈ 1 小时）。
</div>
</div>
<script>
var rows=[].slice.call(document.querySelectorAll('tbody tr'));
document.querySelectorAll('.bar button').forEach(function(b){
  b.onclick=function(){
    document.querySelectorAll('.bar button').forEach(function(x){x.classList.remove('on')});
    b.classList.add('on');
    var f=b.dataset.f;
    rows.forEach(function(r){
      var t=r.dataset.tags||'';
      var show = f==='all' || (f==='tagged' ? t.trim()!=='' : t.split(' ').indexOf(f)>=0);
      r.style.display = show ? '' : 'none';
    });
  };
});
</script>
</body></html>"""


if __name__ == '__main__':
    main()
