# -*- coding: utf-8 -*-
"""_build_dn_page.py —— 「除噪 vs 重生成」三版 A/B 试听页（单文件 HTML）

三条音轨，同一条台词：
  ① 现在用的成品（out/）
  ② 成品直接过 RNNoise（arnndn）
  ③ 参考先 demucs 净化、再重生成（_sweep/clean118/）

判据摆在每行上：底噪 dBFS（越低越干净）、w2v 覆盖率（掉=吃字）。
"""
import base64
import glob
import io
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")

FF = "E:/tool/oopz/ffmpeg.exe"
OUT_HTML = "G:/_setup/_dn_page.html"
MP3_DIR = "G:/_setup/_dn_page_mp3"


def frame_db(y, sr, hop=0.01, win=0.025):
    h, w = int(hop * sr), int(win * sr)
    n = 1 + (len(y) - w) // h
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    seg = y[idx]
    e = np.sqrt((seg ** 2).mean(1)) + 1e-12
    zero = np.abs(seg).max(1) == 0
    return 20 * np.log10(e), zero


def meas(p):
    y, sr = sf.read(p, dtype="float64", always_2d=True)
    y = y.mean(1)
    db, zero = frame_db(y, sr)
    nz = db[~zero]
    return (round(float(np.percentile(nz, 10)), 1) if len(nz) else -240.0), y, sr


def env_of(y, n=180):
    """归一化包络（0~1），页面画波形用"""
    if len(y) < n:
        return [0.0] * n
    k = len(y) // n
    e = np.array([np.abs(y[i * k:(i + 1) * k]).max() for i in range(n)])
    m = e.max() or 1.0
    return [round(float(x / m), 3) for x in e]


def mp3_b64(p):
    os.makedirs(MP3_DIR, exist_ok=True)
    tmp = os.path.join(MP3_DIR, os.path.splitext(os.path.basename(p))[0] + ".mp3")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                    "-codec:a", "libmp3lame", "-b:a", "128k", tmp],
                   check=True, capture_output=True)
    return base64.b64encode(open(tmp, "rb").read()).decode("ascii")


def main():
    sys.path.insert(0, "G:/_setup")
    import _calm_gate as CG
    plan = CG.load_plan()
    scan = json.load(open("G:/_setup/_dn_scan.json", encoding="utf-8"))
    clean = {os.path.basename(f).split("__")[0]: f
             for f in glob.glob("G:/_setup/_sweep/clean118/*.wav")}

    rows = []
    for rid, cf in sorted(clean.items()):
        if rid not in plan:
            continue
        src = f"G:/_setup/_audio_ch123/out/{rid}.wav"
        if not os.path.exists(src):
            continue
        dn = f"G:/_setup/_dn_dirty/{rid}_arnndn.wav"
        if not os.path.exists(dn):
            os.makedirs("G:/_setup/_dn_dirty", exist_ok=True)
            r = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error",
                                "-i", src, "-af", "arnndn=m=std.rnnn",
                                "-ar", "48000", dn],
                               cwd="G:/_setup", capture_output=True, text=True)
            if r.returncode != 0:
                continue
        f0, _, _ = meas(src)
        f1, _, _ = meas(dn)
        f2, _, _ = meas(cf)
        _, yy, _sr = meas(src)
        rows.append({"id": rid, "who": plan[rid]["who"], "emo": plan[rid]["emo"],
                     "env": env_of(yy),
                     "text": plan[rid]["text"], "f0": f0, "f1": f1, "f2": f2,
                     "b0": mp3_b64(src), "b1": mp3_b64(dn), "b2": mp3_b64(cf)})
        print("%-9s %-8s floor %6.1f %6.1f %6.1f" % (rid, plan[rid]["who"], f0, f1, f2), flush=True)

    rows.sort(key=lambda r: r["f0"], reverse=True)
    html = TPL.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
    io.open(OUT_HTML, "w", encoding="utf-8").write(html)
    print("\n%d 条 → %s" % (len(rows), OUT_HTML))


TPL = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>除噪 vs 净化重生成 · A/B</title>
<style>
:root{--bg:#f7f7f9;--fg:#1b1b1f;--sub:#6b6b76;--card:#fff;--line:#e3e3ea;
 --a:#8b8b96;--b:#c9762b;--c:#1f8a5f;--ok:#1f8a5f;--bad:#c0392b;--hl:#fff3e0}
[data-theme=dark]{--bg:#141418;--fg:#ececf2;--sub:#9a9aa8;--card:#1e1e24;--line:#2c2c36;
 --a:#8b8b96;--b:#e0954a;--c:#3fbb85;--hl:#2a2118}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
 font:15px/1.55 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:9;background:var(--bg);border-bottom:1px solid var(--line);
 padding:14px 18px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:650}
.tag{font-size:12px;padding:2px 8px;border-radius:99px;background:var(--line);color:var(--sub)}
button{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--card);
 color:var(--fg);border-radius:8px;padding:6px 12px}
button:hover{border-color:var(--sub)}
.row{background:var(--card);border:1px solid var(--line);border-radius:12px;
 margin:12px 18px;padding:12px 14px;display:grid;grid-template-columns:1fr 300px;gap:14px}
@media(max-width:760px){.row{grid-template-columns:1fr}}
.txt{font-size:14px;line-height:1.5;margin-bottom:8px}
.meta{font-size:12px;color:var(--sub);margin-bottom:8px}
.meta b{color:var(--fg);font-weight:600}
.btns{display:flex;gap:8px;flex-wrap:wrap}
.pb{display:flex;flex-direction:column;gap:2px;align-items:center;min-width:104px;
 padding:7px 10px;border-radius:9px;border:1px solid var(--line);background:transparent;cursor:pointer}
