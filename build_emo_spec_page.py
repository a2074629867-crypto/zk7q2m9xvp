# -*- coding: utf-8 -*-
"""官方 emo 示范页：同源三版对照 + 量化分布 + parser 约束 + 实测对照。"""
import io, html, json, os

OUT = "G:/_setup/dots_emo_spec.html"

def hl(x):
    """转义 + 高亮 emo 标签。"""
    s = html.escape(x)
    import re
    s = re.sub(r'(&lt;/?emo[^&]*?&gt;)', r'<span class="t">\1</span>', s)
    return s

WHOLE = ('<emo type="angry" level="2">I can hear something scraping against the '
         'floorboards just outside my bedroom door and the lights have suddenly '
         'flickered out leaving me completely alone in the freezing darkness of '
         'this empty house tonight.</emo>')

PHRASE = ('I can hear something scraping against the floorboards just outside my '
          'bedroom door and <emo type="melancholic" level="2">the lights have '
          'suddenly flickered out</emo> leaving me completely alone in the freezing '
          'darkness of this empty house tonight.')

MULTI = ('I can hear something <emo type="happy" level="2">scraping against the '
         'floorboards just outside my bedroom door</emo> and the lights have suddenly '
         'flickered out <emo type="disgusted" level="2">leaving me completely alone '
         'in the freezing darkness</emo> of this empty house tonight.')

SHORT1 = ('There was <emo type="afraid" level="2">nothing behind him except for</emo> '
          'his bookcase which <emo type="surprised" level="2">seemed to be missing</emo> '
          'a single, important book.')

SHORT2 = ('Unlike VoiceCode, which <emo type="calm" level="2">is a complete solution</emo>, '
          'Dragonfly is just <emo type="happy" level="2">an improved Python API</emo> to Dragon.')

def block(title, sub, xml):
    return ('<div class="case"><div class="ch"><b>%s</b><span>%s</span></div>'
            '<pre>%s</pre></div>' % (title, sub, hl(xml)))

CASES = (block("_whole", "整段包住 · intense 中位 14 词", WHOLE)
         + block("_phrase", "只包中间一个从句 · 中位 3 词", PHRASE)
         + block("_multi", "一句两个情绪 · 2 个 span", MULTI)
         + block("_multi（更短）", "neutral 集 · 情绪贴合语义", SHORT1)
         + block("_multi（正向）", "calm + happy，都不是负向", SHORT2))

# ---------------- 统计表 ----------------
DIST = [
    ("`_phrase` 词数", "intense 中位 <b>3</b>（1–12）／neutral 中位 <b>2</b>（1–12）"),
    ("`_whole` 词数", "intense 中位 14（1–39）／neutral 中位 8（1–44）"),
    ("span 位置", "phrase <b>100% 在句中</b>（句首 0、句尾 0）"),
    ("span 边界词", "前：and 19 / that 12 / because 8　后：and 30 / leaving 10 / that 9"),
    ("`level`", "<b>624 例全部是 2</b>，0 个 1、0 个 3"),
    ("情绪枚举", "parser 允许 <b>9 种</b>（含 `neutral`），样例出现 8 种"),
    ("数据集", "intense 300（源全是 afraid，改情绪）／ neutral 312（从无到有）"),
]

# ---------------- 实测对照 ----------------
TEST = [
    ("无标签", "—", "16.16", "0.9506", "正常", ""),
    ("1 词 emo", "1", "16.32", "0.9327", "词后插 0.11s 假声", "bad"),
    ("短语 emo", "6", "16.16", "0.8780", "0.77s 连续改动", ""),
    ("从句 emo", "6", "17.12", "0.9021", "该段变慢", ""),
    ("整句 emo", "11", "17.12", "0.8858", "整句慢 6%，最自然", "good"),
    ("两词两情绪", "2", "16.16", "0.9389", "两处各一小段", ""),
    ("整段 emo", "42", "14.88", "0.3815", "整体换声", "bad"),
]

