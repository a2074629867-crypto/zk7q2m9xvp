# -*- coding: utf-8 -*-
"""build_v5ft_page.py —— GSV v5turbo 微调克隆验证试听页（离线单文件，MP3 内嵌）。

读取 E:/tts-models/acpp/out/v5ft/*.wav（由 gsv5_ft_infer.py 产出）：
  base_1.wav / base_0p88.wav   零样本（底模 s2Gv5turbo + s1v3）
  ft_1.wav   / ft_0p88.wav     微调（LoRA e8 + GPT e15）
再跑一次声纹（anchor = 真人 real_trim 同段 29.41s），生成可离线打开的对比页。

用法：G:/Python310/python.exe build_v5ft_page.py
"""
import os, re, sys, json, base64, subprocess, html, time

FFMPEG = 'E:/tool/oopz/ffmpeg.exe'
OUT = 'E:/tts-models/acpp/out/v5ft'
PAGE = 'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_voice_lab/listen_v5ft.html'
ANCHOR = 'G:/_setup/dots_test/_an_real_trim.wav'
SPKPY = 'C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe'
SPK = 'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/spk_embed.py'
REFS = 'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
TXT = 'G:/_setup/scene_calmdeep.txt'

ITEMS = [
    ('base_1',    '零样本 · 1.00x', '底模 s2Gv5turbo + s1v3（未微调）', 'base'),
    ('base_0p88', '零样本 · 0.88x', '底模 s2Gv5turbo + s1v3（未微调）', 'base'),
    ('ft_1',      '微调 · 1.00x',   'LoRA e8 + GPT e15',               'ft'),
    ('ft_0p88',   '微调 · 0.88x',   'LoRA e8 + GPT e15',               'ft'),
]


def dur(p):
    try:
        import soundfile as sf
        return sf.info(p).duration
    except Exception:
        return 0.0


def to_mp3(wav, mp3):
    subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error',
                    '-i', wav, '-ac', '1', '-ar', '32000',
                    '-codec:a', 'libmp3lame', '-b:a', '96k', mp3], check=True)


def b64(p):
    return base64.b64encode(open(p, 'rb').read()).decode()


def spk_scores(files):
    """跑 spk_embed.py，解析 '文件名  相似度  判定'。返回 {basename: score}"""
    if not os.path.exists(SPKPY) or not files:
        return {}
    cmd = [SPKPY, SPK, ANCHOR] + files
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        out = (r.stdout or '') + (r.stderr or '')
    except Exception as e:
        print('  声纹调用失败: %s' % e)
        return {}
    sc = {}
    for ln in out.splitlines():
        m = re.match(r'^\s*(\S+\.wav)\s+([0-9]*\.?[0-9]+)\s', ln)
        if m:
            sc[m.group(1)] = float(m.group(2))
    return sc


def main():
    print('=== 构建 v5ft 试听页 ===')
    # 1) 收集存在的 wav
    rows = []
    for tag, title, sub, grp in ITEMS:
        w = os.path.join(OUT, tag + '.wav')
        if not os.path.exists(w):
            print('  缺: %s' % w)
            continue
        rows.append(dict(tag=tag, title=title, sub=sub, grp=grp, wav=w,
                         dur=dur(w), size=os.path.getsize(w)))
    if not rows:
        print('[错误] 没有任何 wav，跳过（训练可能未完成）')
        return 1

    # 2) 声纹
    print('>>> 声纹对比（anchor = 真人 real_trim）...')
    scores = spk_scores([r['wav'] for r in rows])
    for r in rows:
        r['spk'] = scores.get(os.path.basename(r['wav']))
    for r in rows:
        print('   %-12s %8s  %.2fs' % (r['tag'], ('%.4f' % r['spk']) if r['spk'] else '-', r['dur']))

    # 3) 转 mp3 + base64
    print('>>> 转 MP3 并内嵌 ...')
    for r in rows:
        mp3 = os.path.join(OUT, r['tag'] + '.mp3')
        to_mp3(r['wav'], mp3)
        r['b64'] = b64(mp3)
        r['mp3kb'] = os.path.getsize(mp3) // 1024

    # 真人对照
    anc_b64, anc_dur, anc_spk = '', 0.0, None
    if os.path.exists(ANCHOR):
        mp3 = os.path.join(OUT, '_anchor.mp3')
        to_mp3(ANCHOR, mp3)
        anc_b64 = b64(mp3)
        anc_dur = dur(ANCHOR)
    # 参考音频（8.3s）
    ref_b64, ref_dur = '', 0.0
    if os.path.exists(REFS):
        mp3 = os.path.join(OUT, '_ref.mp3')
        to_mp3(REFS, mp3)
        ref_b64 = b64(mp3)
        ref_dur = dur(REFS)

    text = open(TXT, encoding='utf-8').read().strip() if os.path.exists(TXT) else ''
    nwords = len(text.split())

    # 4) 写页面
    def card(r):
        spk = ('%.4f' % r['spk']) if r['spk'] else '—'
        return '''
    <div class="card %s">
      <div class="hd"><span class="tag">%s</span><span class="spk">声纹 %s</span></div>
      <div class="sub">%s</div>
      <div class="meta">时长 %.2fs · MP3 %dKB</div>
      <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>
    </div>''' % (r['grp'], html.escape(r['title']), spk, html.escape(r['sub']),
                 r['dur'], r['mp3kb'], r['b64'])

    cards = ''.join(card(r) for r in rows)

    anc_html = ''
    if anc_b64:
        anc_html = '''
  <h2>真人对照（声纹基准）</h2>
  <div class="card anchor">
    <div class="hd"><span class="tag">真人原声</span><span class="spk">基准 1.0000</span></div>
    <div class="sub">real_trim.wav · Calm《Wonder》同段 29.41s</div>
    <div class="meta">时长 %.2fs</div>
    <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>
  </div>''' % (anc_dur, anc_b64)

    ref_html = ''
    if ref_b64:
        ref_html = '''
  <h2>推理参考音频（8.3s）</h2>
  <div class="card ref">
    <div class="hd"><span class="tag">voice ref</span></div>
    <div class="sub">wonder_train.wav_0018112640_0018378240.wav</div>
    <div class="meta">时长 %.2fs</div>
    <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>
  </div>''' % (ref_dur, ref_b64)

    # 汇总对比
    b1 = next((r for r in rows if r['tag'] == 'base_1'), None)
    f1 = next((r for r in rows if r['tag'] == 'ft_1'), None)
    delta = ''
    if b1 and f1 and b1['spk'] and f1['spk']:
        d = f1['spk'] - b1['spk']
        delta = ('微调相对零样本 <b class="%s">%+.4f</b>（%.4f → %.4f）'
                 % ('up' if d >= 0 else 'down', d, b1['spk'], f1['spk']))

    ts = time.strftime('%Y-%m-%d %H:%M')
    page = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GSV v5turbo 微调克隆验证</title>
