# -*- coding: utf-8 -*-
"""build_p50_page.py —— 《Wonder》50s 之后段落 edit 成品试听页（离线单文件，内嵌 MP3）"""
import base64, os, subprocess, tempfile
import soundfile as sf

OUT = "G:/_setup/dots_edit2"
HTML = "G:/_setup/dots_p50_ab.html"
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
    return ('<div class="row"><div class="lbl"><b>%s</b>%s'
            '<span class="hintline">%s</span></div><div class="meta">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (label, ('<code>%s</code>' % name) if name else "", hint, meta, b64))


GROUPS = []

GROUPS.append((
    "A · 50s 之后段落（50.91~93.79s）：真人 vs edit 重念",
    "「A stock of prized possessions sat on Zoe's shelves…」到「her big sister Andrea had dozed off」。"
    "按句边界切 3 块（14.68s / 13.99s / 12.43s），各自过 edit，再用<b>真实停顿 0.94s / 0.84s</b> 拼回。"
    "音色对<b>同区域真人原声</b>测 —— 0.9121。",
    [("", "真人原声（对照）", "50.91~93.79s，42.88s", "P50_real_42.9s.wav", None, None),
     ("P50_full", "★ edit 成品（42.58s）", "三块拼接 · 音色 0.9121（对同段真人）· ASR 逐字一致", "P50_full_42.6s.wav", 0.9121, None)]))

GROUPS.append((
    "B · 单块对照（看哪一块掉分）",
    "锚点 = 50s 段真人原声。三块都 ≥0.86，P3（34 词最长）0.8900 反而最高。",
    [("PE1", "P1 · 14.72s（A stock of prized possessions…）", "29 词 · 音色 0.8599", "PE1.wav", 0.8599, None),
     ("PE2", "P2 · 13.92s（Green birds, blue bears…）", "26 词 · 音色 0.8842", "PE2.wav", 0.8842, None),
     ("PE3", "P3 · 12.16s（She knew they weren't to scale…）", "34 词 · 音色 0.8900", "PE3.wav", 0.8900, None)]))

GROUPS.append((
    "C · 三段区域横向对比（同一套流程、各自同区域锚点）",
    "每段都用<b>自己的同区域真人原声</b>做锚点，这样才可比。三段全部 0.91~0.95。",
    [("P50_full", "50s 段 · 42.58s", "锚点 = 50s 真人原声 → 0.9121", "P50_full_42.6s.wav", 0.9121, None),
     ("HEAD_full", "开头段 · 32.60s", "锚点 = 开头真人原声 → 0.9226", "HEAD_full_32.6s.wav", 0.9226, None),
     ("FULL", "771s 段 · 28.50s", "锚点 = 771s 真人原声 → 0.9458", "FULL_edit_28.5s.wav", 0.9458, None)]))

GROUPS.append((
    "D · 锚点偏置演示（为什么不能用 real_trim 横比）",
    "锚点统一换成 768s 的 real_trim：<b>三段真人原声自己都只有 0.70 左右</b>，而成品都比真人原声高 0.04~0.06。"
    "说明这是录音位置差异，不是音色差异。",
    [("P50_real", "50s 段 · 真人原声", "对 real_trim = 0.7010", "P50_real_42.9s.wav", 0.7010, "真人本身"),
     ("P50_full", "50s 段 · edit 成品", "对 real_trim = 0.7473", "P50_full_42.6s.wav", 0.7473, "高于真人"),
     ("HEAD_real", "开头段 · 真人原声", "对 real_trim = 0.7030", "HEAD_real_32.7s.wav", 0.7030, "真人本身"),
     ("HEAD_full", "开头段 · edit 成品", "对 real_trim = 0.7586", "HEAD_full_32.6s.wav", 0.7586, "高于真人"),
     ("FULL", "771s 段 · edit 成品", "对 real_trim = 0.9458 —— 同区域，天然高", "FULL_edit_28.5s.wav", 0.9458, "同区域")]))

rows_html = []
for title, sub, items in GROUPS:
    body = "".join(row(*it) for it in items)
    rows_html.append('<section class="card"><h2>%s</h2><p class="note">%s</p>%s</section>'
                     % (title, sub, body))

html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dots.edit · 《Wonder》50s 之后段落</title>
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
audio{grid-column:1/-1;width:100%;height:32px;filter:invert(.92) hue-rotate(180deg)}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:8px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid #1e232c}
th{color:var(--dim);font-weight:500;font-size:12.5px}
.k{color:#ffd479}.warn{color:var(--acc)}.good{color:#54d18c}
ul{margin:10px 0 0;padding-left:20px}li{margin:5px 0}
</style></head><body><div class="wrap">
<h1>《Wonder》50s 之后段落 · dots.edit 成品</h1>
<div class="sub">源音频 50.91~93.79s（Zoe 房间描写）· 三块分治后按真实停顿拼回 · RX 580 Vulkan · seed 42 · 音色 = WeSpeaker CAM++</div>
__ROWS__
<section class="card">
<h2>结论</h2>
<ul>
<li><b class="good">时长几乎 1:1 复刻</b>：成品 42.58s vs 真人 42.88s，误差 0.30s。三块分别 14.72 / 13.92 / 12.16s，源是 14.68 / 13.99 / 12.43s。</li>
<li><b class="good">内容逐字一致</b>：ASR 回读成品与真人原声两段文字几乎完全相同，连 ASR 把 <code>thumbtacks</code> 误识成 <code>thumbtags</code>、<code>dozed</code> 误识成 <code>doz</code> 都一致 —— 说明是 ASR 的问题，不是生成的。</li>
<li><b class="k">音色 0.9121（对同区域真人）</b>：比开头段 0.9226 略低、比 771s 段 0.9458 低一些，但同属 0.91~0.95 这一档。</li>
<li><b class="warn">这一段没有长停顿</b>：真实间隙只有 0.94s 和 0.84s，所以不像开头段需要「紧凑版」——直接就是可用的连续朗读。</li>
<li><b>分块上限</b>：<code>max_tokens</code> ≈ 源长 × 25。14.68s 用 367、13.99s 用 350、12.43s 用 311，全部一次过、无 OOM。</li>
</ul>
</section>
<section class="card">
<h2>完整源文本（50.91~93.79s）</h2>
<p class="note">从 <code>logs/mcconaughey_v6/2-name2text.txt</code> 直接取，未手工改动。</p>
<table>
<tr><td>A stock of prized possessions sat on Zoe's shelves. Dinosaur figurines, picture books, and a paper mache giraffe.
Purple thumbtacks held some of her finest drawings on the wall. Green birds, blue bears, and red fish.
Cardboard models of the planets hung from the ceiling. From Mercury to Neptune, and even Pluto for good measure.
She knew they weren't to scale, but such were the limits of the seven year old bedroom.
In the bed next to Zoe's, her big sister Andrea had dozed off and was sleeping soundly.</td></tr>
</table>
</section>
</div></body></html>"""

html = html.replace("__ROWS__", "".join(rows_html))
open(HTML, "w", encoding="utf-8").write(html)
print("wrote %s  (%.2f MB)" % (HTML, os.path.getsize(HTML) / 1e6))
