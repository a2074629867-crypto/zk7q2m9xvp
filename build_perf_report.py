# -*- coding: utf-8 -*-
"""构建「官方词句表演 + 实测」报告页，内嵌 6 段对照音频。"""
import base64
import io
import os
import subprocess

D = "G:/_setup/dots_edit2/"
TMP = "G:/_setup/_mp3/"
OUT = "G:/_setup/dots_perf_report.html"
FF = "E:/tool/oopz/ffmpeg.exe"
os.makedirs(TMP, exist_ok=True)

CLIPS = [
    ("ES_src", "原音频（源）", "16.80s", "c05.wav 前 16.8 秒，42 词。所有对比的基准。", "ref"),
    ("ES_base", "无标签复刻", "16.16s", "edit 任务、同内容复刻。声纹 0.9506，是这条链路的正常水平。", "base"),
    ("ES_whole", "整段 pitch −6 半音", "16.16s", "理论应降到 52Hz，实测只降 1.2 半音（兑现 20%）。声纹 0.9330。", "bad"),
    ("ES_enh", "enhance", "16.16s", "整段包 &lt;enhance&gt;。F0 只动 +0.16 半音，等于没效果。声纹 0.9360。", "bad"),
    ("ES_emo3", "emo angry L3（默认 auto）", "14.88s", "F0 飙到 181Hz（+15.6 半音），但声纹崩到 0.3815，不像马修了。", "bad"),
    ("ES_emo3xv", "emo angry L3 + xvector 强制开启", "17.12s", "同样的 emo，强制开启 speaker guidance。F0 205.9Hz（+17.9 半音），声纹回到 0.7654。", "good"),
]


def mp3_b64(name):
    src = D + "MES_" + name + ".wav" if name != "ES_src" else D + "ES_src.wav"
    dst = TMP + name + ".mp3"
    if not os.path.exists(dst):
        subprocess.run([FF, "-y", "-i", src, "-codec:a", "libmp3lame",
                        "-b:a", "96k", "-ar", "24000", "-ac", "1", dst],
                       capture_output=True)
    return base64.b64encode(open(dst, "rb").read()).decode()


cards = []
for name, title, dur, desc, kind in CLIPS:
    b64 = mp3_b64(name)
    cards.append(f'''
<div class="card {kind}">
  <div class="hd"><span class="nm">{title}</span><span class="du">{dur}</span></div>
  <audio controls preload="none" src="data:audio/mpeg;base64,{b64}"></audio>
  <div class="ds">{desc}</div>
</div>''')

