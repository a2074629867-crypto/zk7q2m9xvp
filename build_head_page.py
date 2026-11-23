# -*- coding: utf-8 -*-
"""build_head_page.py —— 《Wonder》开头段 edit 成品试听页 + 微调可行性（离线单文件，内嵌 MP3）"""
import base64, os, subprocess, tempfile
import soundfile as sf

OUT = "G:/_setup/dots_edit2"
HTML = "G:/_setup/dots_head_ab.html"
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
    "A · 开头段（0.57~33.24s）：真人 vs edit 重念",
    "按句边界切成 3 块（6.40s / 11.06s / 9.17s），各自过 edit，再用<b>真实停顿</b>拼回。"
    "音色对「同区域真人原声」测 —— 0.9226，与 771s 那段的 0.9458 基本持平。",
    [("", "真人原声（对照）", "0.57~33.24s，故事开场「as we begin our story…」", "HEAD_real_32.7s.wav", None, None),
     ("HEAD_full", "★ edit 成品（忠实停顿 32.6s）", "保留真实的 5.58s 开场停顿 · 音色 0.9226（对同段真人）", "HEAD_full_32.6s.wav", 0.9226, None),
     ("HEAD_tight", "edit 成品（紧凑停顿 28.2s）", "开场停顿压到 1.2s · 音色 0.9139", "HEAD_tight_28.2s.wav", 0.9139, None)]))

GROUPS.append((
    "B · 单块对照（看哪一块掉分）",
    "三块各自单独测，锚点 = 开头真人原声。H1（12 词短句）最低 0.7648，H2（27 词）最高 0.8726。",
    [("HE1", "H1 · 6.88s（as we begin our story…）", "12 词，最短 —— 声纹估计天然不稳", "HE1.wav", 0.7648, None),
     ("HE2", "H2 · 11.04s（the rattle of an antique telescope…）", "27 词，最长块", "HE2.wav", 0.8726, None),
     ("HE3", "H3 · 8.64s（soothing breeze drifted in…）", "24 词", "HE3.wav", 0.7906, None)]))

GROUPS.append((
    "C · 与上一轮 771s 段成品对比（注意锚点不同）",
    "两段用<b>各自的同区域真人原声</b>做锚点，才可比。若统一用 768s 的 real_trim 做锚点，"
    "开头真人原声自己也只有 0.7030 —— 那是录音位置差异，不是音色差异。",
    [("FULL", "771s 段 · edit 成品 28.5s", "锚点 real_trim(768s) = 0.9458（同区域，天然高）", "FULL_edit_28.5s.wav", 0.9458, None),
     ("HEAD_full", "开头段 · edit 成品 32.6s", "锚点 real_trim(768s) = 0.7586，但锚点 = 开头真人时是 0.9226", "HEAD_full_32.6s.wav", 0.9226, "见说明"),
     ("HEAD_real", "开头段 · 真人原声 32.7s", "连真人自己都只有 0.7030（对 768s 锚点）⇒ 跨区域不可比", "HEAD_real_32.7s.wav", 0.7030, "锚点偏置")]))

rows_html = []
for title, sub, items in GROUPS:
    body = "".join(row(*it) for it in items)
    rows_html.append('<section class="card"><h2>%s</h2><p class="note">%s</p>%s</section>'
                     % (title, sub, body))

html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dots.edit · 《Wonder》开头段成品</title>
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
<h1>《Wonder》开头段 · dots.edit 成品</h1>
<div class="sub">源音频 0.57~33.24s（故事开场）· 三块分治后按真实停顿拼回 · RX 580 Vulkan · seed 42 · 音色 = WeSpeaker CAM++</div>
__ROWS__
<section class="card">
<h2>结论</h2>
<ul>
<li><b class="good">开头段效果与 771s 那段持平</b>：对同区域真人原声 0.9226（771s 段是 0.9458）。差异在锚点，不在音色。</li>
<li><b class="k">锚点偏置必须说清</b>：<code>real_trim</code> 在 768s。用它做锚点时，<b>开头真人原声自己只有 0.7030</b>，而我们的成品是 0.7586 —— 已经比真人原声更接近 768s 那段的音色。所以跨区域比较数字没有意义。</li>
<li><b class="good">内容全对</b>：ASR 回读连藏在 5.58s 停顿里的「wonder. It」都读出来了，36 词仅 Zoe 被 ASR 误识为 Ellie/Oli（模型发音正常）。</li>
<li><b>短块声纹偏低</b>：H1 只有 12 词，0.7648 —— 声纹估计对短音频天然不稳，不是质量问题。</li>
</ul>
</section>
<section class="card">
<h2>微调可行性（dots.tts 官方）</h2>
<table>
<tr><th>项目</th><th>官方现状</th></tr>
<tr><td>训练入口</td><td><code>accelerate launch scripts/train_dots_tts.py --config configs/dots_tts.yaml</code> ✓ 有</td></tr>
<tr><td>数据格式</td><td>JSONL：<code>{"fid","audio","text"}</code>，48kHz，每 7680 采样 = 1 token（6.25 token/s）</td></tr>
<tr><td>优化方式</td><td><b class="warn">全参数 AdamW</b>（<code>model.parameters()</code>），<b>无 LoRA、无冻结开关</b></td></tr>
<tr><td>模型规模</td><td>2B（Qwen2 主干 + 6 层 encoder + 18 层 DiT）</td></tr>
<tr><td>显存估算</td><td>bf16 权重 4G + 梯度 4G + AdamW 两个 fp32 动量 16G ≈ <b class="warn">24GB 起步</b>，加激活/VAE 实际 40GB+</td></tr>
<tr><td>本机</td><td>RX 580 8GB + 16GB RAM ⇒ <b class="warn">跑不了</b></td></tr>
<tr><td>GGUF/acpp</td><td>仅推理（<code>--help</code> 无 lora / train 选项）</td></tr>
</table>
</section>
</div></body></html>"""

html = html.replace("__ROWS__", "".join(rows_html))
open(HTML, "w", encoding="utf-8").write(html)
print("wrote %s  (%.2f MB)" % (HTML, os.path.getsize(HTML) / 1e6))