rows = "".join(
    '<tr class="%s"><td>%s</td><td class="c">%s</td><td class="c">%ss</td>'
    '<td class="c %s">%s</td><td>%s</td></tr>'
    % (cls, n, w, d, "hi" if cls == "good" else ("lo" if cls == "bad" else ""), s, note)
    for n, w, d, s, note, cls in TEST)

dist_rows = "".join("<tr><td class='k'>%s</td><td>%s</td></tr>" % (k, v) for k, v in DIST)

HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dots.tts 官方 emo 示范</title><style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1014;color:#c9d1d9;font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;padding:40px 22px 90px}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:27px;font-weight:650;color:#eef2f6;letter-spacing:-.3px}
.lead{color:#7d8794;font-size:14px;margin:10px 0 34px;padding-bottom:20px;border-bottom:1px solid #1d222b}
h2{font-size:18px;font-weight:600;color:#e3e9f0;margin:40px 0 6px}
h2 em{font-style:normal;font-size:12px;color:#5d6675;font-weight:400;margin-left:10px}
p{color:#98a2b0;font-size:14px;margin:8px 0}
b{color:#dfe6ee;font-weight:600}
code{background:#181d25;color:#8fc7e8;padding:1px 5px;border-radius:4px;font-size:13px;
font-family:"Cascadia Mono",Consolas,monospace}
.case{background:#12161c;border:1px solid #1e242e;border-radius:11px;margin:12px 0;overflow:hidden}
.ch{display:flex;align-items:baseline;gap:12px;padding:11px 16px;background:#161b22;border-bottom:1px solid #1e242e}
.ch b{font-size:13.5px;color:#8fc7e8;font-family:"Cascadia Mono",Consolas,monospace}
.ch span{font-size:12px;color:#69737f}
pre{padding:15px 16px;font:13px/1.85 "Cascadia Mono",Consolas,monospace;color:#aab4c0;
white-space:pre-wrap;word-break:break-word}
pre .t{color:#e0a76a}
table{width:100%%;border-collapse:collapse;margin:14px 0;background:#12161c;
border-radius:10px;overflow:hidden;font-size:13.5px}
th{background:#161b22;color:#8b95a3;font-weight:500;font-size:12px;text-align:left;padding:9px 13px}
td{padding:9px 13px;border-top:1px solid #1c222b;color:#a8b2bf;vertical-align:top}
tr:hover td{background:#161b22}
td.c{text-align:center;font-family:"Cascadia Mono",Consolas,monospace;font-size:12.5px}
td.hi{color:#7fb98a;font-weight:600}td.lo{color:#e07a83;font-weight:600}
td.k{color:#8fc7e8;white-space:nowrap;font-family:"Cascadia Mono",Consolas,monospace;font-size:12.5px}
tr.good td{background:#121a15}tr.bad td{background:#1a1315}
.warn{background:#1a1512;border-left:3px solid #c98a4b;border-radius:0 9px 9px 0;
padding:14px 18px;margin:16px 0;font-size:13.5px;color:#c2ae96}
.warn b{color:#e0b57d}
.ok{background:#111a14;border-left:3px solid #5c9a6b;border-radius:0 9px 9px 0;
padding:14px 18px;margin:16px 0;font-size:13.5px;color:#a8c2ae}
.ok b{color:#8fd0a0}
ul{margin:8px 0 8px 20px}li{color:#98a2b0;font-size:14px;margin:5px 0}
.foot{margin-top:52px;padding-top:20px;border-top:1px solid #1d222b;color:#5d6675;font-size:12.5px}
</style></head><body><div class="wrap">

<h1>官方是怎么示范 emo 的</h1>
<div class="lead">来源：本地 doteBench V1.0 emotion 数据集 612 例 + 官方 parser 与 candidate 适配器源码。
全部为原文与实测统计，非推测。</div>

<h2>一、最漂亮的设计：同源三版对照<em>同一段音频 sha256 e5f60b48… 同一段文本，只改作用范围</em></h2>
<p>官方用一条源音频做了三版，这是理解 emo 粒度最直接的示范。</p>
""" + CASES + """

<h2>二、量化分布<em>624 个 span 实测</em></h2>
<table><tr><th>项目</th><th>官方数值</th></tr>""" + dist_rows + """</table>

<div class="warn"><b>两条更正我此前的说法。</b>
① <code>_multi</code> 的情绪<b>不是乱标</b>——neutral 集的例子是 <code>calm</code> + <code>happy</code>，都贴合语义。
只有 intense 集因为任务是「改情绪」（源全是 afraid）才会出现语义不匹配。<b>我们的源是平静朗读，对应 neutral 场景。</b>
② <b>「官方支持 level 1–3」不等于能用</b>：624 例里只有 2，模型对 1/3 无梯度。</div>

<h2>三、parser 的硬约束<em>违反直接 raise</em></h2>
<pre>parser.py:58
if kind not in ATTRS or <span class="t">set(attrs) != ATTRS[kind]</span> or len(node):
    raise ValueError(...)

ATTRS = {"emo": {"type", "level"}, ...}</pre>
<ul>
<li><code>type</code> 与 <code>level</code> <b>必须同时存在</b>，<code>&lt;emo type="sad"&gt;</code> 非法</li>
<li>不能有多余属性（<code>desc=</code> 之类会被拒）</li>
<li>不能嵌套任何其他标签</li>
<li>枚举外的拼写直接报错，<code>neutral</code> 是合法的第 9 种</li>
</ul>

<h2>四、runtime 实际收到什么<em>compile.py / planner.py</em></h2>
<ul>
<li><code>source_text</code> == <code>target_text</code> == 剥掉所有标签的纯文本（emo 不改任何字符）</li>
<li>两者都带 <code>[EN]</code> / <code>[ZH]</code> 前缀（<code>compile_public_runtime_request</code>，我们一直没加）</li>
<li><code>&lt;emo&gt;</code> <b>不做格式转换</b>，原样进模型——只有 pitch/rate/pause 要转逗号格式。
这是 emo 一直正常工作、而 rate 一直不灵的分界线</li>
<li>多情绪走 sequential：<b>文本标签先、声学标签后，每操作一步</b> ⇒ 两个 emo = 两次生成</li>
</ul>

<h2>五、对照我们的实测<em>短源 16.8s / 42 词 / source==target</em></h2>
<table><tr><th>变体</th><th>词数</th><th>时长</th><th>声纹</th><th>听感</th></tr>""" + rows + """</table>
<p>声纹锚 = 源音频本身（<code>ES_src.wav</code>，无标签时 0.9506 是上限）。</p>

<div class="ok"><b>可用的标注规则。</b>
span <b>8–11 词最佳</b>，最少 4 词（低于 4 词会插假声），最多 11 词；
边界优先落在 <code>and</code> / <code>that</code> / <code>because</code>；
<code>level</code> 固定 2；必须加 <code>--request-option use_xvector=on</code>。</div>

<div class="warn"><b>emo 与 rate 互斥。</b>实测纯 <code>rate 0.88</code> 在 edit 任务下是 17.76s（兑现 84%），
加上 emo 后变成 16.32s，rate 失效。两者都要只能走 sequential。</div>

<div class="foot">数据：<code>doteBench/data/emotion/{intense,neutral}/manifest.json</code> ·
源码：<code>dotebench/instructions/parser.py</code>、<code>candidates/dots_tts_edit/compile.py</code> ·
完整规范：<code>G:/_setup/DOTS_EMO_SPEC.md</code></div>

</div></body></html>"""

io.open(OUT, "w", encoding="utf-8").write(HTML)
print("written", OUT, len(HTML), "chars")
