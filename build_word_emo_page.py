# -*- coding: utf-8 -*-
"""构建「单词级情绪 + edit 任务语速」报告页。"""
import base64
import os
import subprocess

D = "G:/_setup/dots_edit2/"
TMP = "G:/_setup/_mp3w/"
OUT = "G:/_setup/dots_word_emo.html"
FF = "E:/tool/oopz/ffmpeg.exe"
os.makedirs(TMP, exist_ok=True)

CLIPS = [
    ("ES_src", "原音频（源）", "16.80s",
     "c05.wav 前 16.8 秒 / 42 词。所有对比的基准，也是声纹锚点。", "ref"),
    ("ES_base", "无标签复刻", "16.16s",
     "edit 任务、同内容复刻。声纹 0.9506，这是本链路的正常水平。", "base"),
    ("EW_emo_auto", "① 单词 emo（hair）· auto", "16.32s",
     "只给 hair 一个词包 &lt;emo type=&quot;angry&quot;&gt;。声纹 <b>0.9327</b> 没崩。"
     "但 hair 之后插入 0.11s 假声段（主峰 500–673Hz），听着像一次吸气。", "key"),
    ("EW_emo_xv", "② 单词 emo（hair）· xvector on", "16.16s",
     "同标签，强制开启 speaker guidance。声纹 <b>0.9420</b>，比 auto 还高。", "key"),
    ("EW_emo_phrase", "③ 短语级 emo（6 词）", "16.16s",
     "包 reading glasses enfolded in his pocket。改动是 1.45–2.22s 连续 0.77 秒，"
     "30.7% 帧偏移 &gt;3 半音。声纹 0.8780。", "mid"),
    ("EW_emo_clause", "④ 从句级 emo（6 词 · sad）", "17.12s",
     "同样 6 词范围，情绪改成 sad。时长比 base 长 0.96s，声纹 0.9021。", "mid"),
    ("EW_emo_sent", "⑤ 整句级 emo（11 词 · sad）", "17.12s",
     "包 A tussle of grayish white hair banded atop his head。"
     "声纹 <b>0.8858</b> 仍然合格，时长 +6%。", "key"),
    ("EW_multi", "⑥ 官方 _multi（两词两情绪）", "16.16s",
     "hair 用 sad、discovered 用 surprised，同一句两个不同情绪。声纹 0.9389。", "mid"),
    ("EW_emo_pitch", "⑦ 单词 emo + 单词 pitch", "16.16s",
     "hair 包 sad、rifled 包 pitch −5 半音。混合操作自动开 xvector。pitch 依旧测不出效果。", "mid"),
    ("ES_emo3", "✗ 对照：整段 emo（42 词）", "14.88s",
     "整段包 emo angry。F0 飙到 180.8Hz（+15.6 半音），但声纹崩到 <b>0.3815</b>，不像马修了。"
     "这就是范围过大的代价。", "bad"),
    ("EW_rate115", "★ 整段 rate 1.15（edit 任务）", "14.40s",
     "理论 14.05s，实测 14.40s，<b>兑现 93%</b>。内容 42/42 完整，声纹 0.9104。", "rate"),
    ("EW_rate_only", "★ 整段 rate 0.88（edit 任务）", "17.76s",
     "理论 18.36s，实测 17.76s，<b>兑现 84%</b>。声纹 0.8724。", "rate"),
    ("EW_rate075", "★ 整段 rate 0.75（edit 任务）", "20.00s",
     "理论 21.55s，实测 20.00s，<b>兑现 85%</b>。声纹 0.7994。", "rate"),
    ("EW_wrate", "★ 单词 rate 0.60（hair）", "—",
     "只把 hair 一个词放慢到 0.60。这是「给某个词加语调」最直接的手段。", "rate"),
]


