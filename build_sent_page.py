# -*- coding: utf-8 -*-
"""构建「句中情绪位置 + sequential 合成」实测页。"""
import base64
import os
import subprocess

D = "G:/_setup/dots_edit2/"
TMP = "G:/_setup/_mp3s/"
OUT = "G:/_setup/dots_sent_emo.html"
FF = "E:/tool/oopz/ffmpeg.exe"
os.makedirs(TMP, exist_ok=True)

CLIPS = [
    ("ES_src", "原音频（源）", "16.80s",
     "c05.wav 前 16.8 秒 / 42 词。所有声纹的锚点。", "ref"),
    ("ES_base", "无标签复刻（基准）", "16.16s",
     "不打任何标签。声纹 <b>0.9506</b>，三段区段 Δ 全为 0。后面所有对比都相对它。", "base"),

    ("EP_head", "① 句首 6 词 emo（sad）", "16.96s",
     "包 <span class=m>A tussle of grayish white hair</span>。"
     "HEAD <b>+3.71</b> 半音，MID +0.52、TAIL +2.67（小样本）。"
     "声纹 <b>0.9026</b>——几乎无损。", "key"),
    ("EW_emo_clause", "② 句中 6 词 emo（sad）", "17.12s",
     "包 <span class=m>reading glasses enfolded in his pocket</span>（官方范式的「句中」）。"
     "MID <b>+4.23</b>，HEAD +0.16。声纹 <b>0.9021</b>。", "key"),
    ("EP_tail", "③ 句尾 9 词 emo（sad）", "16.80s",
     "包 <span class=m>and a stack of books sat by his side</span>。"
     "TAIL <b>+5.36</b>，HEAD +0.16、MID −0.23。声纹 <b>0.8807</b>。", "key"),
    ("EW_emo_sent", "④ 句首 11 词 emo（sad，最强单处）", "17.12s",
     "同一位置，把范围从 6 词扩到 11 词。HEAD <b>+6.07</b>（6 词时只有 +3.71）。"
     "声纹 <b>0.8858</b>。<b>范围翻倍，效果接近翻倍。</b>", "key"),

    ("EP_two_same_sent", "⑤ 同句双情绪（sad + surprised）", "18.56s",
     "MID 包 sad、TAIL 包 surprised，一次调用。"
     "MID <b>+3.38</b>、TAIL <b>+13.54</b>——两处各自生效、互不干扰，"
     "但 surprised 的量级是 sad 的 4 倍。声纹 <b>0.8406</b>。", "mid"),

    ("SEQ_base_rate", "⑥ 纯 rate 0.80（合成第一步的基线）", "18.88s",
     "整段 <code>&lt;rate, factor=0.80&gt;</code>，edit 任务。"
     "16.16 → 18.88s，<b>兑现 67%</b>（理论 20.20s）。"
     "三段 Δ 全在 ±1.2 内 ⇒ <b>rate 只改时长，不改音高</b>。声纹 0.8784。", "base"),
    ("SEQ_emo_rate", "⑦ 合成：emo 版再套 rate（sequential 两步）", "20.00s",
     "第一步 EW_emo_sent（HEAD +6.07）→ 第二步整段 rate 0.80。"
     "rate 兑现 <b>67%</b>（与纯 rate 完全一致），但 emo <b>只剩 +1.04</b>（衰减 83%）。"
     "声纹 <b>0.7569</b>——两次生成的漂移叠加。", "warn"),

    ("ES_emo3", "对照：整段 emo（42 词）", "14.88s",
     "F0 中位 180.8（+15.6 半音），声纹崩到 <b>0.3815</b>。"
     "这就是「范围失控」的样子。", "bad"),
]

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0e1116;color:#c8cfda;font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:44px 22px 80px}
h1{font-size:27px;color:#e8eef7;margin:0 0 6px;letter-spacing:-.3px}
.sub{color:#6f7a8a;font-size:13.5px;margin-bottom:32px}
h2{font-size:19px;color:#e2e9f3;margin:46px 0 14px;padding-left:11px;border-left:3px solid #4a7fd4}
p{margin:10px 0;color:#b3bccb}
table{width:100%;border-collapse:collapse;background:#141920;border-radius:9px;overflow:hidden;font-size:13px;margin:14px 0}
th{background:#1a2029;color:#8d99ab;font-weight:500;font-size:12px;text-align:left;padding:9px 10px}
td{padding:8px 10px;border-top:1px solid #1f2731;color:#b6c0cf}
tr:hover td{background:#171d25}
.mono,.m{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;color:#8fb8e0}
.pos{color:#7fb98a;font-weight:600}
.neg{color:#6f7a8a}
.hot{color:#e0a06a;font-weight:600}
.card{background:#141920;border:1px solid #1f2731;border-radius:11px;padding:14px 16px;margin:12px 0}
.card.key{border-color:#2f5d3a;background:#121a15}
.card.bad{border-color:#5d2f36;background:#1a1214}
.card.base{border-color:#2f4a5d;background:#12171a}
.card.ref{border-color:#3a3a3a;background:#141414}
.card.mid{border-color:#5d4f2f;background:#1a1712}
.card.warn{border-color:#5d2f52;background:#1a121a}
.hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:9px}
.nm{font-size:14.5px;color:#dfe7f2;font-weight:600}
.du{font-size:12px;color:#6f7a8a;font-family:ui-monospace,Consolas,monospace}
audio{width:100%;height:34px;margin:2px 0 8px}
.ds{font-size:13px;color:#9aa5b4;line-height:1.7}
.note{background:#171d25;border-left:3px solid #4a7fd4;padding:11px 14px;border-radius:0 7px 7px 0;margin:16px 0;font-size:13.5px}
.warnbox{background:#1a1214;border-left:3px solid #b8555f;padding:11px 14px;border-radius:0 7px 7px 0;margin:16px 0;font-size:13.5px}
"""

cards = []
for name, title, dur, desc, kind in CLIPS:
    src = D + ("ES_src.wav" if name == "ES_src" else "MES_" + name + ".wav")
    dst = TMP + name + ".mp3"
    if not os.path.exists(dst):
        subprocess.run([FF, "-y", "-i", src, "-codec:a", "libmp3lame",
                        "-b:a", "96k", "-ar", "24000", "-ac", "1", dst],
                       capture_output=True)
    if not os.path.exists(dst):
        continue
    b64 = base64.b64encode(open(dst, "rb").read()).decode()
    cards.append('''
<div class="card %s">
  <div class="hd"><span class="nm">%s</span><span class="du">%s</span></div>
  <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>
  <div class="ds">%s</div>
</div>''' % (kind, title, dur, b64, desc))

ROWS = [
    ("ES_base", "—", "—", "16.16", "0", "0", "0", "0.9506"),
    ("EP_head", "HEAD", "6", "16.96", "<b>+3.71</b>", "+0.52", "+2.67*", "0.9026"),
    ("EW_emo_clause", "MID", "6", "17.12", "+0.16", "<b>+4.23</b>", "+3.07*", "0.9021"),
    ("EP_tail", "TAIL", "9", "16.80", "+0.16", "−0.23", "<b>+5.36</b>", "0.8807"),
    ("EW_emo_sent", "HEAD", "11", "17.12", "<b>+6.07</b>", "+0.32", "+0.66", "0.8858"),
    ("EP_two_same_sent", "MID + TAIL", "6+9", "18.56", "+0.20", "<b>+3.38</b>", "<b>+13.54</b>", "0.8406"),
    ("SEQ_base_rate", "—（纯 rate）", "—", "18.88", "−0.25", "−0.11", "+1.15", "0.8784"),
    ("SEQ_emo_rate", "HEAD（继承）", "11", "20.00", "<b>+1.04</b>", "+0.55", "+1.69", "0.7569"),
    ("ES_emo3", "整段", "42", "14.88", "—", "—", "—", "0.3815"),
]
trows = "\n".join(
    "<tr><td class=mono>%s</td><td>%s</td><td class=mono>%s</td><td class=mono>%s</td>"
    "<td class=mono>%s</td><td class=mono>%s</td><td class=mono>%s</td><td class=mono>%s</td></tr>" % r
    for r in ROWS)

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>句中情绪位置 + sequential 合成</title>
<style>%s</style></head><body><div class="wrap">

<h1>句中情绪 · 位置与范围 · sequential 合成</h1>
<div class="sub">dots.tts edit 任务 · 短源 ES_src 16.8s / 42 词 · seed 42 · max_tokens 420–480<br>
测量：parselmouth（ceiling 250Hz，RMS 门控 0.006，50ms 窗）· 声纹锚 = ES_src</div>

<h2>一、核心结论</h2>
<div class="note">
<b>emo 是严格局部的。</b>包哪一段，只有那一段抬高；未包的区段全部落在 ±1 半音内（小样本两处除外）。<br>
<b>句首、句中、句尾都生效</b>——官方 612 例全部在句中，但实测两端同样有效，句尾甚至更强（+5.36 vs +4.23）。<br>
<b>效果随范围近似线性</b>：同位置同 type，6 词 +3.71 → 11 词 +6.07。<br>
<b>同句两个情绪可以共存</b>：sad +3.38 与 surprised +13.54 各管各的片段，互不串扰。
</div>

<h2>二、区段测量（Δ 半音，相对 base 同区段）</h2>
<table>
<tr><th>变体</th><th>emo 包住</th><th>词数</th><th>时长</th><th>HEAD</th><th>MID</th><th>TAIL</th><th>声纹</th></tr>
%s
</table>
<p style="font-size:12.5px;color:#6f7a8a">
HEAD = <span class=m>tussle…hair</span>（句首）· MID = <span class=m>reading…pocket</span>（句中）·
TAIL = <span class=m>stack…side</span>（句尾）。<br>
带 * 的格子有效窗只有 9–10 个（TAIL 段在 base 里念得很快，浊音帧稀疏），<b>不可作为结论依据</b>。
</p>

<h2>三、逐条试听</h2>
%s

<h2>四、sequential 合成：能要，但代价明确</h2>
<div class="warnbox">
<b>同块同时写 emo + rate ⇒ rate 兑现 0%%</b>（16.32s，等于没写）。<br>
<b>分两步 ⇒ rate 兑现 67%%，但 emo 衰减 83%%</b>（HEAD +6.07 → +1.04），声纹从 0.8858 掉到 0.7569。<br>
原因：第二步是「拿第一步的输出当 source 再复刻一遍」，复刻时模型按自己的韵律重排，第一步的局部抬升被抹平。
</div>
<table>
<tr><th>方案</th><th>rate 兑现</th><th>emo 保留</th><th>声纹</th><th>结论</th></tr>
<tr><td>同块 emo + rate</td><td class=neg>0%%</td><td>—</td><td>0.9322</td><td class=neg>不可用</td></tr>
<tr><td>sequential 两步</td><td class=pos>67%%</td><td class=hot>约 20%%</td><td>0.7569</td><td>能用，但情绪基本被抹掉</td></tr>
<tr><td>单步 emo + 后期拉伸</td><td>—</td><td class=pos>100%%</td><td>0.8858</td><td class=pos><b>推荐</b></td></tr>
</table>
<p>后期拉伸用 rubberband 0.88x 时声纹 0.784，与 sequential 的 0.7569 相当，但情绪完整保留。
<b>所以「又慢又有情绪」应该走：单步 emo → 后期 rubberband，不要用 sequential。</b></p>

<h2>五、音色代价阶梯</h2>
<table>
<tr><th>情形</th><th>声纹</th><th>说明</th></tr>
<tr><td>无标签</td><td class=mono>0.9506</td><td>基准</td></tr>
<tr><td>1 处 emo，6 词</td><td class=mono>0.90</td><td>几乎无损（句首 0.9026 / 句中 0.9021）</td></tr>
<tr><td>1 处 emo，9–11 词</td><td class=mono>0.88</td><td>仍合格</td></tr>
<tr><td>2 处 emo</td><td class=mono>0.8406</td><td>开始可闻</td></tr>
<tr><td>整段 emo（42 词）</td><td class=mono>0.3815</td><td>崩，不像同一个人</td></tr>
</table>
<p>每多一处 emo，声纹掉约 0.04–0.06。<b>一块里最多 1 处，一章 5–10 处</b>这条不是保守，是实测出来的成本。</p>

<div class="sub" style="margin-top:46px;font-size:12px">
数据：<span class=m>_sent_delta.json</span> · 指令 <span class=m>EP_*.txt / SEQ_rate080.txt</span> ·
音频 <span class=m>MES_EP_*.wav / MES_SEQ_*.wav</span>
</div>

</div></body></html>""" % (CSS, trows, "\n".join(cards))

open(OUT, "w", encoding="utf-8").write(HTML)
print("written", OUT, "%.2f MB" % (len(HTML) / 1048576), "| cards", len(cards))
