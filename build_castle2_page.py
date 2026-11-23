# -*- coding: utf-8 -*-
"""build_castle2_page.py —— 《我是城堡之王》44 词新段落 · 韵律移植试听页（离线单文件，内嵌 MP3）"""
import base64
import os
import subprocess
import tempfile

import soundfile as sf

OUT = "G:/_setup/dots_castle2"
REAL = "E:/tts-models/acpp/out/calmdeep_final/real_trim.wav"
HTML = "G:/_setup/dots_castle2_page.html"
FFMPEG = "E:/tool/oopz/ffmpeg.exe"


def mp3_b64(path):
    tmp = tempfile.mktemp(suffix=".mp3")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path,
                    "-ac", "1", "-ar", "32000", "-b:a", "64k", tmp], check=True)
    b = open(tmp, "rb").read()
    os.remove(tmp)
    return base64.b64encode(b).decode()


def dur(path):
    a, sr = sf.read(path)
    return len(a) / sr


def row(name, label, hint, path, spk=None, note=None):
    p = path if os.path.isabs(path) else os.path.join(OUT, path)
    if not os.path.exists(p):
        return ""
    d = dur(p)
    meta = '<span class="dur">%.2fs</span>' % d
    if spk:
        meta += '<span class="pct">音色 %.4f</span>' % spk
    if note:
        meta += '<span class="pct">%s</span>' % note
    b64 = mp3_b64(p)
    return ('<div class="row"><div class="lbl"><b>%s</b>%s'
            '<span class="hintline">%s</span></div><div class="meta">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (label, ('<code>%s</code>' % name) if name else "", hint, meta, b64))


GROUPS = []

GROUPS.append((
    "A · 新段落五版对照（同一文本、同参考、seed 42）",
    "文本：<i>Three months ago, his grandmother died, and then they had moved to this house…</i>（44 词）"
    "　参考 = baseA（Wonder 566s 段，8.3s）　音色锚点 = real_trim.wav",
    [("real_trim", "真人对照（Wonder 段，不是同一段文字）", "仅作音色锚点，29.41s / 语音 17.45 / 静音 11.96",
      REAL, None, None),
     ("A_plain", "A · 无标签基线", "21.76s / 语音 13.21 / 静音 8.55 / 间隙 9 个（中位 0.78）",
      "A_plain.wav", 0.8147, None),
     ("B_safe", "B · 编译器 safe（rate 0.84 整段一个 span）", "19.20s / 语音 13.35 / 静音 5.85 ← rate 几乎没兑现，反而 seed 少给了停顿",
      "B_safe.wav", 0.8045, None),
     ("C_rate071", "C · rate 0.71", "24.48s / 语音 14.42 / 静音 10.06 / 间隙变 11 个（多出 0.22 / 0.10 微间隙）",
      "C_rate071.wav", 0.8595, None),
     ("D_rhythm", "★ D · A + 真人停顿序列移植", "26.44s / 语音 13.21 / 静音 13.23 / 9 个间隙逐个对齐真人",
      "D_rhythm.wav", 0.8689, None),
     ("E_rate071_rhythm", "★★ E · C + 真人停顿序列移植（推荐）", "27.83s / 语音 14.42 / 静音 13.41 / 真人 29.41s 的 94.6%",
      "E_rate071_rhythm.wav", 0.8801, None)]))

GROUPS.append((
    "B · 停顿序列逐位对照（E vs 真人）",
    "真人 9 个间隙：<code>1.15 1.55 1.07 1.01 1.70 1.17 1.28 1.48 1.51</code>　"
    "E 的 11 个间隙（含两个词内微停顿）：<code>1.15 1.55 <b>0.22 0.10</b> 1.14 1.01 1.70 1.38 1.28 1.48 1.51</code>　"
    "剔除微停顿后 9 个里有 <b>7 个与真人完全一致</b>，另 2 个（1.14 / 1.38）本来就更长，故不动。",
    [("E_rate071_rhythm", "E · 移植后", "静音 13.41s vs 真人 11.96s（多出的来自那两个 0.22/0.10 微间隙 + 两处原本更长的停顿）",
      "E_rate071_rhythm.wav", 0.8801, None),
     ("D_rhythm", "D · 移植后（不减速）", "静音 13.23s / 语音 13.21s —— 停顿对了，但语音仍快 32%",
      "D_rhythm.wav", 0.8689, None),
     ("A_plain", "A · 移植前", "静音 8.55s / 间隙中位 0.78 —— 模型自带停顿只有真人 71%",
      "A_plain.wav", 0.8147, None)]))

GROUPS.append((
    "C · 编译器在这段文本上的决策（--explain 摘要）",
    "10 个子句，rate 0.68~0.81；短句（≤3 词）放慢、连接词起句换气、段末长停 +0.60。"
    "<b>但 safe 模式整段只输出一个 rate 0.84</b> —— 因为实测多个 rate span 会丢词。",
    [("B_safe", "B · safe 输出的标签", '<rate factor="0.84">整段</rate>（无 pause，停顿全部交给后期）',
      "B_safe.wav", 0.8045, None)]))

rows_html = []
for title, sub, items in GROUPS:
    body = "".join(row(*it) for it in items)
    rows_html.append('<section class="card"><h2>%s</h2><p class="note">%s</p>%s</section>'
                     % (title, sub, body))

html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>《我是城堡之王》44 词新段落 · 韵律移植</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--fg:#e8eaf0;--dim:#9aa3b2;--acc:#ff6b5b;--ok:#54d18c;--bd:#252a34}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;padding:28px 20px 80px}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:25px;margin:0 0 6px;letter-spacing:-.3px}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:20px 22px;margin-bottom:18px}
.card h2{font-size:16.5px;margin:0 0 4px;color:#fff}
.note{color:var(--dim);font-size:13px;margin:0 0 12px}
.row{display:grid;grid-template-columns:1fr 118px;gap:8px 14px;align-items:center;padding:10px 0;border-top:1px solid #1e232c}
.row:first-of-type{border-top:0}
.lbl b{font-size:14px;font-weight:600}
.lbl code{display:inline-block;margin-left:8px;background:#0b0d11;border:1px solid #2b3240;color:#ffb3a8;padding:1px 6px;border-radius:5px;font-size:11.5px;font-family:ui-monospace,Consolas,monospace}
.hintline{display:block;color:var(--dim);font-size:12px;margin-top:2px}
.meta{text-align:right}
.dur{font-family:ui-monospace,Consolas,monospace;font-size:13.5px;color:var(--ok);display:block}
.pct{display:block;font-size:11.5px;color:var(--dim);font-family:ui-monospace,monospace}
audio{grid-column:1/-1;width:100%%;height:32px;filter:invert(.92) hue-rotate(180deg)}
table{width:100%%;border-collapse:collapse;font-size:13.5px;margin-top:8px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid #1e232c}
th{color:var(--dim);font-weight:500;font-size:12.5px}
.k{color:#ffd479}.warn{color:var(--acc)}.good{color:#54d18c}
ul{margin:10px 0 0;padding-left:20px}li{margin:5px 0}
</style></head><body><div class="wrap">
<h1>《我是城堡之王》44 词新段落 · 真人停顿移植</h1>
<div class="sub">Susan Hill《I Am the King of the Castle》· dots.tts GGUF q8_0 / RX 580 Vulkan · 参考 = baseA · seed 42 · 音色 = WeSpeaker CAM++ vs real_trim</div>
__ROWS__
<section class="card">
<h2>结论</h2>
<ul>
<li><b class="good">E 是五版里最好的：27.83s / 音色 0.8801</b>，已进入真人跨段天花板（0.88~0.91）下沿。基线 A 只有 0.8147。</li>
<li><b class="k">音色提升主要来自「插入真人真实停顿」</b>：D（A+停顿）0.8689 比 A 高 0.054；E（C+停顿）0.8801 比 C 高 0.021。插入的是真人静音片段（带底噪与换气），不是数字零，所以不需要再铺 room tone。</li>
<li><b class="warn">rate 在这段文本上兑现率极低</b>：0.84 让语音从 13.21→13.35s（+1%），0.71 只到 14.42s（+9.2%）。同样 0.71 在 38 词的 Wonder 段上能到 +19%。<b>长文本上整段 rate 会被稀释。</b></li>
<li><b>缺口定位</b>：E 的语音 14.42s vs 真人 17.45s（还差 3.03s），静音 13.41s 已超过真人 11.96s。也就是说<b>停顿已经够了，剩下的是语速</b>。</li>
<li><b>内容零错误</b>：五版 ASR 回读 44 词全部命中（C 版 <code>until</code> 曾被识为 <code>till</code>，是 ASR 的错）。</li>
</ul>
</section>
<section class="card">
<h2>逐版数据</h2>
<table>
<tr><th>版本</th><th>总长</th><th>语音</th><th>静音</th><th>间隙数</th><th>音色</th></tr>
<tr><td>真人（Wonder 段）</td><td>29.41</td><td class="k">17.45</td><td>11.96</td><td>9</td><td>—</td></tr>
<tr><td>A · 无标签</td><td>21.76</td><td>13.21</td><td>8.55</td><td>9</td><td>0.8147</td></tr>
<tr><td>B · rate 0.84</td><td>19.20</td><td>13.35</td><td>5.85</td><td>9</td><td>0.8045</td></tr>
<tr><td>C · rate 0.71</td><td>24.48</td><td>14.42</td><td>10.06</td><td>11</td><td>0.8595</td></tr>
<tr><td>D · A + 停顿移植</td><td>26.44</td><td>13.21</td><td>13.23</td><td>9</td><td>0.8689</td></tr>
<tr><td><b>E · C + 停顿移植</b></td><td><b>27.83</b></td><td><b>14.42</b></td><td><b>13.41</b></td><td>11</td><td><b class="good">0.8801</b></td></tr>
</table>
</section>
<section class="card">
<h2>完整源文本（44 词）</h2>
<p class="note">取自 <code>G:/_setup/dots_test/castle40.txt</code>，未改动。</p>
<table>
<tr><td>Three months ago, his grandmother died, and then they had moved to this house. 'I will not live there again, until it belongs to me,' his father had said. Though the old man lay upstairs, after a second stroke, and lingered, giving no trouble.</td></tr>
</table>
</section>
</div></body></html>"""

html = html.replace("__ROWS__", "".join(rows_html))
open(HTML, "w", encoding="utf-8").write(html)
print("wrote %s  (%.2f MB)" % (HTML, os.path.getsize(HTML) / 1e6))
