# -*- coding: utf-8 -*-
"""build_review2.py —— 标注审阅页 v2（V2 降噪切片 + large-v3-turbo + 声学校正 + 双模型交叉验证）

每条切片展示：
  · 时间/时长/词数/首静/尾停
  · 停顿可视化（每个词间停顿按长度与「应有标点」着色）
  · 文本（标点与声学不一致处高亮；缺失标点以虚影显示）
  · 双模型分歧（turbo vs small.en）
  · 音频
"""
import base64, json, os, re, subprocess, tempfile
from collections import Counter

FFMPEG = 'E:/tool/oopz/ffmpeg.exe'
D = 'G:/GPT-SoVITS/_dataset_v5full'
ANNOT = D + '/v2_df3_turbo_annot.json'
CROSS = D + '/v2_cross_df3.json'
OUT = 'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_voice_lab/review_labels_df3.html'


def mp3_b64(wav, bitrate='32k', ar=24000):
    tmp = tempfile.mktemp(suffix='.mp3')
    subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', wav,
                    '-ac', '1', '-ar', str(ar), '-codec:a', 'libmp3lame', '-b:a', bitrate, tmp],
                   check=True)
    data = open(tmp, 'rb').read(); os.remove(tmp)
    return base64.b64encode(data).decode('ascii')


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def gapbar(gaps, exps, t1, t2):
    """停顿可视化：宽度∝时长，颜色=应有标点"""
    if not gaps:
        return '<span class="gb none">—</span>'
    out = []
    for g, e in zip(gaps, exps):
        cls = 'none' if e == '' else ('com' if e == ',' else 'per')
        w = max(3, min(46, int(g * 26)))
        out.append('<i class="gb %s" style="width:%dpx" title="%.2fs → %s"></i>'
                   % (cls, w, g, e or '无'))
    return ''.join(out)


def text_html(core, punc, exp, exps, tail, exp_tail):
    """文本 + 标点不一致高亮"""
    parts = []
    for i, c in enumerate(core):
        parts.append(esc(c))
        p = punc[i] if i < len(punc) else ''
        e = exp[i] if i < len(exp) else ''
        if p and p != e:
            parts.append('<span class="pm" title="声学应为 %s">%s</span>' % (esc(e or '无'), esc(p)))
        elif p:
            parts.append(esc(p))
        elif e:
            parts.append('<span class="pg" title="声学有停顿，标注缺标点">%s</span>' % esc(e))
        parts.append(' ')
    s = ''.join(parts).strip()
    if tail is not None:
        last = punc[-1] if punc else ''
        if last in '.!?' and tail < 0.25:
            s += ' <span class="pm">[句末无停顿 %.2fs]</span>' % tail
        elif last == '' and tail >= 1.2:
            s += ' <span class="pg">[尾停 %.2fs 缺标点]</span>' % tail
    return s


