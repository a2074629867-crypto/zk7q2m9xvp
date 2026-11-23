# -*- coding: utf-8 -*-
"""极短句新旧对比试听页（A=旧版，B=新生成）。"""
import base64
import glob
import json
import os
import re
import subprocess
import tempfile

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
OUT = os.path.join(ROOT, "_audio_ch123", "out")
BAK = os.path.join(ROOT, "_bak_short_1122")
FF = "E:/tool/oopz/ffmpeg.exe"


def wc(s):
    return len(re.findall(r"[A-Za-z']+", s or ""))


def mp3_b64(p):
    fd, tmp = tempfile.mkstemp(suffix=".mp3", dir=os.path.join(ROOT, "_tmp_page"))
    os.close(fd)
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                    "-ar", "24000", "-ac", "1", "-b:a", "48k", tmp], check=True)
    b = open(tmp, "rb").read()
    os.remove(tmp)
    return base64.b64encode(b).decode()


def env_of(p, n=120):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    if len(y) < n:
        return [0.0] * n, len(y) / sr
    k = len(y) // n
    e = np.array([np.abs(y[i * k:(i + 1) * k]).max() for i in range(n)])
    m = e.max() or 1.0
    return [round(float(x / m), 3) for x in e], len(y) / sr


def rms(p):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    fr = y[idx]
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-12)
    v = fr[db > db.max() - 40]
    return float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)) if len(v) else -99


def main():
    os.makedirs(os.path.join(ROOT, "_tmp_page"), exist_ok=True)
    plan = [json.loads(l) for l in open(os.path.join(ROOT, "_dlg_plan_v2.jsonl"),
                                       encoding="utf-8")]
    short = [r for r in plan if wc(r["text"]) <= 3]

    rows = []
    for r in short:
        rid = r["id"]
        a = os.path.join(BAK, rid + ".wav")
        if not os.path.exists(a):
            a = os.path.join(OUT, rid + ".wav")
        b = None
        for d in ("_sweep/short2", "_sweep/short_final"):
            p = os.path.join(ROOT, d, rid + "__s42.wav")
            if os.path.exists(p):
                b = p
                break
        if not os.path.exists(a) or not b:
            continue
        ea, da = env_of(a)
        eb, db = env_of(b)
        rows.append({"id": rid, "who": r["who"], "emo": r["emo"], "text": r["text"],
                     "a": mp3_b64(a), "b": mp3_b64(b),
                     "da": round(da, 2), "db": round(db, 2),
                     "ra": round(rms(a), 1), "rb": round(rms(b), 1),
                     "ea": ea, "eb": eb})

    data = json.dumps(rows, ensure_ascii=False)
    html = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>极短句 新旧对比</title>
<style>
:root{--bg:#fbfaf7;--fg:#1b1b1b;--dim:#777;--line:#e3ded4;--a:#2f6bd8;--b:#c2410c;--card:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--dim:#999;--line:#2c2c2c;--a:#6fa0ff;--b:#ff8f5e;--card:#1c1c1c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:22px 16px 60px}
h1{font-size:18px;margin:0 0 4px}
.sub{color:var(--dim);font-size:13px;margin-bottom:16px}
.row{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:8px}
.hd{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:6px}
.id{font-weight:600}
.who{color:var(--dim);font-size:12px}
.txt{color:var(--dim);font-size:12px;margin-left:auto}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.side{border:1px solid var(--line);border-radius:8px;padding:6px 8px}
.side.on{border-color:var(--a);background:rgba(47,107,216,.06)}
.side.b.on{border-color:var(--b);background:rgba(194,65,12,.06)}
.btn{display:flex;gap:8px;align-items:center;margin-bottom:4px}
button{font:inherit;font-size:12px;padding:3px 10px;border-radius:6px;border:1px solid var(--line);background:transparent;color:var(--fg);cursor:pointer}
button:hover{border-color:var(--fg)}
canvas{width:100%;height:34px;display:block}
.meta{color:var(--dim);font-size:11px;margin-top:2px}
kbd{border:1px solid var(--line);border-radius:4px;padding:0 4px;font-size:11px}
</style>
<div class="wrap">
<h1>极短句：旧版 vs 新生成</h1>
<div class="sub">A = 现在库里（旧） / B = 载体短语重建。点按钮播放，<kbd>空格</kbd>暂停。共 <b id="n"></b> 条。<br>
判据：读音对不对、有没有吞字、语气是否自然、音量是否一致。</div>
<div id="list"></div>
</div>
<script>
const D = __DATA__;
const cv = document.createElement('canvas');
document.getElementById('n').textContent = D.length;
function draw(c, env, col){
  const g=c.getContext('2d'), W=c.width=c.clientWidth*2, H=c.height=68;
  g.clearRect(0,0,W,H); g.fillStyle=col; g.globalAlpha=.75;
  const n=env.length, bw=W/n;
  for(let i=0;i<n;i++){const h=Math.max(1,env[i]*H*0.44); g.fillRect(i*bw,H/2-h,Math.max(1,bw-0.6),h*2);}
}
let cur=null;
function play(src){
  if(cur){cur.pause(); cur=null;}
  cur=new Audio('data:audio/mpeg;base64,'+src); cur.play();
}
D.forEach(r=>{
  const el=document.createElement('div'); el.className='row';
  el.innerHTML=`<div class="hd"><span class="id">${r.id}</span><span class="who">${r.who}·${r.emo}</span><span class="txt">${r.text}</span></div>
  <div class="cols">
    <div class="side a"><div class="btn"><button data-s="a">A 旧版 ${r.da}s</button><span class="meta">${r.ra} dBFS</span></div><canvas></canvas></div>
    <div class="side b"><div class="btn"><button data-s="b">B 新版 ${r.db}s</button><span class="meta">${r.rb} dBFS</span></div><canvas></canvas></div>
  </div>`;
  const cs=el.querySelectorAll('canvas');
  draw(cs[0], r.ea, getComputedStyle(document.documentElement).getPropertyValue('--a').trim());
  draw(cs[1], r.eb, getComputedStyle(document.documentElement).getPropertyValue('--b').trim());
  el.querySelector('[data-s=a]').onclick=()=>{play(r.a); el.querySelectorAll('.side').forEach(s=>s.classList.remove('on')); el.querySelector('.side.a').classList.add('on');};
  el.querySelector('[data-s=b]').onclick=()=>{play(r.b); el.querySelectorAll('.side').forEach(s=>s.classList.remove('on')); el.querySelector('.side.b').classList.add('on');};
  document.getElementById('list').appendChild(el);
});
document.addEventListener('keydown',e=>{if(e.code==='Space'){e.preventDefault(); if(cur) cur.paused?cur.play():cur.pause();}});
</script></html>"""
    html = html.replace("__DATA__", data)
    out = os.path.join(ROOT, "_short_page.html")
    open(out, "w", encoding="utf-8").write(html)
    print("→ %s（%d 条，%.0f KB）" % (out, len(rows), os.path.getsize(out) / 1024))


if __name__ == "__main__":
    main()