def mp3_b64(name):
    src = D + ("ES_src.wav" if name == "ES_src" else "MES_" + name + ".wav")
    dst = TMP + name + ".mp3"
    if not os.path.exists(dst):
        subprocess.run([FF, "-y", "-i", src, "-codec:a", "libmp3lame",
                        "-b:a", "96k", "-ar", "24000", "-ac", "1", dst],
                       capture_output=True)
    if not os.path.exists(dst):
        return None
    return base64.b64encode(open(dst, "rb").read()).decode()


cards = []
for name, title, dur, desc, kind in CLIPS:
    b64 = mp3_b64(name)
    if not b64:
        continue
    cards.append('''
<div class="card %s">
  <div class="hd"><span class="nm">%s</span><span class="du">%s</span></div>
  <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>
  <div class="ds">%s</div>
</div>''' % (kind, title, dur, b64, desc))

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0e1116;color:#c8cfda;font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:920px;margin:0 auto;padding:44px 22px 80px}
h1{font-size:27px;color:#e8eef7;margin:0 0 6px;letter-spacing:-.3px}
.sub{color:#6f7a8a;font-size:13.5px;margin-bottom:34px}
h2{font-size:19px;color:#e2e9f3;margin:46px 0 14px;padding-left:11px;border-left:3px solid #4a7fd4}
p{margin:10px 0;color:#b3bccb}
table{width:100%;border-collapse:collapse;background:#141920;border-radius:9px;overflow:hidden;font-size:13.5px;margin:14px 0}
th{background:#1a2029;color:#8d99ab;font-weight:500;font-size:12.5px;text-align:left;padding:9px 12px}
td{padding:9px 12px;border-top:1px solid #1f2731;color:#b6c0cf}
tr:hover td{background:#171d25}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;color:#8fb8e0}
.card{background:#141920;border:1px solid #1f2731;border-radius:11px;padding:14px 16px;margin:12px 0}
.card.key{border-color:#2f5d3a;background:#121a15}
.card.bad{border-color:#5d2f36;background:#1a1214}
.card.base{border-color:#2f4a5d;background:#12171a}
.card.ref{border-color:#3a3a3a;background:#141414}
.card.rate{border-color:#5d4a2f;background:#1a1712}
.card.mid{border-color:#243040}
.hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:9px;gap:12px}
.nm{font-size:14.5px;color:#dfe7f2;font-weight:600}
.du{font-size:12.5px;color:#6f7a8a;font-variant-numeric:tabular-nums;white-space:nowrap}
audio{width:100%;height:34px;margin:2px 0 8px}
.ds{font-size:13px;color:#95a1b3;line-height:1.65}
.hl{color:#e0b060}
.gd{color:#7fb98a}
.bd{color:#e07a83}
.note{background:#1a1614;border-left:3px solid #b8863b;padding:12px 15px;border-radius:0 7px 7px 0;margin:18px 0;font-size:13.5px;color:#c2b394}
.good{background:#121a15;border-left:3px solid #4a8a5c;padding:12px 15px;border-radius:0 7px 7px 0;margin:18px 0;font-size:13.5px;color:#a8c9b2}
.foot{margin-top:50px;padding-top:18px;border-top:1px solid #1f2731;color:#5f6a7a;font-size:12.5px}
"""

BODY = """
<h1>给单个词加情绪，以及 edit 任务下的真实语速</h1>
<div class="sub">42 词 / 16.16s 短源 · edit 任务 · seed 42 · 同一条 voice_ref · 全部 42/42 词内容完整</div>

<h2>两个结论</h2>
<div class="good">
<b>一、单词级 emo 生效，而且不毁音色。</b>声纹 0.93–0.94，和整段 emo 的 0.38 是两回事。<br>
<b>二、edit 任务下 rate 完全线性，兑现 84–93%。</b>这条之前被 tts 任务的 2–6% 掩盖了。
</div>

<h2>一、单词级 emo：生效，但变形</h2>
<table>
<tr><th>变体</th><th>标签范围</th><th>时长</th><th>声纹</th><th>现象</th></tr>
<tr><td>无标签 base</td><td>—</td><td>16.16s</td><td>0.9506</td><td>基准</td></tr>
<tr><td>① emo · auto</td><td>1 词</td><td>16.32s</td><td class="gd">0.9327</td><td>该词后插入 0.11s 假声</td></tr>
<tr><td>② emo · xv on</td><td>1 词</td><td>16.16s</td><td class="gd">0.9420</td><td>同上</td></tr>
<tr><td>③ _phrase</td><td>6 词短语</td><td>16.16s</td><td class="gd">0.8780</td><td>0.77s 连续改动</td></tr>
<tr><td>④ 从句 sad</td><td>6 词</td><td>17.12s</td><td class="gd">0.9021</td><td>该段变慢</td></tr>
<tr><td>⑤ 整句 sad</td><td>11 词</td><td>17.12s</td><td class="gd">0.8858</td><td>该句变慢 +6%</td></tr>
<tr><td>⑥ _multi</td><td>2 词 / 2 情绪</td><td>16.16s</td><td class="gd">0.9389</td><td>两处各一段</td></tr>
<tr><td class="bd">✗ 整段 emo</td><td>42 词</td><td class="bd">14.88s</td><td class="bd">0.3815</td><td>整体换声</td></tr>
</table>

<p>单词级 emo 的问题不在音色，在<b>形态</b>：base 在 1.71–1.85s 是静音，
三个包了 hair 的变体都在 1.72–1.84s 多出一段 <span class="mono">418–436 Hz</span> 的短音。
频谱主峰 500–673 Hz，RMS 只比基线高 24%。</p>
<p>听感上它更像<span class="hl">一次吸气或轻叹</span>，而不是「带情绪地说这个词」。</p>

<div class="note">
<b>范围越大越像语气，越小越像插音。</b>
1 个词 → 0.11 秒假声；6 词短语 → 0.77 秒连续改动；11 词整句 → 整句慢 6%、声纹仍 0.8858；
42 词整段 → 音色崩到 0.38。<b>安全上限在 11 词左右。</b>
</div>

<h2>二、edit 任务下 rate 是可靠旋钮</h2>
<table>
<tr><th>factor</th><th>理论时长</th><th>实测</th><th>兑现率</th><th>声纹</th><th>内容</th></tr>
<tr><td>1.15</td><td>14.05s</td><td>14.40s</td><td class="gd">93%</td><td>0.9104</td><td>42/42</td></tr>
<tr><td>1.00</td><td>16.16s</td><td>16.16s</td><td>—</td><td>0.9506</td><td>42/42</td></tr>
<tr><td>0.88</td><td>18.36s</td><td>17.76s</td><td class="gd">84%</td><td>0.8724</td><td>42/42</td></tr>
<tr><td>0.75</td><td>21.55s</td><td>20.00s</td><td class="gd">85%</td><td>0.7994</td><td>42/42</td></tr>
</table>
<p>同样一个 <span class="mono">&lt;rate&gt;</span>，在 tts 任务下只兑现 2–6%，在 edit 任务下兑现 84–93%，而且完全线性、不丢词。</p>
<p><b>差别在有没有 source 锚点。</b>tts 是从零生成，标签被稀释；edit 是「照着源改」，rate 改的是这个源的时长，模型照做。</p>
<p>代价是声纹随放慢下降：0.95 → 0.87 → 0.80。放慢越多，音色越淡。</p>

<h2>试听（1–9 情绪，10 是失败对照，11–14 语速）</h2>
"""

HTML = ('<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>单词级情绪 + edit 语速实测</title>\n<style>' + CSS + '</style></head>'
        '<body><div class="wrap">' + BODY + '\n' + "\n".join(cards) + '\n'
        '<div class="foot">数据：<span class="mono">_ew_ts.json</span> · '
        '<span class="mono">_ew_f0.py</span> · 指令 <span class="mono">EW_*.txt</span> · '
        '音频 <span class="mono">MES_EW_*.wav</span></div>\n'
        '</div></body></html>')

open(OUT, "w", encoding="utf-8").write(HTML)
print("written", OUT, "%.2f MB" % (len(HTML) / 1048576))
print("cards", len(cards))
