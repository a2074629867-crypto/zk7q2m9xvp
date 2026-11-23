# -*- coding: utf-8 -*-
"""build_edit_page.py —— dots.edit 源音频 / 参考音频 对照试听页（离线单文件，内嵌 MP3）"""
import base64, os, subprocess, tempfile
import soundfile as sf

OUT = "G:/_setup/dots_edit2"
HTML = "G:/_setup/dots_edit_ab.html"
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
    "A · 完整成品：edit 模式重念真人原段（28.5s）",
    "把真人 771.07~799.76s 那段原声按句边界拆成两块，各自过一遍 edit，再用真实的 0.66s 句间空隙拼回。"
    "输出时长 28.50s，真人 28.69s。",
    [("", "真人原声（对照）", "771.07~799.76s，未经任何处理", "SRC_real_28.69s.wav", 0.8847, None),
     ("FULL", "★ edit 成品（两段拼接）", "音色 0.9458 —— 本项目历史最高（此前 TTS 最好 0.8641）", "FULL_edit_28.5s.wav", 0.9458, None)]))

GROUPS.append((
    "B · 音色到底由谁决定：改参考 / 改 xvector 都不动",
    "同一段真人源音频（771.07~786.20s），只改 voice-ref 与 use_xvector。"
    "三版时长一模一样，音色也一模一样 —— 说明 edit 模式下参考音频完全无效。",
    [("V1", "xvector=off + 参考=baseA（566s）", "音色 0.9464 · ASR 逐字全对", "V1_c1_off_baseA.wav", 0.9464, None),
     ("V2", "xvector=off + 参考=早段（33.69s）", "换成开头 8.54s 做参考 —— 结果与 V1 完全相同（0.9464）", "V2_c1_off_early.wav", 0.9464, None),
     ("V3", "xvector=auto（用源音色）", "0.9460，且 ASR 出现重复词「swirling in lakes, swirling in oceans」", "V3_c1_auto.wav", 0.9460, "有重复")]))

GROUPS.append((
    "C · 换「更靠前」的音频：两种用法都试了，都更差",
    "① 当参考音频用（TTS 模式，rate 0.60）；② 当源音频用（edit 模式，538.75~553.88s）。",
    [("TTS_baseA", "TTS · 参考=baseA（566s）", "对照：24.64s / 音色 0.8990", "TTS_rate060_baseA.wav", 0.8990, None),
     ("TTS_early", "TTS · 参考=开头（24.07s，9.17s）", "换成更靠前的参考后掉到 0.7547（-0.144）", "TTS_rate060_earlyref.wav", 0.7547, "明显更差"),
     ("E1", "edit · 源=早段（538.75s，15.13s）", "0.8021（对照 0.9464）。注意：内容变成那一段自己的文字了", "E1_early_src.wav", 0.8021, "内容不同")]))

rows_html = []
for title, sub, items in GROUPS:
    body = "".join(row(*it) for it in items)
    rows_html.append('<section class="card"><h2>%s</h2><p class="note">%s</p>%s</section>'
                     % (title, sub, body))

html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dots.edit 源音频 / 参考音频 对照</title>
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
<h1>dots.edit：换「更靠前」的音频，反而更不像</h1>
<div class="sub">dots.tts Edit GGUF q8_0 · RX 580 Vulkan · 同文本 / 同 seed 42 · 音色 = WeSpeaker CAM++ 对真人锚点 real_trim.wav</div>
__ROWS__
<section class="card">
<h2>结论</h2>
<ul>
<li><b class="k">edit 模式下，参考音频（voice-ref）完全不起作用</b> —— V1 与 V2 只是换了参考，时长、音色（0.9464 vs 0.9464）、内容全部一致。音色只由<b>源音频</b>决定。</li>
<li><b class="good">edit 是目前最好的路线</b>：28.50s 成品音色 0.9458，比之前 TTS 最好成绩（rate 0.60 的 0.8641）高 8 个点，且韵律直接沿用真人（28.50s vs 真人 28.69s）。</li>
<li><b class="warn">换更靠前的音频，两种用法都更差</b>：当参考用 0.8990 → 0.7547；当源用 0.9464 → 0.8021。</li>
<li><b class="warn">换源音频还有个副作用</b>：edit 只重念源音频<b>自己</b>的内容 —— 传 target_text 也不管用（实测输出仍是源音频的原话）。所以源音频必须是「真人已经在念你要的那段文字」。</li>
</ul>
</section>
<section class="card">
<h2>全部数字</h2>
<table>
<tr><th>文件</th><th>模式 / 配置</th><th>时长</th><th>音色</th></tr>
<tr><td>真人原声 771.07~799.76s</td><td>—</td><td>28.69s</td><td>0.8847</td></tr>
<tr><td><b>FULL_edit_28.5s</b></td><td>edit · 两段拼接</td><td>28.50s</td><td><b class="good">0.9458</b></td></tr>
<tr><td>V1_c1</td><td>edit · xvector=off · ref=baseA</td><td>15.04s</td><td><b class="good">0.9464</b></td></tr>
<tr><td>V2_c1</td><td>edit · xvector=off · ref=早段33.69s</td><td>15.04s</td><td>0.9464（与 V1 相同）</td></tr>
<tr><td>V3_c1</td><td>edit · xvector=auto</td><td>15.04s</td><td>0.9460（有重复词）</td></tr>
<tr><td>E1_early_src</td><td>edit · 源=538.75~553.88s</td><td>15.04s</td><td>0.8021</td></tr>
<tr><td>TTS_rate060_baseA</td><td>TTS · rate 0.60 · ref=baseA</td><td>24.64s</td><td>0.8990</td></tr>
<tr><td>TTS_rate060_earlyref</td><td>TTS · rate 0.60 · ref=开头24.07s</td><td>24.80s</td><td><span class="warn">0.7547</span></td></tr>
</table>
<p class="note" style="margin-top:12px">真人锚点 = <code>E:/tts-models/acpp/out/calmdeep_final/real_trim.wav</code>（29.4s）。同人跨段天花板 0.88~0.91。</p>
</section>
</div></body></html>"""

html = html.replace("__ROWS__", "".join(rows_html))
open(HTML, "w", encoding="utf-8").write(html)
print("wrote %s  (%.2f MB)" % (HTML, os.path.getsize(HTML) / 1e6))