.pb .k{font-size:12px;font-weight:600}
.pb .f{font-size:11px;color:var(--sub);font-variant-numeric:tabular-nums}
.pb.on{border-width:2px}
.pb[data-v="0"].on{border-color:var(--a);background:color-mix(in srgb,var(--a) 12%,transparent)}
.pb[data-v="1"].on{border-color:var(--b);background:color-mix(in srgb,var(--b) 12%,transparent)}
.pb[data-v="2"].on{border-color:var(--c);background:color-mix(in srgb,var(--c) 12%,transparent)}
.pick{margin-left:auto;display:flex;gap:6px;align-items:center}
.pick button[data-p].sel{background:var(--ok);color:#fff;border-color:var(--ok)}
canvas{width:100%;height:54px;display:block}
.who{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;
 border:1px solid var(--line);color:var(--sub);margin-right:6px}
.lead{color:var(--bad);font-weight:600}
</style></head><body>
<header>
 <h1>除噪 vs 净化重生成</h1>
 <span class="tag" id="cnt"></span>
 <span class="tag">空格暂停 · 1/2/3 播放三版</span>
 <span style="flex:1"></span>
 <button onclick="tt()">深浅切换</button>
 <button onclick="exportPicks()">导出选择</button>
</header>
<div id="list"></div>
<script>
const D=__DATA__;
const L=['① 现用成品','② 成品过 RNNoise','③ 参考净化后重生成'];
const B=['b0','b1','b2'];
let cur=null,curKey=null;
const picks=JSON.parse(localStorage.getItem('dn_picks')||'{}');
document.getElementById('cnt').textContent=D.length+' 条';
if(localStorage.getItem('dn_theme')==='dark')document.documentElement.dataset.theme='dark';

function env(b64,n=200){
  const bin=atob(b64),u=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);
  return u; // 不解码音频，仅占位
}
const list=document.getElementById('list');
D.forEach((r,idx)=>{
  const el=document.createElement('div');el.className='row';
  const best=[r.f0,r.f1,r.f2];
  el.innerHTML=`
   <div>
     <div class="meta"><span class="who">${r.who} · ${r.emo}</span>
       <b>${r.id}</b> 底噪 ${r.f0} / ${r.f1} / ${r.f2} dBFS
       　重生成 ${r.f2-r.f0>0?'<span style="color:var(--bad)">'+(r.f2-r.f0).toFixed(1)+'</span>':'<span style="color:var(--ok)">'+(r.f2-r.f0).toFixed(1)+'</span>'} dB</div>
     <div class="txt">${r.text}</div>
     <div class="btns">
       ${L.map((s,i)=>`<button class="pb" data-v="${i}" data-i="${idx}">
          <span class="k">${s}</span><span class="f">${best[i]} dBFS</span></button>`).join('')}
       <span class="pick">${L.map((s,i)=>`<button data-p="${i}" data-i="${idx}">${['A','B','C'][i]}</button>`).join('')}</span>
     </div>
     <canvas data-i="${idx}" height="54"></canvas>
   </div>
   <div style="font-size:12px;color:var(--sub)">
     ① 现在发出去的版本<br>② 直接在成品上压噪（会削齿音、可能吃字）<br>③ 参考先 demucs 去掉配乐再重生成<br>
     <div style="margin-top:8px">按听感点 A / B / C 选出这条该用哪个</div>
   </div>`;
  list.appendChild(el);

  const cv=el.querySelector('canvas');
  drawWave(cv, r.env);

  el.querySelectorAll('.pb').forEach(btn=>{
    btn.onclick=()=>play(r.idx=r.id, +btn.dataset.v, el, btn);
  });
  el.querySelectorAll('.pick button').forEach(btn=>{
    if(picks[r.id]==+btn.dataset.p)btn.classList.add('sel');
    btn.onclick=()=>{
      el.querySelectorAll('.pick button').forEach(b=>b.classList.remove('sel'));
      btn.classList.add('sel');picks[r.id]=+btn.dataset.p;
      localStorage.setItem('dn_picks',JSON.stringify(picks));
    };
  });
});

function drawWave(cv,env){
  const g=cv.getContext('2d'),W=cv.width=cv.clientWidth*2,H=cv.height*2;
  g.clearRect(0,0,W,H);
  const col=getComputedStyle(document.documentElement).getPropertyValue('--a').trim();
  g.fillStyle=col;g.globalAlpha=.55;
  const n=env.length,bw=W/n;
  for(let i=0;i<n;i++){
    const h=Math.max(1,env[i]*H*0.45);
    g.fillRect(i*bw,H/2-h,Math.max(1,bw-0.6),h*2);
  }
  g.globalAlpha=1;
}

let au=null;
function play(id,v,el,btn){
  if(au){au.pause();au=null}
  el.querySelectorAll('.pb').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  const r=D.find(x=>x.id===id);
  au=new Audio('data:audio/mpeg;base64,'+r[B[v]]);
  au.play();
}

document.addEventListener('keydown',e=>{
  if(e.code==='Space'){e.preventDefault();if(au){au.paused?au.play():au.pause()}}
});
function tt(){const d=document.documentElement;
  d.dataset.theme=d.dataset.theme==='dark'?'':'dark';
  localStorage.setItem('dn_theme',d.dataset.theme==='dark'?'dark':'light');
  document.querySelectorAll('canvas').forEach((c,i)=>drawWave(c,D[i].env));}
function exportPicks(){
  const out=D.filter(r=>picks[r.id]!==undefined)
    .map(r=>`${r.id}\t${['A','B','C'][picks[r.id]]}\t${r.who}`);
  const blob=new Blob([out.join('\n')],{type:'text/plain'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='dn_picks.txt';a.click();
}
</script></body></html>"""

if __name__ == "__main__":
    main()
