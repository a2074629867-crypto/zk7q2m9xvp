# -*- coding: utf-8 -*-
"""构建「neutral / calm / natural 三种 emo 取值」实测页。"""
import base64
import os
import subprocess

D = "G:/_setup/dots_edit2/"
TMP = "G:/_setup/_mp3n/"
OUT = "G:/_setup/dots_neutral.html"
FF = "E:/tool/oopz/ffmpeg.exe"
os.makedirs(TMP, exist_ok=True)

CLIPS = [
    ("ES_src", "原音频（源）", "16.80s",
     "c05.wav 前 16.8 秒 / 42 词。基准与声纹锚点。低频帧占 86%，正常男声。", "ref"),
    ("ES_base", "无标签复刻（真正的「自然」）", "16.16s",
     "不打任何标签。声纹 0.9506，低频 86.0% / 高频 8.6%。"
     "这才是「自然朗读」的实际听感——想要 natural，答案是<b>不写标签</b>。", "base"),
    ("EN_whole_neutral", "① 整段 neutral（42 词）", "13.12s",
     "比 base <b>短 19%</b>，F0 中位从 74.9 抬到 97.1（+4.6 半音），"
     "高频帧 8.6% → <b>34.9%</b>，声纹掉到 <b>0.6590</b>。"
     "它既不是「无变化」，也不是「更平静」——是把声音整体抬起来了。", "bad"),
    ("EN_sent_neutral", "② 整句 neutral（11 词）", "16.48s",
     "只包 A tussle of grayish white hair banded atop his head。"
     "声纹 <b>0.8876</b>，低频 60.6% / 高频 14.4%，该段出现 462–506 Hz 气声。", "key"),
    ("EN_sent_calm", "③ 整句 calm（11 词）", "16.48s",
     "同范围、换成 calm。声纹 <b>0.8834</b>，低频 59.6% / 高频 15.9%。"
     "<b>与 neutral 的波形相关 0.9724</b>——引擎基本分辨不出这两个 type。", "key"),
    ("EN_sent_natural", "④ 整句 natural（非法值）", "16.48s",
     "natural 不在官方 9 种枚举内（官方 parser 直接 raise ValueError）。"
     "实测不报错、不丢词，但效果与 neutral/calm 混在一起（高频 19.0%、声纹 0.8780）"
     "——<b>不可预期，不能用</b>。", "bad"),
    ("ES_emo3", "对照：整段 angry（42 词）", "14.88s",
     "F0 中位 180.8（+15.6 半音），低频只剩 2.6%，声纹崩到 0.3815。"
     "emo 的真实量级在这里——neutral 只是它的温和版。", "mid"),
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
<h1>neutral / calm / natural 三种取值实测</h1>
<div class="sub">42 词 / 16.8s 短源 · edit 任务 · seed 42 · use_xvector=auto · 全部 42/42 词内容完整</div>

<h2>三个结论</h2>
<div class="good">
<b>一、`natural` 不是合法值。</b>官方枚举只有 9 种，<span class="mono">neutral</span> 在里面，
<span class="mono">natural</span> 不在。官方 parser 见到它会直接 <span class="mono">raise ValueError</span>。<br>
<b>二、`neutral` 不等于「无变化」。</b>它会把声音整体抬起来：+4.6 半音、时长 −19%、高频帧翻四倍。<br>
<b>三、`neutral` 与 `calm` 几乎是同一个东西。</b>波形相关 <b>0.9724</b>，时长完全相同（16.480s）。
</div>

<h2>实测数据</h2>
<table>
<tr><th>变体</th><th>时长</th><th>F0 中位</th><th>Δ半音</th><th>低频 &lt;100Hz</th><th>高频 &gt;200Hz</th><th>声纹</th></tr>
<tr><td>无标签 base</td><td>16.16s</td><td>74.9</td><td>—</td><td class="gd">86.0%</td><td class="gd">8.6%</td><td class="gd">0.9506</td></tr>
<tr><td>整段 neutral</td><td class="bd">13.12s</td><td>97.1</td><td class="bd">+4.59</td><td class="bd">52.3%</td><td class="bd">34.9%</td><td class="bd">0.6590</td></tr>
<tr><td>整句 neutral</td><td>16.48s</td><td>81.2</td><td>+1.49</td><td>60.6%</td><td>14.4%</td><td class="gd">0.8876</td></tr>
<tr><td>整句 calm</td><td>16.48s</td><td>81.0</td><td>+1.51</td><td>59.6%</td><td>15.9%</td><td class="gd">0.8834</td></tr>
<tr><td>整句 natural</td><td>16.48s</td><td>90.0</td><td>+3.25</td><td>58.9%</td><td>19.0%</td><td>0.8780</td></tr>
<tr><td>对照：整段 angry</td><td>14.88s</td><td>180.8</td><td class="bd">+15.63</td><td class="bd">2.6%</td><td>31.8%</td><td class="bd">0.3815</td></tr>
</table>

<p>「低频 &lt;100 Hz」是这次最有说服力的一列：正常男声朗读有 86% 的浊音帧落在 100 Hz 以下。
整段 neutral 把它打到 52.3%，同时把 &gt;200 Hz 的帧从 8.6% 抬到 34.9%。
<b>这不是「更平静」，是把音色整体抬高了</b>，所以声纹从 0.95 掉到 0.66。</p>

<div class="note">
<b>`natural` 的真实行为：</b>它不在枚举里，但模型不报错也不忽略——输出与 neutral/calm 落在同一档
（高频 19.0%、声纹 0.8780、时长 16.480s 与另两组逐帧对齐）。<br>
换句话说：<b>它被当成了某个「非负面」的默认情绪来执行</b>，但官方从未定义过它，
具体落到哪一档不可预期、也不可复现。<b>标注里绝对不要写。</b>
</div>

<h2>那「自然的朗读」应该怎么做</h2>
<div class="good">
<b>不写 emo。</b>base 那一段（第 2 条）就是自然的——低频 86%、声纹 0.95。<br>
想要更慢、更柔，走 <span class="mono">rate</span>（edit 任务，兑现 84–93%）+ 后期停顿，不要试图用 emo 表达「平静」。
</div>

<h2>试听（第 2 条是真正的「自然」，第 3 条最值得对比）</h2>
"""

HTML = ('<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>neutral / calm / natural 实测</title>\n<style>' + CSS + '</style></head>'
        '<body><div class="wrap">' + BODY + '\n' + "\n".join(cards) + '\n'
        '<div class="foot">数据：<span class="mono">_ew_ts.json</span> · '
        '指令 <span class="mono">EN_*.txt</span> · '
        '音频 <span class="mono">MES_EN_*.wav</span></div>\n'
        '</div></body></html>')

open(OUT, "w", encoding="utf-8").write(HTML)
print("written", OUT, "%.2f MB" % (len(HTML) / 1048576))
print("cards", len(cards))
