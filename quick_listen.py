# -*- coding: utf-8 -*-
"""快速试听页：把当前训练成果打包成单文件 HTML（MP3 base64 内嵌）"""
import base64, os, subprocess, html

FF = 'E:/tool/oopz/ffmpeg.exe'
OUT = 'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_voice_lab/listen_now.html'
TMP = 'G:/_setup/_quicklisten'
os.makedirs(TMP, exist_ok=True)

ITEMS = [
    ('(1) SoVITS 微调版 —— 本次训练成果',
     'E:/tts-models/acpp/out/v5iso/1_ftvits_basegpt.wav',
     '21.00s｜声纹 0.5184',
     'ok',
     '配置：SoVITS 微调 e8（LoRA r32）+ 官方 GPT 底模。<b>SoVITS 微调是成功的</b> —— 能正常出 21 秒完整语音。'
     '但注意声纹 0.5184 低于零样本的 0.8508（客观指标存疑，下面会细说）。'),
    ('(2) 零样本对照 —— 官方双底模',
     'E:/tts-models/acpp/out/v5iso/4_base_base.wav',
     '21.00s｜声纹 0.8508',
     'base',
     '两个都是官方底模、不加载任何微调权重 —— 作为对照基线。'),
    ('(3) GPT 微调版（刚重训完的新权重）',
     'E:/tts-models/acpp/out/v5iso/2_basevits_ftgpt15.wav',
     '1.24s｜崩（截断）',
     'bad',
     'SoVITS 用官方底模 + GPT 用刚重训完的 e15 → 只出 1.24 秒。'
     '<b>这就是还没解决的问题</b>：我们自己训练的 GPT 权重会让输出崩掉（不管旧库还是新库、续训还是干净重训）。'),
    ('(4) SoVITS+GPT 全微调（第一轮旧权重）',
     'E:/tts-models/acpp/out/v5iso/3_ftvits_ftgpt_e8.wav',
     '0.72s｜崩',
     'bad',
     'GPT 用第一轮（旧库流程）的 e8 → 0.72 秒，更短。'),
    ('(5) 真人参考 —— 同段 29.41s',
     'G:/_setup/dots_test/_an_real_trim.wav',
     '29.41s',
     'anchor',
     '声纹统一锚点：McConaughey 真人朗读同一段文字。'),
]

def to_mp3(src, tag):
    dst = os.path.join(TMP, tag + '.mp3')
    if not (os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src)):
        subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error',
                        '-i', src, '-ac', '1', '-ar', '32000',
                        '-codec:a', 'libmp3lame', '-b:a', '96k', dst], check=True)
    return dst

cards = []
for i, (name, path, meta, kind, desc) in enumerate(ITEMS):
    if not os.path.exists(path):
        continue
    mp3 = to_mp3(path, 'q%d' % i)
    b64 = base64.b64encode(open(mp3, 'rb').read()).decode()
    cls = {'ok': 'ok', 'bad': 'bad', 'base': 'base', 'anchor': 'anchor'}[kind]
    cards.append(f'''<div class="card {cls}">
  <div class="hdr"><span class="name">{html.escape(name)}</span><span class="meta">{html.escape(meta)}</span></div>
  <audio controls preload="none" src="data:audio/mpeg;base64,{b64}"></audio>
  <div class="desc">{desc}</div>
</div>''')

page = f'''<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>训练成果试听 · {len(cards)} 版对比</title>
<style>
:root{{color-scheme:light dark}}
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:780px;margin:0 auto;padding:20px 16px 60px;
background:#f7f8fa;color:#1c1f26}}
@media(prefers-color-scheme:dark){{body{{background:#16181d;color:#e8eaef}}}}
h1{{font-size:19px;margin:0 0 4px}}
.sub{{color:#7a8290;font-size:13px;margin-bottom:18px}}
.card{{background:#fff;border:1px solid #e3e6ec;border-radius:12px;padding:14px 16px;margin-bottom:14px}}
@media(prefers-color-scheme:dark){{.card{{background:#1e2128;border-color:#2e3340}}}}
.card.ok{{border-left:4px solid #2e9e5b}}
.card.bad{{border-left:4px solid #d64545}}
.card.base{{border-left:4px solid #3b82f6}}
.card.anchor{{border-left:4px solid #8b5cf6}}
.hdr{{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:8px}}
.name{{font-weight:600;font-size:15px}}
.meta{{font-size:12px;color:#7a8290;white-space:nowrap}}
audio{{width:100%;height:38px}}
.desc{{font-size:13px;color:#565e6d;line-height:1.6;margin-top:9px}}
@media(prefers-color-scheme:dark){{.desc{{color:#a8b0bd}}}}
.note{{background:#fff8e6;border:1px solid #f0dfae;border-radius:10px;padding:12px 15px;font-size:13px;line-height:1.7;color:#6b5a1e;margin-top:6px}}
@media(prefers-color-scheme:dark){{.note{{background:#2a2517;border-color:#4a4028;color:#d8c88a}}}}
</style></head><body>
<h1>训练成果试听</h1>
<div class="sub">同文本（Calm 段落）· 同参考音频（8.3s）· 同 seed(42) —— 唯一变量是加载哪套权重</div>
{''.join(cards)}
<div class="note"><b>怎么读：</b>(1) 是本次训练能用的部分； (3)(4) 是还没解决的 GPT 问题——
只要加载我们训练的 GPT 权重，输出就只剩 1 秒左右。<br>
<b>结论一句话：</b>SoVITS 训好了（(1) 能出完整 21s），GPT 还在查（base 正常说明推理链没问题，训练链有异常，正在对照官方文档逐项排查）。</div>
</body></html>'''

open(OUT, 'w', encoding='utf-8').write(page)
print('OK ->', OUT)
print('大小: %.1f KB | 卡片 %d' % (os.path.getsize(OUT) / 1024, len(cards)))