def main():
    A = json.load(open(ANNOT, encoding='utf-8'))
    sl = A['slices']
    t1, t2 = A['comma_th'], A['period_th']
    C = {}
    if os.path.exists(CROSS):
        C = {r['i']: r for r in json.load(open(CROSS, encoding='utf-8'))['slices']}
    print('读入 %d 条（标点阈值 %.2f / %.2f），交叉验证 %d 条' % (len(sl), t1, t2, len(C)))

    rows = []
    for r in sl:
        p = os.path.join(D, 'sliced_df3', r['file']).replace('\\', '/')
        if not os.path.exists(p):
            print('  MISS', p); continue
        b64 = mp3_b64(p)
        tags = []
        fl = r['flags']
        if any(f.startswith('punc') for f in fl): tags.append('pmis')
        if 'period_no_pause' in fl: tags.append('pp')
        if 'pause_no_period' in fl: tags.append('np')
        if 'halluc_phrase' in fl or 'repeat' in ' '.join(fl): tags.append('hall')
        if r['nwords'] < 3: tags.append('short')
        c = C.get(r['i'])
        if c and c['rate'] < 0.95: tags.append('cross')
        tg = ''
        if 'pmis' in tags: tg += '<span class="tg pm">标点</span>'
        if 'pp' in tags: tg += '<span class="tg pp">句末无停顿</span>'
        if 'np' in tags: tg += '<span class="tg np">有停顿缺标点</span>'
        if 'hall' in tags: tg += '<span class="tg hl">幻觉?</span>'
        if 'short' in tags: tg += '<span class="tg sh">短</span>'
        if 'cross' in tags: tg += '<span class="tg cr">模型分歧</span>'

        cross_html = ''
        if c and c['rate'] < 0.999:
            dd = ' / '.join('%s → %s' % (d['turbo'] or '∅', d['small'] or '∅')
                            for d in c['diffs'][:4])
            cross_html = ('<div class="cx">small.en(%.0f%%): %s</div>'
                          % (100 * c['rate'], esc(dd[:150])))

        rows.append(
            '<tr class="r%s" data-tags="%s"><td class="idx">%03d</td>'
            '<td class="tm">%6.2f</td><td class="num">%.2f</td><td class="num">%d</td>'
            '<td class="num sil">%.2f</td><td class="num sil">%.2f</td>'
            '<td class="gbc">%s</td>'
            '<td class="tx">%s%s%s</td>'
            '<td class="au"><audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></td></tr>'
            % (' warn' if tags else '', ' '.join(tags), r['i'], r['t0'], r['dur'], r['nwords'],
               r['lead'], r['tail'] if r['tail'] is not None else 0.0,
               gapbar(r['gaps'], r['exp'], t1, t2),
               tg,
               text_html(r['core'], r['punc'], r['exp'], r['exp'], r['tail'], r['exp_tail']),
               cross_html, b64))

    full = re.sub(r'\s+', ' ', ' '.join(r['text'] for r in sl)).strip()
    c = Counter(t for r in sl for t in r['flags'])
    total_words = sum(r['nwords'] for r in sl)
    total_dur = sum(r['dur'] for r in sl)
    n_pm = sum(1 for r in sl if any(f.startswith('punc') for f in r['flags']))

    stats = """<div class="stats">
  <div class="st"><b>%d</b><span>切片数</span></div>
  <div class="st"><b>%d</b><span>总词数</span></div>
  <div class="st"><b>%.1f</b><span>总时长(分)</span></div>
  <div class="st w"><b>%d</b><span>标点不一致</span></div>
  <div class="st w"><b>%d</b><span>句末无停顿</span></div>
  <div class="st w"><b>%d</b><span>有停顿缺标点</span></div>
  <div class="st w"><b>%d</b><span>幻觉嫌疑</span></div>
  <div class="st g"><b>%d</b><span>模型分歧</span></div>
</div>""" % (len(rows), total_words, total_dur / 60, n_pm, c.get('period_no_pause', 0),
            c.get('pause_no_period', 0), c.get('halluc_phrase', 0) + c.get('repeat', 0),
            sum(1 for r in sl if (C.get(r['i']) or {}).get('rate', 1) < 0.95))

    html = TEMPLATE.replace('@@STATS@@', stats).replace('@@FULL@@', esc(full)) \
                   .replace('@@ROWS@@', '\n'.join(rows)) \
                   .replace('@@T1@@', '%.2f' % t1).replace('@@T2@@', '%.2f' % t2)
    open(OUT, 'w', encoding='utf-8').write(html)
    print('WROTE %s  (%.2f MB)  %d 行' % (OUT, os.path.getsize(OUT) / 1024 / 1024, len(rows)))


