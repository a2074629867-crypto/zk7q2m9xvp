# -*- coding: utf-8 -*-
"""build_verify_pack.py —— 给用户自备 ASR 做对照的音频包

产出
----
G:/_setup/_verify/wav/<名>.wav    16k 单声道（喂外部 ASR）
G:/_setup/_verify/mp3/<名>.mp3    128k（试听）
G:/_setup/_verify/verify.html     离线单文件对照页（音频 + 各家输出）
G:/_setup/_verify/texts.json      纯文本对照表

每个片段同时列出：
  · small.en 整段（vad=True, copt=True）—— 目前认为最可信
  · large-v3-turbo 分块（vad=False, copt=False）—— 已知大面积幻觉
  · large-v3-turbo 25s 单窗（vad=False, copt=False）
  · medium.en 25s 单窗
"""
import base64, json, os, subprocess, time
import numpy as np, soundfile as sf
from faster_whisper import WhisperModel

FFMPEG = 'E:/tool/oopz/ffmpeg.exe'
SRC = 'G:/GPT-SoVITS/_dataset/wonder_train.wav'
D = 'G:/GPT-SoVITS/_dataset_v5full'
OUT = 'G:/_setup/_verify'
TURBO = 'G:/asr_models/faster-whisper-large-v3-turbo'
MED = 'G:/asr_models/faster-whisper-medium.en'

REGIONS = [(0, 25, 'head_0-25'),
           (170, 200, 'disputed_170-200'),
           (245, 270, 'r245-270'),
           (860, 885, 'r860-885'),
           (955, 980, 'r955-980'),
           (1340, 1365, 'r1340-1365')]

os.makedirs(OUT + '/wav', exist_ok=True)
os.makedirs(OUT + '/mp3', exist_ok=True)

# ---- small.en 整段文本 ----
A = json.load(open(D + '/asr_full.json', encoding='utf-8'))
def small_text(lo, hi):
    out = []
    for s in A['segments']:
        a = s.get('start'); b = s.get('end')
        if a is None or b < lo or a > hi: continue
        out.append(s.get('text', '').strip())
    return ' '.join(out).strip()

# ---- turbo 分块文本 ----
T = json.load(open(D + '/v2_turbo.json', encoding='utf-8'))
def turbo_chunk_text(lo, hi):
    out = []
    for w in T['windows']:
        if w['t1'] < lo or w['t0'] > hi: continue
        out.append(w['text'].strip())
    return ' '.join(out).strip()

# ---- 切音频（ffmpeg 切割 + 重采样到 16k 单声道）----
x, _ = sf.read(SRC, dtype='float32', always_2d=True); x = x.mean(1)
print('源 %d 帧 (%.1fs)' % (len(x), len(x) / 32000), flush=True)
for lo, hi, nm in REGIONS:
    w = OUT + '/wav/%s.wav' % nm
    m = OUT + '/mp3/%s.mp3' % nm
    subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error',
                    '-i', SRC, '-ss', str(lo), '-t', str(hi - lo),
                    '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', w], check=True)
    subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', w,
                    '-codec:a', 'libmp3lame', '-b:a', '128k', m], check=True)
    print('  切出 %-20s %.1fs' % (nm, hi - lo), flush=True)

# ---- 单窗跑 turbo / medium ----
models = {}
def run(mp, ct, seg):
    key = (mp, ct)
    if key not in models:
        models[key] = WhisperModel(mp, device='cpu', compute_type=ct, cpu_threads=10)
    segs, _ = models[key].transcribe(seg, language='en', beam_size=5, word_timestamps=True,
                                     condition_on_previous_text=False, vad_filter=False)
    return ''.join(s.text for s in segs).strip()

res = {}
for lo, hi, nm in REGIONS:
    seg = x[int(lo * 32000):int(hi * 32000)]
    print('\n[%s]' % nm, flush=True)
    t1 = time.time(); a = run(TURBO, 'int8', seg); print('  turbo int8 %.1fs' % (time.time() - t1), flush=True)
    t1 = time.time(); b = run(MED, 'int8', seg);   print('  meden int8 %.1fs' % (time.time() - t1), flush=True)
    res[nm] = dict(lo=lo, hi=hi, small=small_text(lo, hi), turbo_chunk=turbo_chunk_text(lo, hi),
                   turbo_win=a, med_win=b)

