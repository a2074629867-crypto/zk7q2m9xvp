# -*- coding: utf-8 -*-
"""build_denoise_page.py —— 训练音频降噪对比试听页（离线单文件）"""
import base64, os, subprocess, tempfile, json
import numpy as np, soundfile as sf
from scipy.signal import welch

FFMPEG = 'E:/tool/oopz/ffmpeg.exe'
SR = 32000
OUT_HTML = 'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_voice_lab/listen_denoise.html'

SRC = 'G:/GPT-SoVITS/_dataset/wonder_train.wav'
V1  = 'G:/_setup/_denoise_full/wonder_train_df3.wav'
V2  = 'G:/_setup/_denoise_full/wonder_train_df3_notch.wav'

# 两段：语音段（听音质有无损伤） / 嗡鸣段（听噪声是否清掉）
CLIPS = [('voi', '语音段 0:00-0:20', 0.0, 20.0),
         ('hum', '嗡鸣段 20:00-20:20', 1200.0, 1220.0)]

VERSIONS = [('src', '① 原始录音（未处理）', SRC),
            ('df3', '② DF3 降噪（宽带噪声）', V1),
            ('ntc', '③ DF3 + notch（低频嗡鸣也削）', V2)]


def rd_seg(p, a, b):
    with sf.SoundFile(p) as f:
        f.seek(int(a * SR))
        x = f.read(int((b - a) * SR), dtype='float64', always_2d=True).mean(1)
    return x


def db(v):
    return 10 * np.log10(max(v, 1e-30))


def bandE(x, lo, hi):
    f, P = welch(x, fs=SR, nperseg=4096)
    m = (f >= lo) & (f < hi)
    return db(P[m].mean())


def mp3_b64(x):
    tmp_w = tempfile.mktemp(suffix='.wav')
    tmp_m = tempfile.mktemp(suffix='.mp3')
    sf.write(tmp_w, x.astype('float64'), SR, subtype='PCM_16')
    subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', tmp_w,
                    '-codec:a', 'libmp3lame', '-b:a', '128k', tmp_m], check=True)
    data = open(tmp_m, 'rb').read()
    os.remove(tmp_w); os.remove(tmp_m)
    return base64.b64encode(data).decode('ascii')


def analyze(p):
    x, _ = sf.read(p, dtype='float64', always_2d=True); x = x.mean(1)
    sil = x[int(9.61 * SR):int(12.58 * SR)]
    voi = x[int(0.8 * SR):int(2.0 * SR)]
    hum = x[int(1200 * SR):int(1210 * SR)]
    return {
        'sil_lf': round(bandE(sil, 60, 100), 1),
        'sil_mid': round(bandE(sil, 300, 2000), 1),
        'hum_lf': round(bandE(hum, 60, 100), 1),
        'voi_lf': round(bandE(voi, 60, 100), 1),
        'voi_mid': round(bandE(voi, 300, 2000), 1),
        'voi_hi': round(bandE(voi, 4000, 10000), 1),
        'rms': round(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12), 1),
    }


AN = {k: analyze(p) for k, _, p in VERSIONS}

cards = []
for ck, cname, a, b in CLIPS:
    inner = []
    for vk, vname, vp in VERSIONS:
        x = rd_seg(vp, a, b)
        b64 = mp3_b64(x)
        m = AN[vk]
        if ck == 'hum':
            meta = '嗡鸣段 60-100Hz <b>%.1f dB</b>' % m['hum_lf']
        else:
            meta = ('语音 60-100Hz %.1f · 300-2kHz %.1f · 4-10kHz %.1f dB'
                    % (m['voi_lf'], m['voi_mid'], m['voi_hi']))
        inner.append('<div class="card %s"><div class="tt"><span class="nm">%s</span></div>'
                     '<div class="meta">%s</div>'
                     '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
                     % ({'src': 'c-src', 'df3': 'c-v1', 'ntc': 'c-v2'}[vk], vname, meta, b64))
    cards.append('<div class="grp">%s</div>%s' % (cname, ''.join(inner)))

rows = []
for vk, vname, vp in VERSIONS:
    m = AN[vk]
    rows.append('<tr><td>%s</td><td class="num">%.1f</td><td class="num">%.1f</td>'
                '<td class="num">%.1f</td><td class="num">%.1f</td><td class="num">%.1f</td>'
                '<td class="num">%.1f</td><td class="num">%.1f</td></tr>'
                % (vname, m['sil_lf'], m['sil_mid'], m['hum_lf'], m['voi_lf'], m['voi_mid'],
                   m['voi_hi'], m['rms']))

HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>训练音频降噪对比</title>
<style>
:root{--bg:#12141a;--card:#1b1e26;--fg:#e8eaf0;--dim:#9aa3b2;--ac:#5cc8ff;--good:#39d98a;--warn:#ffb454}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;padding:20px 16px 60px}
.wrap{max-width:980px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:16px;line-height:1.8}
.box{background:var(--card);border:1px solid #2b3140;border-radius:10px;padding:12px 15px;margin:0 0 18px;font-size:12.5px;line-height:1.85}
.box b{color:var(--fg)} .box .k{color:var(--warn);font-family:ui-monospace,Menlo,Consolas,monospace}
.grp{margin:24px 0 10px;font-size:16px;font-weight:600;border-left:3px solid var(--ac);padding-left:10px}
.card{background:var(--card);border-radius:12px;padding:12px 15px;margin:8px 0;border:1px solid #262a35}
.card.c-src{border-color:#5a3a3a} .card.c-v1{border-color:#3a5a44} .card.c-v2{border-color:#3a4a63}
.tt{display:flex;align-items:baseline;gap:9px;margin-bottom:4px} .nm{font-weight:600}
.meta{font-size:12px;color:var(--dim);font-family:ui-monospace,Menlo,Consolas,monospace;margin:3px 0 6px}
.meta b{color:var(--good)}
audio{width:100%;height:34px;margin-top:3px}
table{width:100%;border-collapse:collapse;margin:16px 0;font-size:11.5px}
th,td{padding:5px 4px;border-bottom:1px solid #262a35;text-align:left}
th{color:var(--dim);font-weight:500;font-size:11px}
td.num{font-family:ui-monospace,Menlo,Consolas,monospace;text-align:right}
.hint{color:var(--dim);font-size:12.5px;margin-top:20px;line-height:1.85}
.hint b{color:var(--fg)}
code{background:#22262f;padding:1px 5px;border-radius:4px;font-size:12px}
</style></head><body><div class="wrap">
<h1>训练音频降噪 · 三版本对比</h1>
<div class="sub">源：<code>wonder_train.wav</code>（26.92 min @32kHz）—— 马修读 Calm《Wonder》</div>
<div class="box">
<b>先说一个关键发现：这段录音里没有背景音乐。</b>Demucs 分离出的"伴奏轨"在 2k–10kHz 只有 −102~−109 dB（近乎空白），
20–60Hz 也只有 −72~−84 dB。所以不存在"去背景音乐"这一步。<br><br>
<b>真正的噪声有两层：</b><br>
① <b>宽带底噪</b> —— 静音段 −79 dB（含高频嘶声）。用 <b>DeepFilterNet3</b> 处理，降到 <span class="k">−104.7 dB</span>（−25.7 dB）。<br>
② <b>低频嗡鸣</b> —— 基频 <span class="k">68.36 Hz</span> 与 <span class="k">76.17 Hz</span>（含完整泛音列，差 7.81Hz 产生 3.9Hz 拍频），
是机械/通风嗡鸣的指纹，静音段 −52.8 dB。<b>DF3 对它完全无效</b>（它是为语音频段设计的），需另加 notch。<br><br>
⚠️ <b>但 notch 有代价</b>：68/76Hz 与男声基频重叠，削嗡鸣必然削一点人声低音（实测语音 60–100Hz 损 3~6 dB）。
所以③是"更干净但低音略薄"，①是"更原味但带嗡鸣"。<b>请你听感裁决。</b>
</div>
@@CARDS@@
<h3 style="font-size:14px;margin:22px 0 6px">量化对照（dB）</h3>
<table>
<tr><th>版本</th><th>静音60-100</th><th>静音300-2k</th><th>嗡鸣60-100</th><th>语音60-100</th><th>语音300-2k</th><th>语音4-10k</th><th>全段RMS</th></tr>
@@ROWS@@
</table>
<div class="hint">
<b>请这样听：</b><br>
1. <b>语音段</b>：切 ②③ 与 ①，听人声<b>有没有变薄、变闷、发金属声</b>。③ 的男声低音会略薄一点，这是 notch 的代价。<br>
2. <b>嗡鸣段</b>：这一段基本是静音，① 里能听到持续的低频"嗡嗡"，② 里嗡鸣还在，③ 里应该明显干净。<br><br>
<b>要你回答一句</b>：训练数据用 <b>②</b>（保守，只除宽带噪声）还是 <b>③</b>（彻底，连嗡鸣一起除）？<br>
选完我就用它重切切片（时间轴与原始严格一致，<b>已做好的 465 条标注可以 100% 复用</b>），然后开始训练。
</div></div></body></html>"""

HTML = HTML.replace('@@CARDS@@', ''.join(cards)).replace('@@ROWS@@', ''.join(rows))
open(OUT_HTML, 'w', encoding='utf-8').write(HTML)
print('WROTE %s  (%.2f MB)' % (OUT_HTML, os.path.getsize(OUT_HTML) / 1048576))
print(json.dumps(AN, ensure_ascii=False, indent=1))
