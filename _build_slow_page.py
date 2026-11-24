# -*- coding: utf-8 -*-
"""语速试听页：同一句的 原速 / 0.88 / 0.80 三版并排。

    python _build_slow_page.py     → _slow_page.html（127.0.0.1:8096）
"""
import base64
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_sweep", "slow_page")
OUT = os.path.join(HERE, "_slow_page.html")

TAGS = [("a", "原速"), ("b", "×0.88"), ("c", "×0.80")]

TPL = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>语速 A/B/C — 原速 / 0.88 / 0.80</title>
<style>
:root{--bg:#f6f7f9;--fg:#15181d;--mut:#6b7280;--card:#fff;--line:#e3e6ea;--acc:#c0392b;--sel:#1f6feb}
@media(prefers-color-scheme:dark){:root{--bg:#0f1216;--fg:#e6e9ef;--mut:#98a2b3;--card:#161a20;--line:#252b33;--acc:#ff6b5a;--sel:#4c8dff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 18px;z-index:5}
h1{font-size:15px;margin:0 0 4px}
.hint{color:var(--mut);font-size:12px}
main{padding:14px 18px 60px;max-width:980px;margin:0 auto}
.row{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:10px}
.top{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px}
.id{font-weight:600;font-variant-numeric:tabular-nums}
.who{color:var(--mut);font-size:12px}
.txt{color:var(--mut);font-size:12px;margin-bottom:10px}
.btns{display:flex;gap:8px;flex-wrap:wrap}
button{background:transparent;border:1px solid var(--line);color:var(--fg);border-radius:8px;padding:7px 12px;
  cursor:pointer;font:inherit;font-variant-numeric:tabular-nums}
button:hover{border-color:var(--acc)}
button.on{border-color:var(--sel);box-shadow:0 0 0 2px color-mix(in srgb,var(--sel) 25%,transparent)}
button b{font-weight:600}
button span{color:var(--mut);font-size:11px;margin-left:6px}
footer{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);
  padding:10px 18px;display:flex;gap:12px;align-items:center;font-size:12px}
#cnt{color:var(--mut)}
#exp{border-color:var(--acc)}
</style></head><body>
<header>
  <h1>语速 A/B/C —— 同一句：原速 / ×0.88 / ×0.80</h1>
  <div class="hint">点按钮播放；按 <b>1/2/3</b> 记选择；<b>空格</b> 暂停。<span style="color:var(--acc)">wpm 是「含停顿」口径</span>，正常对白 152~190。</div>
</header>
<main id="rows"></main>
<footer><span id="cnt">已选 0 / __N__</span><button id="exp">导出选择</button></footer>
<script>
const D = __DATA__;
const ORDER = ['a','b','c'];
const pick = {};
const rows = document.getElementById('rows');
let playing = null;
D.forEach((r,i)=>{
  const el = document.createElement('div'); el.className='row';
  const btns = ORDER.map((k,idx)=>{
    const v = r.vers[k];
    return `<button data-i="${i}" data-k="${k}"><b>${'ABC'[idx]}</b> ${v.rate===1?'原速':'×'+v.rate} <span>${v.wpm} wpm · ${v.dur}s</span></button>`;
  }).join('');
  el.innerHTML = `<div class="top"><span class="id">${r.id}</span><span class="who">${r.who} · ${r.emo}</span></div>
    <div class="txt">${r.text}</div><div class="btns">${btns}</div>`;
  rows.appendChild(el);
});
rows.addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b) return;
  const i=b.dataset.i,k=b.dataset.k;
  document.querySelectorAll(`button[data-i="${i}"]`).forEach(x=>x.classList.toggle('on',x===b));
  pick[i]=k; upd();
  play(D[i].vers[k].src);
});
document.querySelectorAll('button[data-i]').forEach(b=>{
  b.addEventListener('dblclick',e=>{e.preventDefault();});
});
function play(b64){
  if(playing){playing.pause();}
  playing = new Audio('data:audio/wav;base64,'+b64);
  playing.play();
}
document.addEventListener('keydown',e=>{
  if(e.code==='Space'){e.preventDefault(); if(playing){playing.paused?playing.play():playing.pause();}}
});
function upd(){
  const n=Object.keys(pick).length;
  document.getElementById('cnt').textContent=`已选 ${n} / ${D.length}`;
}
document.getElementById('exp').onclick=()=>{
  const out = Object.entries(pick).map(([i,k])=>({id:D[i].id,选择:'ABC'[ORDER.indexOf(k)],rate:D[i].vers[k].rate,wpm:D[i].vers[k].wpm}));
  const s = JSON.stringify(out,null,1);
  navigator.clipboard?.writeText(s);
  alert(s);
};
</script></body></html>"""


def b64(p):
    return base64.b64encode(open(p, "rb").read()).decode()


def main():
    meta = json.load(open(os.path.join(SRC, "meta.json"), encoding="utf-8"))
    data = []
    for rid, r in meta.items():
        vers = {}
        for tag, _label in TAGS:
            p = os.path.join(SRC, "%s_%s.wav" % (rid, tag))
            if not os.path.exists(p):
                continue
            vers[tag] = dict(r["vers"][tag], src=b64(p))
        data.append({"id": rid, "who": r["who"], "emo": r["emo"],
                     "text": r["text"].replace("‘", "「").replace("’", "」"),
                     "vers": vers})
    html = TPL.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__N__", str(len(data)))
    open(OUT, "w", encoding="utf-8").write(html)
    print("%s  %.1f MB  %d 条 × %d 版" % (OUT, os.path.getsize(OUT) / 1048576, len(data), len(TAGS)))


if __name__ == "__main__":
    main()