json.dump(res, open(OUT + '/texts.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---- HTML ----
def esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

cards = []
for lo, hi, nm in REGIONS:
    r = res[nm]
    b64 = base64.b64encode(open(OUT + '/mp3/%s.mp3' % nm, 'rb').read()).decode('ascii')
    cards.append("""<div class="card">
  <div class="hd"><b>%s</b> <span class="tm">%.0f–%.0fs（%.0fs）</span>
    <a class="dl" href="wav/%s.wav" download>下载 WAV(16k)</a></div>
  <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>
  <div class="row"><span class="lb ok">small.en 整段</span><div>%s</div></div>
  <div class="row"><span class="lb bad">turbo 分块</span><div>%s</div></div>
  <div class="row"><span class="lb bad">turbo 单窗</span><div>%s</div></div>
  <div class="row"><span class="lb bad">medium 单窗</span><div>%s</div></div>
</div>""" % (nm, lo, hi, hi - lo, nm, b64,
             esc(r['small']), esc(r['turbo_chunk']), esc(r['turbo_win']), esc(r['med_win'])))

HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASR 对照包 · Wonder</title><style>
:root{--bg:#12141a;--card:#1b1e26;--fg:#e8eaf0;--dim:#9aa3b2;--ac:#5cc8ff;--ok:#39d98a;--bad:#ff7b7b;--warn:#ffb454}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;padding:20px 16px 60px}
.wrap{max-width:1000px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:16px;line-height:1.8}
.box{background:var(--card);border:1px solid #2b3140;border-radius:10px;padding:12px 15px;margin:0 0 18px;font-size:12.5px;line-height:1.9}
.box b{color:var(--fg)} .box code{background:#22262f;padding:1px 5px;border-radius:4px}
.card{background:var(--card);border:1px solid #2b3140;border-radius:12px;padding:12px 15px;margin:12px 0}
.hd{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.tm{color:var(--dim);font-size:12.5px;font-family:ui-monospace,monospace}
.dl{margin-left:auto;color:var(--ac);font-size:12.5px;text-decoration:none;border:1px solid #2f4a5e;border-radius:14px;padding:2px 10px}
audio{width:100%;height:34px;margin:4px 0 8px}
.row{display:flex;gap:10px;padding:5px 0;border-top:1px solid #232833;font-size:13.5px}
.lb{flex:0 0 96px;font-size:11.5px;padding:1px 0;color:var(--dim);font-family:ui-monospace,monospace}
.lb.ok{color:var(--ok)} .lb.bad{color:var(--bad)}
.row div{flex:1}
</style></head><body><div class="wrap">
<h1>ASR 对照包 · Wonder（Calm）· Matthew McConaughey</h1>
<div class="sub">源：<code>wonder_train.wav</code> 26.92 min @32kHz。以下片段已切成 <b>16k 单声道 WAV</b>，可直接喂任意 ASR。</div>
<div class="box">
<b>为什么需要你帮忙对照：</b><br>
本机跑 <code>large-v3-turbo</code> 在这段音频上<b>大面积幻觉</b>（67 窗里 27 窗被污染，出现
<code>The dark ... The dark ...</code>、<code>Thank you.</code>、<code>unlocking the clothes</code>×109 这类重复），
<b>medium.en 与 int8/float32 都一样崩</b>；而 <code>small.en</code> 整段转写（<code>vad_filter=True</code> +
<code>condition_on_previous_text=True</code>）输出却是连贯故事文本。<br>
两者差异极大，需要<b>第三方 ASR 裁决</b>。<br><br>
<b>请重点看：</b><code>disputed_170-200</code>（small.en 说 "leaves gliding down from their branches..."，
turbo 说 "I'm going to go from the point of view of the world..."）。<br>
把上面音频丢进你的识别工具，回贴结果即可。
</div>
@@CARDS@@
</div></body></html>"""
HTML = HTML.replace('@@CARDS@@', '\n'.join(cards))
open(OUT + '/verify.html', 'w', encoding='utf-8').write(HTML)
print('\n写出 %s/verify.html  %s/texts.json' % (OUT, OUT))
print('VERIFYDONE', flush=True)