HTML = '''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dots.tts 词句表演：官方规范与实测</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0e1116;color:#c8cfda;font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:44px 22px 80px}
h1{font-size:27px;color:#e8eef7;margin:0 0 6px;letter-spacing:-.3px}
.sub{color:#6f7a8a;font-size:13.5px;margin-bottom:38px}
h2{font-size:19px;color:#e2e9f3;margin:46px 0 14px;padding-left:11px;border-left:3px solid #4a7fd4}
h3{font-size:15.5px;color:#a9b8cd;margin:26px 0 10px;font-weight:600}
p{margin:10px 0;color:#b3bccb}
table{width:100%;border-collapse:collapse;background:#141920;border-radius:9px;overflow:hidden;font-size:13.5px;margin:14px 0}
th{background:#1a2029;color:#8d99ab;font-weight:500;font-size:12.5px;text-align:left;padding:9px 12px}
td{padding:9px 12px;border-top:1px solid #1f2731;color:#b6c0cf}
tr:hover td{background:#171d25}
.num{font-variant-numeric:tabular-nums}
.hi{color:#e2b45c;font-weight:600}
.ok{color:#7fb98a;font-weight:600}
.no{color:#d97a83;font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:18px 0}
@media(max-width:680px){.grid{grid-template-columns:1fr}}
.card{background:#141920;border:1px solid #1f2731;border-radius:11px;padding:14px 15px}
.card.good{border-color:#2f5a3c;background:#121a15}
.card.bad{border-color:#3a2429}
.card.ref{border-color:#2a3a52}
.hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:9px;gap:10px}
.nm{font-size:13.5px;color:#dbe4f0;font-weight:600}
.du{font-size:12px;color:#6d788a;font-variant-numeric:tabular-nums;white-space:nowrap}
audio{width:100%;height:34px;margin:2px 0 8px;filter:invert(.92) hue-rotate(180deg)}
.ds{font-size:12.5px;color:#8b96a7;line-height:1.65}
.lead{background:#131922;border:1px solid #223046;border-radius:10px;padding:16px 18px;margin:20px 0}
.lead b{color:#e8c179}
code{background:#1b222c;color:#9fc4ea;padding:1px 5px;border-radius:4px;font-size:12.5px}
.foot{margin-top:56px;padding-top:18px;border-top:1px solid #1c232c;color:#5f6a79;font-size:12px}
ul{margin:10px 0;padding-left:22px}li{margin:6px 0;color:#b3bccb}
.kv{display:grid;grid-template-columns:130px 1fr;gap:4px 14px;font-size:13.5px;margin:12px 0}
.kv dt{color:#7d8899}.kv dd{margin:0;color:#b6c0cf}
</style></head><body><div class="wrap">

<h1>dots.tts 词句表演：官方规范与实测</h1>
<div class="sub">数据源 doteBench V1.0（prosody 360 / emotion 612 / compositional 240）· 实测 2026-10-18 · RX580 · DotTTS-Edit-GGUF q8_0</div>

<div class="lead">
<b>一句话结论：</b>官方给了 <code>rate</code> 和 <code>pitch</code> 两个「表演」标签，但在这台机器上实测，
<code>pitch</code> 是死参数（整段 −6 半音只降 1.2 半音，−12 反而只降 0.28），
<code>rate</code> 兑现约 25%，<b>只有 <code>emo</code> 真正改变语气语调</b>（+15.6 半音），
但它默认会毁掉音色（0.38）——必须同时加 <code>--use-xvector on</code> 才能保住（0.77）。
</div>

<h2>一、官方只用一个标签做表演？不，是两个</h2>
<p>doteBench 的 prosody 集 360 例，标签分布干净得出奇——只有 <code>rate</code> 和 <code>pitch</code>，没有任何 emo 或 pause 混进来：</p>
<table>
<tr><th>组合</th><th>例数</th><th>说明</th></tr>
<tr><td>只有 <code>rate</code></td><td class="num">120</td><td>纯语速</td></tr>
<tr><td>只有 <code>pitch</code></td><td class="num">120</td><td>纯音高</td></tr>
<tr><td><code>pitch</code> + <code>rate</code></td><td class="num">120</td><td>两者混用，各管不同的词</td></tr>
</table>

<h3>官方示例原文</h3>
<p>这是 prosody 集的第一条，同一个源音频、同一段文本，只换标签位置：</p>
<table>
<tr><th>变体</th><th>指令</th></tr>
<tr><td>wave_1</td><td><code>"Yes, yes," she &lt;rate factor="1.12"&gt;hurried&lt;/rate&gt;, pulling her hand &lt;rate factor="0.88"&gt;gently&lt;/rate&gt; away from him.</code></td></tr>
<tr><td>wave_2</td><td><code>"Yes, yes," she hurried, &lt;rate factor="0.95"&gt;pulling&lt;/rate&gt; her hand gently away from him.</code></td></tr>
<tr><td>wave_3</td><td><code>"Yes, yes," she &lt;rate factor="1.19"&gt;hurried&lt;/rate&gt;, pulling her hand gently away from him. &lt;rate factor="0.77"&gt;Presently&lt;/rate&gt; it stole…</code></td></tr>
</table>
<p>三条共同点，也是官方的用法核心：</p>
<ul>
<li><b>标签只包一个词</b>（hurried / gently / pulling / Presently），从不包整句</li>
<li>同一句里可以有多个 span，各管一个词</li>
<li>pitch 和 rate <b>不嵌套</b>，分别落在不同的词上</li>
</ul>

<h3>粒度分布：七成是单词或短词组</h3>
<table>
<tr><th>粒度</th><th>例数</th><th>占比</th></tr>
<tr><td><code>single_word</code></td><td class="num">108</td><td class="num">30%</td></tr>
<tr><td><code>short_phrase</code></td><td class="num">108</td><td class="num">30%</td></tr>
<tr><td><code>clause</code></td><td class="num">120</td><td class="num">33%</td></tr>
<tr><td><code>sentence</code></td><td class="num">24</td><td class="num">7%</td></tr>
</table>
<p>整句只有 7%。<b>官方的表演是「给某个词加戏」，不是「给整段定调」。</b></p>

<h3>pitch 的取值：−9 到 +9 半音，负值略多</h3>
<table>
<tr><th>半音</th><th>次数</th><th>半音</th><th>次数</th></tr>
<tr><td>−7</td><td class="num">7</td><td>+3</td><td class="num">54</td></tr>
<tr><td>−6</td><td class="num">38</td><td>+4</td><td class="num">36</td></tr>
<tr><td class="hi">−5</td><td class="num hi">66</td><td class="hi">+5</td><td class="num hi">55</td></tr>
<tr><td>−4</td><td class="num">43</td><td>+6</td><td class="num">26</td></tr>
<tr><td>−3</td><td class="num">31</td><td>+9</td><td class="num">7</td></tr>
<tr><td>−2</td><td class="num">21</td><td>+2</td><td class="num">14</td></tr>
</table>

<h2>二、emo 有三种官方写法，第三种最有用</h2>
<p>emo 集 612 例（intense 300 + neutral 312），每种写法各占三分之一：</p>
<table>
<tr><th>写法</th><th>例数</th><th>例子</th></tr>
<tr><td><code>_whole</code></td><td class="num">204</td><td>整段包一个 emo</td></tr>
<tr><td><code>_phrase</code></td><td class="num">204</td><td>只包中段一个短语，前后不动</td></tr>
<tr><td><code>_multi</code></td><td class="num">204</td><td><b>一句里两个不同情绪</b>，各管一段</td></tr>
</table>
<p><code>_multi</code> 的实例：</p>
<p><code>I can hear something &lt;emo type="happy" level="2"&gt;scraping against the floorboards just outside my bedroom door&lt;/emo&gt; and the lights have suddenly flickered out &lt;emo type="disgusted" level="2"&gt;leaving me completely alone in the freezing darkness&lt;/emo&gt;.</code></p>
<p>注意它标的是 <b>happy</b> 和 <b>disgusted</b>——这是恐怖场景。官方在 <code>_multi</code> 里<b>故意让情绪与语义不匹配</b>，
测的是「模型是否服从指令」，不是「情绪是否合理」。<code>annotations.source_emotion</code> 还记录了源音频原本的情绪（afraid），
说明 intense 集是<b>改情绪</b>，neutral 集是<b>从无到有</b>。</p>

<h2>三、官方自评：情绪是强项，副语言是弱项</h2>
<p>README 的 EmergentTTS-Eval，对 gpt-4o-mini-tts 的胜率：</p>
<table>
<tr><th>模型</th><th>Emotions</th><th>Paraling.</th><th>Quest.</th><th>Syntax</th></tr>
<tr><td>gpt-4o-mini-tts</td><td class="num">59.2%</td><td class="num">58.8%</td><td class="num">52.7%</td><td class="num">57.1%</td></tr>
<tr><td><b>dots.tts (Pretrain)</b></td><td class="num ok">72.7%</td><td class="num no">54.7%</td><td class="num no">48.4%</td><td class="num">58.4%</td></tr>
<tr><td>dots.tts (SOAR)</td><td class="num">63.9%</td><td class="num">52.7%</td><td class="num">47.0%</td><td class="num ok">65.7%</td></tr>
</table>
<p><b>Emotions 72.7% 是所有开源模型最高</b>，但 Paraling（叹气、笑、耳语）和 Quest（疑问句）都低于 gpt-4o-mini-tts。
我们做的是睡前低语朗读——正好撞在它最弱的一格上。</p>

<h2>四、实测：六段音频，同一个源</h2>
<p>源是 <code>c05.wav</code> 的前 16.8 秒（42 词），edit 任务、<code>source_text == target_text</code>、seed 42。
所有变体内容都完整（42/42 词），差别只在「念法」。<b>请按顺序听。</b></p>

<div class="grid">''' + "".join(cards) + '''</div>

<h2>五、数据</h2>
<table>
<tr><th>变体</th><th>时长</th><th>中位 F0</th><th>Δ 半音</th><th>声纹</th><th>判定</th></tr>
<tr><td>原音频</td><td class="num">16.80s</td><td class="num">73.3</td><td class="num">—</td><td class="num">1.0000</td><td>基准</td></tr>
<tr><td>无标签复刻</td><td class="num">16.16s</td><td class="num">74.9</td><td class="num">+0.38</td><td class="num">0.9506</td><td>正常</td></tr>
<tr><td>词级 pitch −6</td><td class="num">16.16s</td><td class="num">73.5</td><td class="num">+0.05</td><td class="num">0.9622</td><td class="no">无效</td></tr>
<tr><td>整段 pitch −6</td><td class="num">16.16s</td><td class="num">68.4</td><td class="num">−1.20</td><td class="num">0.9330</td><td class="no">兑现 20%</td></tr>
<tr><td>整段 pitch −12</td><td class="num">16.16s</td><td class="num">72.1</td><td class="num">−0.28</td><td class="num">0.9273</td><td class="no">比 −6 更小</td></tr>
<tr><td>enhance</td><td class="num">16.16s</td><td class="num">74.0</td><td class="num">+0.16</td><td class="num">0.9360</td><td class="no">无效</td></tr>
<tr><td>emo angry L1</td><td class="num">14.88s</td><td class="num">181.3</td><td class="num">+15.67</td><td class="num no">0.3856</td><td class="no">毁音色</td></tr>
<tr><td>emo angry L2</td><td class="num">14.56s</td><td class="num">182.3</td><td class="num">+15.77</td><td class="num no">0.3404</td><td class="no">毁音色</td></tr>
<tr><td>emo angry L3</td><td class="num">14.88s</td><td class="num">180.8</td><td class="num">+15.63</td><td class="num no">0.3815</td><td class="no">毁音色</td></tr>
<tr><td><b>emo L3 + xvector on</b></td><td class="num">17.12s</td><td class="num hi">205.9</td><td class="num hi">+17.87</td><td class="num ok">0.7654</td><td class="ok">可用</td></tr>
</table>

<div class="lead">
<b>三条硬结论</b><br>
① <b>pitch 是死参数</b>：−6 降 1.2 半音，−12 只降 0.28 半音，不线性也不单调，等同噪声；词级完全不动。<br>
② <b>level 是死参数</b>：L1/L2/L3 的 F0 是 181.3 / 182.3 / 180.8，三档一模一样，只有 <code>type</code> 起作用。<br>
③ <b>emo 必须配 <code>--use-xvector on</code></b>：默认 auto 会因为「全是 emo」自动关闭 speaker guidance，
音色切到 voice_ref，声纹崩到 0.38；强制开启后回到 0.77（等于我们链路的正常水平），情绪还更强。
</div>

<h2>六、为什么 emo 能救回来</h2>
<p>官方 README 的原文规则：</p>
<p><code>Edit speaker guidance defaults to auto: it is disabled when the instruction contains at least one operation and every operation is emo, bg, or enhance, and enabled for text, pitch, rate, pause, speaker transfer, or mixed edits.</code></p>
<p>源码里就是一行：</p>
<p><code>_AUTO_DISABLE_XVECTOR_TAGS = frozenset({"emo", "bg", "enhance"})</code></p>
<p>所以：<b>只要整条指令只有 emo，speaker guidance 就被关掉，音色改从 voice_ref 取</b>——
我们的 voice_ref 是 8.3 秒的参考片段，撑不住愤怒这种极端音高，于是「不像」。
加 <code>--use-xvector on</code> 强制保留 source_audio 的音色，问题消失。</p>

<h2>七、对生产链的意义</h2>
<div class="kv">
<dt>要改语气</dt><dd>用 <code>emo</code> + <code>--use-xvector on</code>，按场景/段落打。不要指望 pitch。</dd>
<dt>要改语速</dt><dd><code>rate</code> 兑现约 25%，只能微调；大幅改速走后期 rubberband。</dd>
<dt>不要用</dt><dd><code>pitch</code>（无效）、<code>enhance</code>（无效）、<code>level</code>（无梯度）。</dd>
<dt>emo 的代价</dt><dd>它是「换一种说法」，会把 F0 整体拉高一个八度、时长缩短 8%，不是微调。适合段落级，不适合句级。</dd>
<dt>下一步</dt><dd>测 <code>calm</code> / <code>melancholic</code> 这两个与睡前朗读更匹配的 type，看方向是否也这么猛。</dd>
</div>

<div class="foot">
实测环境：RX580 8GB · Vulkan · DotTTS-Edit-GGUF q8_0 · seed 42 · max_tokens 420 ·
voice_ref = wonder_train 8.3s 切片 · 声纹锚 = 源音频本身（同内容同段，可比）<br>
数据源：doteBench V1.0 prosody 360 / emotion 612 / compositional 240 · dots.tts README · data.md · edit_instruction.py
</div>

</div></body></html>'''

io.open(OUT, "w", encoding="utf-8").write(HTML)
print("written", OUT, len(HTML), "chars")
