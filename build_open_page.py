# -*- coding: utf-8 -*-
"""build_open_page.py —— 开头段参考 vs baseA 参考 · 同文本对照试听页"""
import base64
import os
import subprocess
import tempfile

import soundfile as sf

REAL = "E:/tts-models/acpp/out/calmdeep_final/real_trim.wav"
HTML = "G:/_setup/dots_open_page.html"
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


def row(name, label, hint, path, spk=None):
    if not os.path.exists(path):
        return ""
    d = dur(path)
    meta = '<span class="dur">%.2fs</span>' % d
    if spk:
        meta += '<span class="pct">音色 %.4f</span>' % spk
    b64 = mp3_b64(path)
    return ('<div class="row"><div class="lbl"><b>%s</b>%s'
            '<span class="hintline">%s</span></div><div class="meta">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (label, ('<code>%s</code>' % name) if name else "", hint, meta, b64))


O = "G:/_setup/dots_open/"
C2 = "G:/_setup/dots_castle2/"

GROUPS = []

GROUPS.append((
    "A · 同一段文本，只换参考音频（seed 42 不变）",
    "文本：《我是城堡之王》44 词段　参考 A = <b>开头段 24.07~33.24s</b>（9.17s，&ldquo;soothing breeze drifted in…&rdquo;）"
    "　参考 B = baseA 566s 段（8.3s）　两者都跑 rate 0.71 + 真人停顿移植",
    [("real", "真人对照（Wonder 段，非同一段文字）", "只作音色锚点：29.41s / 语音 17.45 / 静音 11.96",
      REAL, None),
     ("E_open", "★ 开头参考 · rate 0.71 + 真人停顿", "26.90s / 语音 13.11 / 静音 13.79 / 间隙中位 1.48（比真人 1.28 还长）",
      O + "E_open_rhythm.wav", 0.6925),
     ("E_base", "☆ baseA 参考 · rate 0.71 + 真人停顿（上一版）", "27.83s / 语音 14.42 / 静音 13.41 / 间隙中位 1.28",
      C2 + "E_rate071_rhythm.wav", 0.8801)]))

GROUPS.append((
    "B · 开头参考的原始两版（不加停顿）",
    "听这两条可以判断：是「音色本身」的问题，还是「停顿结构」的问题",
    [("A_open", "开头参考 · 无标签", "14.56s / 语音 11.12 / 静音 3.44 / <b>只有 2 个间隙</b> —— 模型几乎不停顿",
      O + "A_open.wav", 0.7472),
     ("C_open", "开头参考 · rate 0.71", "23.68s / 语音 13.12 / 静音 10.56 / 9 个间隙",
      O + "C_open.wav", 0.6836),
     ("C_base", "baseA 参考 · rate 0.71（对照）", "24.48s / 语音 14.42 / 静音 10.06 / 11 个间隙",
      C2 + "C_rate071.wav", 0.8595)]))

rows_html = []
for title, sub, items in GROUPS:
    body = "".join(row(*it) for it in items)
    rows_html.append('<section class="card"><h2>%s</h2><p class="note">%s</p>%s</section>'
                     % (title, sub, body))

html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>开头音色 vs baseA · 同文本对照</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--fg:#e8eaf0;--dim:#9aa3b2;--acc:#ff6b5b;--ok:#54d18c;--bd:#252a34}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;padding:28px 20px 80px}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px;letter-spacing:-.3px}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:22px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:20px 22px;margin-bottom:18px}
.card h2{font-size:16.5px;margin:0 0 4px;color:#fff}
.note{color:var(--dim);font-size:13px;margin:0 0 12px}
.row{display:grid;grid-template-columns:1fr 118px;gap:8px 14px;align-items:center;padding:11px 0;border-top:1px solid #1e232c}
.row:first-of-type{border-top:0}
.lbl b{font-size:14px;font-weight:600}
.lbl code{display:inline-block;margin-left:8px;background:#0b0d11;border:1px solid #2b3240;color:#ffb3a8;padding:1px 6px;border-radius:5px;font-size:11.5px;font-family:ui-monospace,Consolas,monospace}
.hintline{display:block;color:var(--dim);font-size:12px;margin-top:2px}
.meta{text-align:right}
.dur{font-family:ui-monospace,Consolas,monospace;font-size:13.5px;color:var(--ok);display:block}
.pct{display:block;font-size:11.5px;color:var(--dim);font-family:ui-monospace,monospace}
audio{grid-column:1/-1;width:100%%;height:34px;filter:invert(.92) hue-rotate(180deg)}
table{width:100%%;border-collapse:collapse;font-size:13.5px;margin-top:8px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid #1e232c}
th{color:var(--dim);font-weight:500;font-size:12.5px}
.k{color:#ffd479}.warn{color:var(--acc)}.good{color:#54d18c}
ul{margin:10px 0 0;padding-left:20px}li{margin:5px 0}
</style></head><body><div class="wrap">
<h1>开头音色 vs baseA · 同文本对照</h1>
<div class="sub">同一段 44 词、同一 seed 42、同一 rate 0.71、同一停顿移植 —— <b>只换参考音频</b>。音色锚点 = real_trim.wav（跨区域统一基准）</div>
__ROWS__
<section class="card">
<h2>数据对照</h2>
<table>
<tr><th>版本</th><th>总长</th><th>语音</th><th>静音</th><th>间隙中位</th><th>音色</th></tr>
<tr><td>真人（Wonder 段）</td><td>29.41</td><td class="k">17.45</td><td>11.96</td><td>1.28</td><td>—</td></tr>
<tr><td>开头参考 · 无标签</td><td>14.56</td><td>11.12</td><td>3.44</td><td>1.09</td><td>0.7472</td></tr>
<tr><td>开头参考 · rate 0.71</td><td>23.68</td><td>13.12</td><td>10.56</td><td>0.92</td><td>0.6836</td></tr>
<tr><td><b>开头参考 · rate + 停顿移植</b></td><td><b>26.90</b></td><td>13.11</td><td><b>13.79</b></td><td><b>1.48</b></td><td class="warn">0.6925</td></tr>
<tr><td>baseA 参考 · rate 0.71</td><td>24.48</td><td>14.42</td><td>10.06</td><td>0.88</td><td>0.8595</td></tr>
<tr><td><b>baseA 参考 · rate + 停顿移植</b></td><td><b>27.83</b></td><td><b>14.42</b></td><td>13.41</td><td>1.28</td><td class="good"><b>0.8801</b></td></tr>
</table>
<p class="note" style="margin-top:12px">声纹数字仅供参考：<b>跨区域锚点有偏置</b>（开头段真人自己对 real_trim 也只有 0.70 左右），所以这组数字会系统性地压低开头参考。
<b>最终以你的耳朵为准。</b></p>
</section>
<section class="card">
<h2>两个观察（供你听的时候对照）</h2>
<ul>
<li><b class="k">开头参考明显更「快」</b>：不加任何标签时只出 14.56s（44 词 = 181 wpm），而 baseA 参考是 21.76s（121 wpm），且<b>只有 2 个间隙</b> —— 开头那段本身语速快、句子之间不停，模型把节奏也一起学过去了。</li>
<li><b class="warn">加 rate + 停顿后总长反而接近</b>（26.90 vs 27.83），但<b>语音只有 13.11s，比 baseA 的 14.42s 还短 1.3s</b>，静音被拉到 13.79s（超过真人 11.96s）。听感上会偏「慢但是句子念得急」。</li>
</ul>
</section>
</div></body></html>"""

html = html.replace("__ROWS__", "".join(rows_html))
open(HTML, "w", encoding="utf-8").write(html)
print("wrote %s  (%.2f MB)" % (HTML, os.path.getsize(HTML) / 1e6))
