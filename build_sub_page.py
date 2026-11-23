# -*- coding: utf-8 -*-
"""build_sub_page.py —— dots.edit 换内容实验页（instruction 补上后的突破 + 韵律继承验证）"""
import base64, os, subprocess, tempfile
import soundfile as sf

OUT = "G:/_setup/dots_edit2"
HTML = "G:/_setup/dots_sub_ab.html"
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


def row(label, hint, path, spk=None, note=None, hl=False):
    p = os.path.join(OUT, path)
    if not os.path.exists(p):
        return ""
    d = dur(p)
    meta = '<span class="dur">%.2fs</span>' % d
    if spk:
        meta += '<span class="pct">音色 %.4f</span>' % spk
    if note:
        meta += '<span class="pct">%s</span>' % note
    b64 = mp3_b64(p)
    return ('<div class="row%s"><div class="lbl"><b>%s</b>'
            '<span class="hintline">%s</span></div><div class="meta">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (" hl" if hl else "", label, hint, meta, b64))


GROUPS = []

GROUPS.append((
    "A · 换内容（同一个源音频，念完全不同的新文本）",
    "源音频是 50.91~65.59s 的「A stock of prized possessions sat on Zoe's shelves…」（29 词，118.5 wpm）。"
    "新文本是 31 词的另一段话。"
    "<b>关键：必须传 <code>--request-option instruction</code></b>，"
    "格式 <code>&lt;sub targ=\"新文本\"&gt;旧文本&lt;/sub&gt;</code>。之前漏传这个参数，"
    "模型收到的原文=目标文，所以只会复刻。",
    [("", "源音频（真人原话）", "P1 · 14.68s · 29词 · 118.5wpm · 「A stock of prized possessions…」",
      "P1_14.68s.wav", None, None),
     ("★ SUB_AUTO（xvector=auto）", "念出了全新文本 · 音色 0.7799", "SUB_AUTO.wav", 0.7799, None, True),
     ("SUB_A（xvector=off）", "念出了全新文本，但音色崩到 0.4235", "SUB_A.wav", 0.4235, None),
     ("PE1（复刻对照）", "不传 instruction 时的结果：原话重念，音色 0.8599", "PE1.wav", 0.8599, None)]))

GROUPS.append((
    "B · 韵律继承测试（决定性）",
    "同一段新文本，换两个语速差 38% 的源音频：<b>P1 = 118.5 wpm</b> vs <b>P3 = 164 wpm</b>。"
    "如果韵律会继承，两版输出时长应该差 20~30%。"
    "<b>实测都是 9.76s，一秒不差</b> —— 说明源音频只给音色，不给韵律。",
    [("SUB_A（源 P1 · 118.5wpm）", "xvector=off", "SUB_A.wav", 0.4235, "9.76s"),
     ("SUB_FAST（源 P3 · 164wpm）", "xvector=off · 同一新文本", "SUB_FAST.wav", 0.4799, "9.76s")]))

CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#252a34;--tx:#e6e8ee;--dim:#98a0b3;--acc:#6ea8fe;--good:#4ade80;--bad:#f87171;--warn:#fbbf24}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px 80px;background:var(--bg);color:var(--tx);
font:15px/1.7 -apple-system,"Segoe UI",system-ui,"Microsoft YaHei",sans-serif}
.wrap{max-width:920px;margin:0 auto}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.3px}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:28px}
h2{font-size:17px;margin:34px 0 10px;padding-left:10px;border-left:3px solid var(--acc)}
.note{color:var(--dim);font-size:13px;margin:0 0 14px;padding:12px 14px;background:var(--card);
border:1px solid var(--line);border-radius:10px}
.note code{background:#222732;padding:1px 5px;border-radius:4px;font-size:12px;color:#c9d1e0}
.row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:13px 15px;margin-bottom:9px;
background:var(--card);border:1px solid var(--line);border-radius:11px}
.row.hl{border-color:#3a5a8a;background:#1a2233}
.lbl{flex:1 1 300px;min-width:260px}
.lbl b{font-size:14.5px;font-weight:600}
.hintline{display:block;color:var(--dim);font-size:12.5px;margin-top:3px}
.meta{display:flex;gap:8px;flex-wrap:wrap;font-size:12px}
.dur{background:#222732;padding:2px 8px;border-radius:6px;color:#c9d1e0;font-variant-numeric:tabular-nums}
.pct{background:#2a2233;padding:2px 8px;border-radius:6px;color:#c4a8e8;font-variant-numeric:tabular-nums}
audio{width:100%;max-width:340px;height:34px}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:6px 0 4px;
background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line)}
th{background:#1c2129;color:var(--dim);font-weight:600;font-size:12.5px}
tr:last-child td{border-bottom:none}
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.k{color:var(--acc);font-weight:600}
ul{margin:8px 0 0;padding-left:22px}
li{margin-bottom:7px}
.foot{margin-top:36px;color:#6b7385;font-size:12px;border-top:1px solid var(--line);padding-top:16px}
"""

cards = []
for title, note, rows in GROUPS:
    cards.append('<h2>%s</h2>\n<p class="note">%s</p>\n%s' % (title, note, "".join(row(*r) for r in rows)))

CONCL = """
<h2>C · 结论</h2>
<table>
<tr><th>版本</th><th>xvector</th><th>源语速</th><th>输出</th><th>内容</th><th>音色</th></tr>
<tr><td>PE1（复刻）</td><td>off</td><td>118.5 wpm</td><td>14.72s</td><td class="warn">源原话</td><td class="good">0.8599</td></tr>
<tr><td>SUB_A</td><td>off</td><td>118.5 wpm</td><td>9.76s</td><td class="good">新文本 ✓</td><td class="bad">0.4235</td></tr>
<tr><td>SUB_FAST</td><td>off</td><td><b>164 wpm</b></td><td><b>9.76s</b></td><td class="good">新文本 ✓</td><td class="bad">0.4799</td></tr>
<tr><td>SUB_AUTO</td><td>auto</td><td>118.5 wpm</td><td>13.76s</td><td class="good">新文本 ✓</td><td class="good">0.7799</td></tr>
</table>
<p class="note">
<b class="k">① 换内容成功</b> —— 补上 <code>instruction</code> 参数后，模型确实念出了全新的 31 词文本，ASR 逐字核对无误。
之前「target_text 被忽略」的判断是<b>参数漏传造成的假象</b>，已更正。<br><br>
<b class="k">② 韵律不继承源音频</b> —— 源 118.5 wpm 与 164 wpm 差 38%，同一新文本输出<b>都是 9.76s，一秒不差</b>。
源音频在上下文里只充当「音色条件」，生成长度完全由目标文本决定。<br><br>
<b class="k">③ 音色</b> —— 换内容时 <code>xvector=off</code> 会崩（0.42~0.48），必须用 <code>auto</code>（0.78）。
但仍低于复刻时的 0.86，更低于 GSV 的 0.90。<br><br>
<b class="warn">④ 定位</b> —— dots.edit 换内容 = 一个「能念新文本的 TTS，音色 0.78」。
它<b>不是韵律克隆工具</b>。要韵律只有两条真路：<b>微调</b>（需 GPU）或 <b>IndexTTS 的 emo_audio_prompt</b>。
</p>
"""

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dots.edit 换内容实验 · 韵律继承验证</title>
<style>%s</style></head><body><div class="wrap">
<h1>dots.edit 换内容实验</h1>
<div class="sub">补上 <code style="background:#222732;padding:1px 5px;border-radius:4px">instruction</code> 参数后的突破 · 以及韵律到底有没有继承源音频</div>
%s
%s
<div class="foot">
源音频：<code>G:/GPT-SoVITS/_dataset/wonder_train.wav</code> 50.91~93.79s（DF3+55Hz 未处理母带）·
模型：DotTTS-Edit-GGUF q8_0 · RX580 Vulkan · seed 42 · max_tokens 420 ·
音色基准：同区域真人原声 P50_real_42.9s.wav（WeSpeaker CAM++）
</div>
</div></body></html>""" % (CSS, "".join(cards), CONCL)

open(HTML, "w", encoding="utf-8").write(html)
print("written %s  %.2f MB" % (HTML, os.path.getsize(HTML) / 1e6))
