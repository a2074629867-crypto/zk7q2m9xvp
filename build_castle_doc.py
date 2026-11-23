# -*- coding: utf-8 -*-
"""build_castle_doc.py —— 《我是城堡之王》参考音频对比 + dots.tts 官方情绪/韵律规范全解"""
import base64, os, subprocess, tempfile
import soundfile as sf

OUT = "G:/_setup/dots_edit2"
HTML = "G:/_setup/dots_castle_doc.html"
FFMPEG = "E:/tool/oopz/ffmpeg.exe"


def mp3_b64(path):
    tmp = tempfile.mktemp(suffix=".mp3")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path,
                    "-ac", "1", "-ar", "32000", "-b:a", "64k", tmp], check=True)
    b = open(tmp, "rb").read()
    os.remove(tmp)
    return base64.b64encode(b).decode()


def dur(p):
    a, sr = sf.read(p)
    return len(a) / sr


def row(label, hint, fname, spk=None, wpm=None, hl=False):
    p = os.path.join(OUT, fname)
    if not os.path.exists(p):
        return ""
    d = dur(p)
    meta = '<span class="dur">%.2fs</span>' % d
    if wpm:
        meta += '<span class="wpm">%.0f wpm</span>' % wpm
    if spk:
        cls = "good" if spk >= 0.80 else ("warn" if spk >= 0.70 else "bad")
        meta += '<span class="pct %s">音色 %.4f</span>' % (cls, spk)
    b64 = mp3_b64(p)
    return ('<div class="row%s"><div class="lbl"><b>%s</b>'
            '<span class="hintline">%s</span></div><div class="meta">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (" hl" if hl else "", label, hint, meta, b64))


CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#252a34;--tx:#e6e8ee;--dim:#98a0b3;--acc:#6ea8fe;
--good:#4ade80;--bad:#f87171;--warn:#fbbf24;--purple:#c4a8e8}
*{box-sizing:border-box}
body{margin:0;padding:34px 20px 90px;background:var(--bg);color:var(--tx);
font:15px/1.75 -apple-system,"Segoe UI",system-ui,"Microsoft YaHei",sans-serif}
.wrap{max-width:940px;margin:0 auto}
h1{font-size:27px;margin:0 0 8px;letter-spacing:-.4px}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:30px;line-height:1.8}
h2{font-size:17.5px;margin:38px 0 12px;padding-left:11px;border-left:3px solid var(--acc)}
h3{font-size:14.5px;margin:22px 0 8px;color:var(--acc)}
.note{color:var(--dim);font-size:13px;margin:0 0 15px;padding:13px 15px;background:var(--card);
border:1px solid var(--line);border-radius:10px;line-height:1.85}
.note code,.code{background:#222732;padding:1.5px 6px;border-radius:5px;font-size:12.5px;
color:#c9d1e0;font-family:ui-monospace,Consolas,monospace}
pre{background:#12161d;border:1px solid var(--line);border-radius:9px;padding:13px 15px;
overflow-x:auto;font-size:12.5px;line-height:1.75;margin:10px 0;color:#c9d1e0}
pre .t{color:#6ea8fe}.pre .d{color:#98a0b3}
.row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:13px 15px;margin-bottom:9px;
background:var(--card);border:1px solid var(--line);border-radius:11px}
.row.hl{border-color:#3a5a8a;background:#1a2233}
.lbl{flex:1 1 300px;min-width:250px}
.lbl b{font-size:14.5px;font-weight:600}
.hintline{display:block;color:var(--dim);font-size:12.5px;margin-top:3px}
.meta{display:flex;gap:7px;flex-wrap:wrap;font-size:12px}
.dur{background:#222732;padding:2px 8px;border-radius:6px;color:#c9d1e0;font-variant-numeric:tabular-nums}
.wpm{background:#222732;padding:2px 8px;border-radius:6px;color:#8fb8d8;font-variant-numeric:tabular-nums}
.pct{background:#2a2233;padding:2px 8px;border-radius:6px;font-variant-numeric:tabular-nums}
.pct.good{color:var(--good)}.pct.warn{color:var(--warn)}.pct.bad{color:var(--bad)}
audio{width:100%;max-width:330px;height:34px}
table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0 6px;
background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#1c2129;color:var(--dim);font-weight:600;font-size:12px}
tr:last-child td{border-bottom:none}
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.k{color:var(--acc);font-weight:600}
.p{color:var(--purple)}
ul{margin:8px 0 0;padding-left:22px}li{margin-bottom:8px}
.rule{background:#1a2233;border:1px solid #3a5a8a;border-radius:10px;padding:14px 16px;margin:12px 0}
.rule b{color:var(--acc)}
.foot{margin-top:40px;color:#6b7385;font-size:12px;border-top:1px solid var(--line);padding-top:16px;line-height:1.8}
"""

ROWS = "".join([
    row("源参考：开头段 9.17s", "0.57~33.24s 里的 24.07~33.24s，就是你喜欢的那段「soothing breeze… rustling the curtains」",
        "REF_early2_9.17s.wav"),
    row("★ 城堡之王 · 开头段参考", "52 词 → 19.84s · 音色 0.7386（对 768s 锚点）",
        "CASTLE_earlyref.wav", 0.7386, 157, True),
    row("城堡之王 · baseA 参考", "52 词 → 22.08s · 音色 0.8258 · 语速更接近睡前朗读",
        "CASTLE_baseA.wav", 0.8258, 141),
])

DOC_EMO = """
<h2>二、官方怎么调情绪</h2>
<p class="note">
情绪只有<b class="k">一个标签</b>：<code>&lt;emo&gt;</code>。两种互斥写法 ——
<b>给类型+强度</b>，或<b>给自由描述</b>。
</p>

<h3>写法 A：type + level（推荐，训练数据覆盖最全）</h3>
<pre>&lt;emo type="calm" level="2"&gt;Zoe drifted off to the soundest of sleeps.&lt;/emo&gt;</pre>
<table>
<tr><th>参数</th><th>合法取值</th><th>说明</th></tr>
<tr><td><code>type</code></td><td class="p">happy · angry · sad · afraid · disgusted · melancholic · surprised · <b>calm</b></td><td>8 种，取自 <code>editing.py</code> 的 <code>EMOTION_TYPES</code></td></tr>
<tr><td><code>level</code></td><td class="p">1 · 2 · 3</td><td>强度三档，默认 2。<b>不写 level 就是 2</b></td></tr>
</table>

<h3>写法 B：desc 自由描述（与 type/level 互斥）</h3>
<pre>&lt;emo desc="a sleepy, almost whispered bedtime voice"&gt;Zoe drifted off…&lt;/emo&gt;</pre>
<p class="note">
<code>desc</code> 走的是模型对自然语言的理解，<b>没有训练标签兜底</b>，
实测效果不稳定。官方 playground 把它放在「Custom」里，说明是探索性用法。
</p>

<h3>⚠️ 实测反直觉：<code>emo calm</code> 会让语速变快</h3>
<p class="note">
38 词基线 20.80s → <code>&lt;emo type="calm" level="3"&gt;</code> 出 <b class="warn">3.68s</b>（4 词短句场景），
长文本场景 <code>rate 0.71 + calm L2</code> 只有 <b class="warn">19.84s</b>，比纯 <code>rate 0.71</code> 的 23.52s
<b>还短 3.7s</b>，音色同时掉到 0.7867。
⇒ <b>「calm」在模型里对应的是「平静地快说」，不是「缓慢低语」。</b>
做睡前故事不能用它，要用 <code>&lt;rate&gt;</code>。
</p>
"""

DOC_PROSO = """
<h2>三、官方怎么调韵律</h2>
<p class="note">
韵律是<b class="k">三个独立标签</b>，各管一个维度，互不替代。
</p>
<table>
<tr><th>标签</th><th>语法</th><th>官方取值</th><th>作用</th></tr>
<tr>
  <td><code>pitch</code></td>
  <td><code>&lt;pitch, semitones=-5&gt;文字&lt;/pitch&gt;</code></td>
  <td class="p">playground: <b>±5 / ±7 / ±9</b>（无 0，无 ±1~4）<br>doteBench 示例: <code>3</code></td>
  <td>整段音高平移，单位半音。负=更低更沉</td>
</tr>
<tr>
  <td><code>rate</code></td>
  <td><code>&lt;rate, factor=0.60&gt;文字&lt;/rate&gt;</code></td>
  <td class="p">playground: <b>0.55–0.99 或 1.01–1.95</b>（不能 1.00）<br>doteBench: 只说「正数」</td>
  <td>语速倍率。<b>只作用于语音段，不动静音段</b></td>
</tr>
<tr>
  <td><code>pause</code></td>
  <td><code>&lt;pause act="ins" level="2"/&gt;</code></td>
  <td class="p">act: <b>ins</b>（插入）/ <b>red</b>（缩短）<br>level: 1–3（playground）；doteBench 无 level</td>
  <td>在文本边界加/减停顿，自闭合标签</td>
</tr>
</table>

<h3>两套官方写法，解析器都认</h3>
<pre><span class="d"># playground UI 生成（给人用的默认格式，逗号 + 无引号）</span>
<span class="t">&lt;pitch, semitones=-5&gt;</span>…<span class="t">&lt;/pitch&gt;</span>
<span class="t">&lt;rate, factor=0.60&gt;</span>…<span class="t">&lt;/rate&gt;</span>
<span class="t">&lt;pause act="ins" level="2"/&gt;</span>

<span class="d"># doteBench 评测规范（等号 + 引号）</span>
<span class="t">&lt;pitch semitones="3"&gt;</span>…<span class="t">&lt;/pitch&gt;</span>
<span class="t">&lt;rate factor="1.2"&gt;</span>…<span class="t">&lt;/rate&gt;</span>
<span class="t">&lt;pause act="ins"/&gt;</span></pre>
<p class="note">
解析器正则 <code>_OPEN_TAG_RE = ^&lt;\\s*([A-Za-z_][\\w-]*)(?:\\s|,|&gt;)</code> ——
<b>逗号和等号都被接受</b>。但<b>属性值解析器完全不校验</b>（只存 raw_opening_tag），
写 <code>level="9"</code> 也不报错，会直接喂给模型。
⇒ <b>范围限制是 UI 的约束，不是模型的约束。</b>
</p>
"""

RULES = """
<h2>四、三条铁律（官方文档明写）</h2>

<div class="rule">
<b>① Operations cannot nest or cross</b><br>
<code>docs/data.md</code> 原文：<i>"Operations cannot nest or cross."</i>
⇒ <b class="bad">不能嵌套</b>。我此前写的
<code>&lt;rate, factor=0.71&gt;&lt;emo type="calm" level="2"&gt;…&lt;/emo&gt;&lt;/rate&gt;</code>
<b>是违规的</b>，实测也确实是反效果（19.84s，比纯 rate 还短 3.7s）。<br>
正确做法是<b>按源序并列</b>，每个操作只管自己那一段：
<pre>&lt;rate, factor=0.60&gt;第一句&lt;/rate&gt; 第二句 &lt;pause act="ins" level="2"/&gt; &lt;emo type="sad" level="2"&gt;第三句&lt;/emo&gt;</pre>
</div>

<div class="rule">
<b>② 所有操作都是局部的</b><br>
官方每个标签的说明都写 <i>"affected text"</i> —— 只作用于被包裹的那段文字。
想整段放慢就必须把整段包起来，不能指望「设一次管全文」。
</div>

<div class="rule">
<b>③ xvector 自动开关，这是个硬耦合（最容易被忽略）</b><br>
<code>README</code> 原文：<i>"it is disabled when the instruction contains at least one operation
and every operation is <code>emo</code>, <code>bg</code>, or <code>enhance</code>, and enabled for
text, pitch, rate, pause, speaker transfer, or mixed edits."</i>
<table>
<tr><th>指令里有什么</th><th>xvector</th><th>音色来自</th></tr>
<tr><td>只有 <code>emo</code> / <code>bg</code> / <code>enhance</code></td><td class="good">关闭</td><td><b>voice-ref 参考音频</b></td></tr>
<tr><td>含 <code>sub</code>/<code>ins</code>/<code>del</code>/<code>pitch</code>/<code>rate</code>/<code>pause</code>/<code>spk_transfer</code> 或混合</td><td class="warn">开启</td><td><b>source-audio 源音频</b></td></tr>
</table>
<p class="note" style="margin-bottom:0">
⇒ <b>调情绪</b>（emo）时音色跟着参考走；<b>改文本或调韵律</b>时音色切成源音频的。
这就是实测里「换内容后音色从 0.86 崩到 0.42」的机制 —— 可以用
<code>--request-option use_xvector=on</code> 强制开启救回来（0.42 → 0.78）。
</p>
</div>
"""

CONCL = """
<h2>五、城堡之王实测</h2>
<table>
<tr><th>参考</th><th>时长</th><th>语速</th><th>音色</th><th>ASR 内容</th></tr>
<tr><td>开头段 9.17s（你喜欢的那段）</td><td>19.84s</td><td>157 wpm</td><td class="warn">0.7386</td><td class="good">52 词全对</td></tr>
<tr><td><b>baseA（566s）</b></td><td>22.08s</td><td><b>141 wpm</b></td><td class="good">0.8258</td><td class="good">52 词全对</td></tr>
</table>
<p class="note">
两条内容都<b class="good">逐字正确</b>。但开头段参考的音色低 <b class="warn">8.7 个点</b>（0.7386 vs 0.8258），
语速也快 16 wpm。<b>这是第三次测出同一结论</b>（前两次：rate 0.60 场景 0.7547 vs 0.8990）——
开头段作为参考确实不如 baseA。<br><br>
原因推测：baseA（566s）那段是<b>完整长句、气息连贯、有句间停顿</b>，
而开头段（24.07~33.24s）末尾带明显气声收尾，参考音频里气声比例过高会把音色往「虚」的方向拉。
这也符合官方那条反直觉说明：<b>参考音频不是越「好听」越好，而是要气息稳定、动态范围正常。</b>
</p>
"""

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>城堡之王 · dots.tts 官方情绪与韵律规范</title>
<style>%s</style></head><body><div class="wrap">
<h1>城堡之王 × 官方情绪/韵律规范</h1>
<div class="sub">
上半部分：用《Wonder》最开头的参考音频念《我是城堡之王》（Susan Hill，52 词），与 baseA 参考对比。<br>
下半部分：dots.tts 官方文档里情绪和韵律的完整语法 —— 包括<b>两套官方写法</b>、<b>三条铁律</b>，
以及我此前踩过的两个坑（嵌套违规、逗号 vs 等号）。
</div>

<h2>一、《我是城堡之王》· 换参考音频</h2>
<p class="note">
文本：<i>"But it had not been moving. The old man had breathed noisily, and dribbled a little,
and never woken. The sick room smelled sour. Edmund Hooper, walking down the great staircase
into the woodpanelled hall, thought nothing of his grandfather. But later, he remembered the
moth-like whiteness of the very old skin."</i>（52 词）<br>
模式：TTS（无标签、seed 42、同一模型）。<b>只换参考音频</b>，其余全部固定。
</p>
%s

%s
%s
%s
%s

<div class="foot">
官方依据：<code>dots_repo/README.md</code>（edit 章节 L161-190）、
<code>dots_repo/src/dots_tts/data/edit_instruction.py</code>（解析器）、
<code>dots_repo/apps/edit_playground/editing.py</code>（UI 常量）、
<code>doteBench/docs/data.md</code>（XML 评测规范 V1.0）<br>
模型：DotTTS-Edit-GGUF q8_0 · RX580 Vulkan · 音色基准 real_trim.wav（768s，统一跨区域基准）
</div>
</div></body></html>""" % (CSS, ROWS, DOC_EMO, DOC_PROSO, RULES, CONCL)

open(HTML, "w", encoding="utf-8").write(html)
print("written %s  %.2f MB" % (HTML, os.path.getsize(HTML) / 1e6))