<style>
  :root{--bg:#f6f7f9;--fg:#1c2028;--sub:#5a6270;--card:#fff;--bd:#e3e6ec;
        --ft:#e8f4ea;--ftb:#7fc48c;--bs:#eef2f8;--bsb:#9fb4d0;--up:#0a8a3c;--down:#c22;}
  @media (prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e8eaee;--sub:#9aa3b2;
        --card:#1c2027;--bd:#2b3039;--ft:#1d2a20;--ftb:#3f7a4c;--bs:#1b2028;--bsb:#3a4658;
        --up:#4ecb7a;--down:#ff7b7b;}}
  *{box-sizing:border-box}
  body{margin:0;padding:28px 18px 60px;background:var(--bg);color:var(--fg);
       font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;}
  .wrap{max-width:760px;margin:0 auto}
  h1{font-size:21px;margin:0 0 6px}
  h2{font-size:15px;margin:30px 0 10px;color:var(--sub);font-weight:600}
  .lead{color:var(--sub);font-size:13px;margin-bottom:18px}
  .box{background:var(--card);border:1px solid var(--bd);border-radius:10px;
       padding:14px 16px;margin-bottom:18px;font-size:13px;color:var(--sub);line-height:1.75}
  .box b{color:var(--fg)}
  .card{background:var(--card);border:1px solid var(--bd);border-left:4px solid var(--bd);
        border-radius:10px;padding:13px 15px;margin-bottom:12px}
  .card.ft{border-left-color:var(--ftb);background:var(--ft)}
  .card.base{border-left-color:var(--bsb);background:var(--bs)}
  .card.anchor{border-left-color:#c9a227}
  .card.ref{border-left-color:#8a7fd0}
  .hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
  .tag{font-weight:700;font-size:15px}
  .spk{font-variant-numeric:tabular-nums;font-size:13px;color:var(--sub)}
  .sub{color:var(--sub);font-size:12.5px;margin:3px 0 6px}
  .meta{color:var(--sub);font-size:12px;margin-bottom:8px;opacity:.85}
  audio{width:100%%;height:36px}
  .up{color:var(--up)}.down{color:var(--down)}
  code{background:rgba(127,127,127,.14);padding:1px 5px;border-radius:4px;font-size:12px}
</style>
</head>
<body><div class="wrap">
<h1>GSV v5turbo 微调克隆验证</h1>
<div class="lead">同一文本 · 同一参考音频（8.3s）· 同一 seed(42) —— 唯一变量是「是否加载微调权重」</div>

<div class="box">
<b>对比设计</b><br>
文本：<code>scene_calmdeep.txt</code>（%d 词）&nbsp;·&nbsp; 参考：<code>wonder_train.wav_0018112640_0018378240.wav</code>（8.3s）<br>
<b>零样本</b> = 官方底模 <code>s2Gv5turbo.pth</code> + <code>s1v3.ckpt</code>（未训练）<br>
<b>微调</b> = 我们的 LoRA（<code>net_g.cfm</code> r32, 8 epoch）+ GPT（<code>e15.ckpt</code>，15 epoch）<br>
声纹锚点 = 真人同段 <code>real_trim.wav</code>（29.41s）%s<br>
<span style="font-size:12px;opacity:.85">※ 声纹是<b>锚点函数</b>，跨锚点不可比；本页全部用同一个真人锚点，故内部可比。</span>
</div>

<h2>对比试听</h2>
%s
%s
%s

<div class="lead" style="margin-top:26px">生成时间 %s</div>
</div></body></html>''' % (nwords, ('　·　' + delta) if delta else '', cards, anc_html, ref_html, ts)

    os.makedirs(os.path.dirname(PAGE), exist_ok=True)
    open(PAGE, 'w', encoding='utf-8').write(page)
    print('\n[ok] 写出 %s  (%.1f MB)' % (PAGE, os.path.getsize(PAGE) / 1e6))
    json.dump({'items': [{k: v for k, v in r.items() if k != 'b64'} for r in rows],
               'anchor': {'dur': anc_dur, 'spk': anc_spk},
               'page': PAGE},
              open(os.path.join(OUT, 'summary.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('[ok] 写出 %s/summary.json' % OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