TEMPLATE = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>标注审阅 v2 · Wonder</title>
<style>
:root{--bg:#12141a;--card:#1b1e26;--fg:#e8eaf0;--dim:#9aa3b2;--ac:#5cc8ff;--good:#39d98a;--warn:#ffb454;--bad:#ff7b7b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;padding:18px 14px 60px}
.wrap{max-width:1500px;margin:0 auto}
h1{font-size:21px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:14px;line-height:1.8}
.box{background:var(--card);border:1px solid #2b3140;border-radius:10px;padding:12px 15px;margin:0 0 16px;font-size:12.5px;line-height:1.85}
.box b{color:var(--fg)} .box code{background:#22262f;padding:1px 5px;border-radius:4px}
.stats{display:flex;flex-wrap:wrap;gap:9px;margin:0 0 16px}
.st{background:var(--card);border:1px solid #2b3140;border-radius:9px;padding:8px 13px;min-width:96px}
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
th,td{padding:6px;border-bottom:1px solid #232833;vertical-align:middle;text-align:left}
th{color:var(--dim);font-weight:500;font-size:11.5px;position:sticky;top:0;background:#161922;z-index:2}
td.idx{color:var(--dim);font-family:ui-monospace,monospace;width:40px}
td.tm{font-family:ui-monospace,monospace;color:var(--dim);width:54px}
td.num{font-family:ui-monospace,monospace;text-align:right;width:46px}
td.sil{color:#7d8797}
td.gbc{width:96px;white-space:nowrap}
td.tx{line-height:1.7}
td.au{width:220px}
audio{width:210px;height:30px}
tr.warn{background:rgba(255,180,84,.04)}
.tg{display:inline-block;font-size:10.5px;padding:0 6px;border-radius:9px;margin-right:5px;vertical-align:1px}
.tg.pm{background:rgba(255,180,84,.18);color:var(--warn)}
.tg.pp{background:rgba(255,123,123,.18);color:#ff9d9d}
.tg.np{background:rgba(92,200,255,.16);color:var(--ac)}
.tg.hl{background:rgba(255,123,123,.26);color:#ffb3b3}
.tg.sh{background:rgba(154,163,178,.18);color:#aab3c2}
.tg.cr{background:rgba(57,217,138,.16);color:var(--good)}
i.gb{display:inline-block;height:9px;border-radius:2px;margin-right:2px;vertical-align:middle}
i.gb.none{background:#39404e} i.gb.com{background:var(--warn)} i.gb.per{background:#ff7b7b}
span.gb.none{color:var(--dim)}
span.pm{color:var(--warn);border-bottom:2px solid var(--warn);font-weight:700}
span.pg{color:#5b6473;border-bottom:2px dotted #5b6473;font-style:italic}
div.cx{color:#8f9aab;font-size:11px;margin-top:3px;font-family:ui-monospace,monospace;line-height:1.6}
.hint{color:var(--dim);font-size:12.5px;margin-top:20px;line-height:1.9}
.hint b{color:var(--fg)}
</style></head><body><div class="wrap">
<h1>标注审阅 · Wonder（Calm）· ② DF3 降噪 + large-v3-turbo + 声学校正</h1>
<div class="sub">训练音频 = <b>② DF3 降噪（宽带噪声）</b> <code>wonder_train_df3.wav</code> → 重切 461 段 → large-v3-turbo 分块转写（词级时间戳）→ 异常窗重转 → 声学标点校正 → 双模型交叉验证</div>
<div class="box">
<b>这一版比上一版做了什么：</b><br>
① <b>换音频</b>：训练音频从 ③（DF3+notch）改为 <b>②（纯 DF3，只除宽带噪声）</b>。notch 实测只影响 60–85Hz
   （90Hz 以上 ≤0.3dB），但它会削掉男声低音 ⇒ 按你的选择用 ②。<br>
② <b>换模型</b>：small.en → <b>large-v3-turbo</b>（错误率显著更低），且在<b>降噪后</b>的音频上转写。<br>
③ <b>分块 + 上下文接力</b>：以切片边界（=真实停顿）为切点分成 ~24s 的窗，逐窗转写，
   <code>initial_prompt</code> 用<b>上文真实文本</b>（不是编造的提示语，避免致幻），词时间戳加窗偏移 ⇒ <b>无长程漂移</b>。<br>
④ <b>异常窗重转</b>：全片 67 窗里 9 窗 wps 越界（6 窗重复致幻、3 窗漏转），已用「5 档解码阶梯 + 重复惩罚」重转择优。<br>
⑤ <b>声学标点校正</b>：GSV 的标点是<b>训练符号</b>（实测 <code>oceans,</code> → <code>... AH0 N Z , ...</code>），
   所以标点必须和音频实际停顿一致。阈值<b>从 ASR 自身输出标定</b>：
   <code>无标点 &lt; @@T1@@s &lt; 逗号 &lt; @@T2@@s &lt; 句号</code>。<br>
⑥ <b>标点规范化</b>：实测 <code>;</code> <code>:</code> <code>—</code> 会被 GSV 前端<b>静默丢弃</b>（停顿信息丢失）⇒ 映射为逗号；
   <code>'</code> 会变成 <code>-</code> 停顿符、孤立 <code>-</code> 会读成 "minus" ⇒ 清理。<br>
⑦ <b>双模型交叉验证</b>：large-v3-turbo vs small.en，两模型都认同 = 高置信，分歧处 = 错词嫌疑点。<br><br>
<b>颜色说明</b>：<span class="pm">橙色标点</span> = 与声学停顿不一致；
<span class="pg">灰色虚影标点</span> = 声学上有停顿但标注里缺标点；停顿条 <span style="color:#39404e">灰</span>=无标点
<span style="color:#ffb454">橙</span>=逗号 <span style="color:#ff7b7b">红</span>=句号。
</div>
@@STATS@@
<details class="full"><summary>▸ 展开全文连读（当故事通读，错词最容易在这里看出来）</summary><pre>@@FULL@@</pre></details>
<div class="bar">
  <button class="on" data-f="all">全部</button>
  <button data-f="tagged">有标记</button>
  <button data-f="pmis">标点不一致</button>
  <button data-f="pp">句末无停顿</button>
  <button data-f="np">有停顿缺标点</button>
  <button data-f="hall">幻觉嫌疑</button>
  <button data-f="cross">模型分歧</button>
  <button data-f="short">短文本</button>
</div>
<table><thead><tr><th>#</th><th>起点s</th><th>时长</th><th>词</th><th>首静</th><th>尾停</th><th>停顿</th><th>文本</th><th>试听</th></tr></thead>
<tbody>
@@ROWS@@
</tbody></table>
<div class="hint">
<b>怎么审（三步）：</b><br>
1. 展开「全文连读」通读一遍 —— 找错词/漏词（例如 ASR 把 weaving 听成 weeding）。<br>
2. 点「<b>模型分歧</b>」—— 两个模型给的词不一样的地方，<b>错词概率最高</b>，逐条看。<br>
3. 点「<b>标点不一致</b>」—— 标注标点与音频停顿不符的地方，确认该保留哪个。<br><br>
审完说「开始」，我跑训练（SoVITS v5turbo LoRA ≈ 23 分钟 + GPT ≈ 1 小时）。
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
