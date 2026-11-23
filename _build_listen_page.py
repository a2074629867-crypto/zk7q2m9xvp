# -*- coding: utf-8 -*-
"""对白返工试听页（A/B/C 对比）。

设计目标：耳朵要能立刻分辨「哪一版更好」，所以每行同时给三样东西
  1) 三个可单独播放的 take（A=被否的旧版、B=现用、C=新版）
  2) 从波形算出来的包络条 —— 停顿在哪、密度如何，一眼看见，不靠猜
  3) 实测指标：时长 / 吐字语速 wpm_voiced / voiced-tilt / F0

用法：
  G:/Python310/python.exe -u _build_listen_page.py --ids c2_0246,c2_0279 ... --out _listen_page.html
音频用相对路径引用（页面放在 G:/_setup 下，靠本地 http server 打开）。
"""
import argparse
import io
import json
import os
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")

ROOT = "G:/_setup"
LIVE = "_audio_ch123/out_paused"
OLD = "_audio_ch123/out_bak_prepause"
NEW = "_sweep/cand53/pick"
NEW2 = "_sweep/cand54/pick"
REF = "castle_fr_ref/1_charles_normal.wav"
REF_LABEL = "13.58s · 你切的那 8 段拼起来"
# 2026-11-21 用 castle_srt_cues.json 逐句核对过（此前是用 ASR 猜的，错 3 处）：
#   ASR: "Moi aussi, je suis né comme ça"      SRT i=25: "Je suis né comme ça aussi?"
#   ASR: "Vous êtes Monsieur Breaud ?"          SRT i=33: "Vous êtes M. Bréaud?"
#   ASR: "Et si elle ne vous aime pas ?"        SRT i=357: "Et si elle, elle vous aime pas?"
REF_TEXT = ("Je suis né comme ça aussi? Vous êtes Monsieur Bréaud? "
            "Moi, je suis Charles Vernet. Non. Ça va mieux, maintenant. Non, monsieur. "
            "Et si elle, elle vous aime pas? Laisse. C'est moi qui t'invite. Je suis encore très riche.")


def rel(p):
    p = p.replace("\\", "/")
    if p.startswith(ROOT + "/"):
        return p[len(ROOT) + 1:]
    return p


def envelope(path, npts=240):
    """峰值包络，0~1。用于画「停顿在哪」的条纹。"""
    try:
        y, sr = sf.read(path, dtype="float32")
    except Exception:
        return []
    if y.ndim > 1:
        y = y.mean(1)
    if not len(y):
        return []
    win = max(1, len(y) // npts)
    out = []
    for i in range(npts):
        seg = y[i * win:(i + 1) * win]
        if not len(seg):
            out.append(0.0)
            continue
        out.append(float(np.abs(seg).max()))
    mx = max(out) or 1.0
    return [round(v / mx, 3) for v in out]


def _asr_of(asrlib, psum, i):
    """ASR json 的键混用 / 和 \\，比之前统一归一。"""
    tag = (psum.get(i) or {}).get("tag")
    if not tag or not asrlib:
        return ""
    idx = {k.replace("\\", "/").lower(): v for k, v in asrlib.items()}
    for d in ("cand54", "cand53"):
        p = os.path.join(ROOT, "_sweep", d, tag + ".wav").replace("\\", "/").lower()
        t = (idx.get(p) or {}).get("text")
        if t:
            return t
    return ""


def measure(path, text):
    """复用 calm_gate 的量测口径，失败就返回空指标。"""
    try:
        import _calm_gate as CG
        nw = CG.spoken_words(text) or 1
        m = CG.measure(path, nw, text)
        return {"dur": round(m["dur"], 2), "wpm": int(m["wpm_voiced"]),
                "tilt": round(m["tilt"], 3), "f0": int(m["F0"]),
                "gaps": [round(g, 2) for g in (m.get("gaps") or [])][:4]}
    except Exception as e:
        try:
            info = sf.info(path)
            return {"dur": round(info.duration, 2), "wpm": None,
                    "tilt": None, "f0": None, "gaps": [], "err": str(e)[:60]}
        except Exception:
            return {"dur": None, "wpm": None, "tilt": None, "f0": None, "gaps": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--live", default=LIVE)
    ap.add_argument("--old", default=OLD)
    ap.add_argument("--new", default=NEW, help="C 列：5s 短参考版")
    ap.add_argument("--new2", default=NEW2, help="D 列：13.58s 长参考版")
    ap.add_argument("--out", default=os.path.join(ROOT, "_listen_page.html"))
    ap.add_argument("--asr", default="", help="可选：{id: text} 覆盖")
    ap.add_argument("--asr-json", default="_words_cand53.json", help="候选 ASR（按选中的 tag 回查）")
    ap.add_argument("--align", default="", help="wav2vec2 声学复检结果 json")
    ap.add_argument("--picksum", default="_pick53_summary.json", help="C 列选片摘要")
    ap.add_argument("--picksum2", default="_pick54_summary.json", help="D 列选片摘要")
    ap.add_argument("--asr-json2", default="_words_cand54.json", help="D 列候选 ASR")
    ap.add_argument("--title", default="对白返工试听 · 10 条")
    ap.add_argument("--note", default="")
    ap.add_argument("--labels", default="", help="逗号分隔，覆盖 A,B,C,D 的列名")
    ap.add_argument("--subs", default="", help="逗号分隔，覆盖四列的副标题")
    ap.add_argument("--no-cd", action="store_true", help="只出 A/B 两列（停顿对比用）")
    a = ap.parse_args()

    import _calm_gate as CG
    plan = CG.load_plan()
    asr = {}
    if a.asr and os.path.exists(a.asr):
        asr = json.load(io.open(a.asr, encoding="utf-8"))

    alignd = {}
    if a.align:
        apj = a.align if os.path.isabs(a.align) else os.path.join(ROOT, a.align)
        if os.path.exists(apj):
            for r in json.load(io.open(apj, encoding="utf-8")):
                alignd[r["id"]] = {"cov": r.get("w2v_cov"), "text": r.get("w2v_text") or "",
                                   "issues": r.get("issues") or []}

    sump = a.picksum if os.path.isabs(a.picksum) else os.path.join(ROOT, a.picksum)
    psum = json.load(io.open(sump, encoding="utf-8")) if os.path.exists(sump) else {}
    sump2 = a.picksum2 if os.path.isabs(a.picksum2) else os.path.join(ROOT, a.picksum2)
    psum2 = json.load(io.open(sump2, encoding="utf-8")) if os.path.exists(sump2) else {}
    asrlib2 = {}
    ap2 = a.asr_json2 if os.path.isabs(a.asr_json2) else os.path.join(ROOT, a.asr_json2)
    if os.path.exists(ap2):
        asrlib2 = json.load(io.open(ap2, encoding="utf-8"))

    asrlib = {}
    ap_ = a.asr_json if os.path.isabs(a.asr_json) else os.path.join(ROOT, a.asr_json)
    if os.path.exists(ap_):
        asrlib = json.load(io.open(ap_, encoding="utf-8"))

    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    rows = []
    for i in ids:
        text = (plan.get(i) or {}).get("text") or ""
        takes = []
        cand = [
            ("A", "上一版", "同参考更早一次生成", os.path.join(a.old, "%s.wav" % i)),
            ("B", "现用（nervous_2）", "换参考前的版本", os.path.join(a.live, "%s.wav" % i)),
            ("C", "5s 参考（c185 单句）", "上一轮生成", os.path.join(a.new, "%s.wav" % i)),
            ("D", "13.58s 参考（你切的 8 段）", "本轮生成", os.path.join(a.new2, "%s.wav" % i)),
        ]
        if a.no_cd:
            cand = cand[:2]
        if a.labels:
            lb = [x.strip() for x in a.labels.split(",")]
            cand = [(c[0], lb[k] if k < len(lb) else c[1], c[2], c[3])
                    for k, c in enumerate(cand)]
        if a.subs:
            sb = [x.strip() for x in a.subs.split(",")]
            cand = [(c[0], c[1], sb[k] if k < len(sb) else c[2], c[3])
                    for k, c in enumerate(cand)]
        for key, label, sub, path in cand:
            if not os.path.exists(path):
                takes.append({"key": key, "label": label, "sub": sub, "missing": True})
                continue
            t = {"key": key, "label": label, "sub": sub + " · " + rel(path).split("/")[-2] + "/",
                 "src": rel(path)}
            t.update(measure(path, text))
            t["env"] = envelope(path)
            takes.append(t)
        rows.append({
            "id": i,
            "who": (plan.get(i) or {}).get("who") or "",
            "emo": (plan.get(i) or {}).get("emo") or "",
            "text": text,
            "asr": asr.get(i) or _asr_of(asrlib2, psum2, i) or _asr_of(asrlib, psum, i),
            "asr_src": "D" if _asr_of(asrlib2, psum2, i) else ("C" if _asr_of(asrlib, psum, i) else ""),
            "cflag": (psum.get(i) or {}).get("flag") or "",
            "cnote": ";".join(((psum.get(i) or {}).get("reject") or []) +
                              ((psum.get(i) or {}).get("reasons") or [])),
            "calts": (psum.get(i) or {}).get("alt") or [],
            "w2v": alignd.get(i),
            "takes": takes,
        })
        print("%-9s %s" % (i, " ".join(
            "%s%s" % (t["key"], "✓" if not t.get("missing") else "-") for t in takes)))

    data = {"title": a.title, "note": a.note,
            "generated": time.strftime("%Y-%m-%d %H:%M"), "rows": rows}

    refp = os.path.join(ROOT, REF)
    if os.path.exists(refp):
        try:
            rdur = round(sf.info(refp).duration, 2)
        except Exception:
            rdur = None
        data["ref"] = {"src": REF, "text": REF_TEXT, "dur": rdur, "label": REF_LABEL,
                       "env": envelope(refp, 200)}
    html = TEMPLATE.replace("__TITLE__", a.title).replace(
        "__DATA__", json.dumps(data, ensure_ascii=False))
    io.open(a.out, "w", encoding="utf-8").write(html)
    print("wrote", a.out, "rows", len(rows), "bytes", os.path.getsize(a.out))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
 --bg:#f6f7f9; --panel:#fff; --line:#e2e5ea; --line2:#eef0f3;
 --tx:#1a1f26; --tx2:#5a6472; --tx3:#8d97a5;
 --brand:#2f6feb; --ok:#1a7f37; --warn:#9a6700; --bad:#cf222e;
 --wave:#c9d3e0; --wave-on:#2f6feb;
}
html[data-theme="dark"]{
 --bg:#0f1319; --panel:#171c23; --line:#252c36; --line2:#1f252d;
 --tx:#e7edf4; --tx2:#9aa5b3; --tx3:#6c7683;
 --brand:#6ea8fe; --ok:#4ac26b; --warn:#d4a72c; --bad:#ff6b6b;
 --wave:#2c3542; --wave-on:#6ea8fe;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
 font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
 -webkit-font-smoothing:antialiased}
.wrap{max-width:1240px;margin:0 auto;padding:26px 22px 90px}
header{display:flex;align-items:flex-start;gap:16px;margin-bottom:6px}
h1{font-size:20px;margin:0;letter-spacing:-.2px}
.sub{color:var(--tx2);font-size:12.5px;margin-top:4px}
.spacer{flex:1}
.iconbtn{background:var(--panel);border:1px solid var(--line);color:var(--tx2);
 border-radius:8px;cursor:pointer;padding:6px 11px;font-size:12.5px}
.iconbtn:hover{border-color:var(--brand);color:var(--brand)}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:16px 0 20px;
 padding:11px 13px;background:var(--panel);border:1px solid var(--line);border-radius:11px;
 position:sticky;top:8px;z-index:20;box-shadow:0 2px 10px rgba(16,24,40,.04)}
.btn{background:var(--bg);border:1px solid var(--line);color:var(--tx);border-radius:8px;
 padding:7px 13px;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.btn:hover{border-color:var(--brand);color:var(--brand)}
.btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
.btn.primary:hover{filter:brightness(1.08);color:#fff}
.btn.ghost{background:transparent}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden}
.seg button{background:var(--panel);border:0;color:var(--tx2);padding:7px 12px;font-size:12.5px;cursor:pointer}
.seg button+button{border-left:1px solid var(--line)}
.seg button.on{background:var(--brand);color:#fff}
.hint{color:var(--tx3);font-size:12px;margin-left:auto}

.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
 padding:14px 16px;margin-bottom:11px;transition:border-color .15s,box-shadow .15s}
.card.active{border-color:var(--brand);box-shadow:0 0 0 3px rgba(47,111,235,.12)}
.chead{display:flex;align-items:center;gap:10px;margin-bottom:9px;flex-wrap:wrap}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;color:var(--tx2);
 background:var(--bg);border:1px solid var(--line2);border-radius:6px;padding:2px 7px}
.who{font-size:12.5px;color:var(--tx2)}
.pill{font-size:11.5px;border:1px solid var(--line);border-radius:20px;padding:1px 9px;color:var(--tx2)}
.pill.emo{border-color:rgba(47,111,235,.35);color:var(--brand)}
.pill.warn{border-color:var(--warn);color:var(--warn);cursor:help}
.line{font-size:14.5px;line-height:1.6;margin:2px 0 12px;color:var(--tx)}
.line .q{color:var(--tx3)}
.asr{font-size:12px;color:var(--tx2);margin:-8px 0 11px}
.asr b{font-weight:600;color:var(--ok);font-size:11px;letter-spacing:.4px;margin-right:6px}
.asr.w2v b{color:var(--warn)}
.w2vtxt{font-family:ui-monospace,monospace;font-size:11.5px;color:var(--tx2)}
.w2vtxt em{font-style:normal;color:var(--bad);background:rgba(207,34,46,.10);
 border-bottom:1px solid currentColor;padding:0 2px;border-radius:2px}

.takes{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}
.refbar{display:flex;align-items:center;gap:13px;background:var(--panel);border:1px solid var(--line);
 border-radius:12px;padding:11px 15px;margin-bottom:14px}
.refbar .rst{font-family:ui-monospace,monospace;font-size:10.5px;font-weight:700;color:#fff;
 background:var(--warn);border-radius:5px;padding:1px 7px;letter-spacing:.5px}
.refbar .rt{font-size:13px;font-weight:600}
.refbar .rs{font-size:11.5px;color:var(--tx3);margin-top:1px}
.take{border:1px solid var(--line);border-radius:10px;padding:9px 10px 8px;background:var(--bg);
 position:relative;overflow:hidden}
.take.missing{opacity:.45;border-style:dashed}
.take.on{border-color:var(--brand);background:color-mix(in srgb,var(--brand) 6%,var(--bg))}
.thead{display:flex;align-items:center;gap:7px;margin-bottom:6px}
.tk{font-family:ui-monospace,monospace;font-size:11px;font-weight:700;color:#fff;background:var(--tx3);
 border-radius:5px;padding:1px 6px}
.take.on .tk{background:var(--brand)}
.tlabel{font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dur{margin-left:auto;font-size:11.5px;color:var(--tx3);font-variant-numeric:tabular-nums}
.wavewrap{display:flex;align-items:center;gap:8px}
.play{width:30px;height:30px;min-width:30px;border-radius:50%;border:1px solid var(--line);
 background:var(--panel);color:var(--tx);cursor:pointer;font-size:12px;display:grid;place-items:center;
 transition:.12s}
.play:hover{border-color:var(--brand);color:var(--brand)}
.take.on .play{background:var(--brand);border-color:var(--brand);color:#fff}
canvas{width:100%;height:30px;display:block;cursor:pointer}
.metrics{display:flex;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--tx3);margin-top:7px;
 font-variant-numeric:tabular-nums}
.metrics span b{color:var(--tx2);font-weight:600}
.metrics .bad{color:var(--bad)}
.metrics .ok{color:var(--ok)}
.gaps{font-size:11px;color:var(--tx3);margin-top:3px}
.foot{color:var(--tx3);font-size:12px;margin-top:26px;line-height:1.9}
@media(max-width:1180px){.takes{grid-template-columns:repeat(2,1fr)}}
@media(max-width:640px){.takes{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<header>
 <div><h1 id="h1"></h1><div class="sub" id="sub"></div></div>
 <div class="spacer"></div>
 <button class="iconbtn" id="theme">◐ 深色</button>
</header>

<div class="toolbar">
 <button class="btn primary" id="playall">▶ 顺序播放最新版</button>
 <button class="btn" id="aball">A→B→C→D 逐条对比</button>
 <button class="btn ghost" id="stop">■ 停</button>
 <div class="seg" id="speed">
   <button data-r="0.85">0.85×</button><button data-r="1" class="on">1×</button><button data-r="1.15">1.15×</button>
 </div>
 <div class="hint" id="now">点任意波形开始播放</div>
</div>

<div id="refbar"></div>
<div id="list"></div>
<div class="foot" id="foot"></div>
</div>

<script>
const DATA = __DATA__;
function colorOf(k){
  const dark = document.documentElement.dataset.theme === 'dark';
  if(k==='D') return dark? '#7ee2b8' : '#1a7f37';
  if(k==='C') return dark? '#7aa2ff' : '#2f6feb';
  if(k==='B') return dark? '#e3b341' : '#bf8700';
  return dark? '#8b94a3' : '#8d97a5';
}
let audio = new Audio();
audio.preload = 'auto';
let playing = null;   // {card, take}
let queue = [], qmode = '';

const $ = s => document.querySelector(s);
document.getElementById('h1').textContent = DATA.title;
document.getElementById('sub').textContent = '生成于 ' + DATA.generated + ' · ' + DATA.rows.length + ' 条 · 点击波形任意位置播放（drag 可拖动）';

function fmt(v, suf, dec){ return (v===null||v===undefined) ? '—' : (dec? v.toFixed(dec): v) + (suf||''); }

function buildWave(canvas, env, color){
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 220, h = 30;
  canvas.width = w*dpr; canvas.height = h*dpr;
  const g = canvas.getContext('2d'); g.scale(dpr,dpr);
  g.clearRect(0,0,w,h);
  const n = env.length; if(!n) return;
  const bw = w/n;
  for(let i=0;i<n;i++){
    const v = Math.max(env[i], 0.02);
    const bh = Math.max(1.5, v*(h-4));
    g.fillStyle = env[i] < 0.06 ? 'rgba(207,34,46,.32)' : color;
    g.fillRect(i*bw, (h-bh)/2, Math.max(bw*0.72, .7), bh);
  }
}

function playPlain(src, label, offset){
  audio.src = src; audio.currentTime = offset||0; audio.play().catch(()=>{});
  playing = null;
  document.querySelectorAll('.take').forEach(el=>el.classList.remove('on'));
  document.querySelectorAll('.card').forEach(c=>c.classList.remove('active'));
  $('#now').textContent = label;
}

function renderRef(){
  if(!DATA.ref){ return; }
  const el = $('#refbar');
  el.className = 'refbar';
  el.innerHTML = `
    <button class="play" id="refplay">▶</button>
    <div style="flex:1;min-width:0">
      <div class="rt"><span class="rst">REF</span> ${DATA.ref.label || ''}${DATA.ref.dur? ' · '+DATA.ref.dur.toFixed(2)+'s':''}</div>
      <div class="rs">${DATA.ref.text}　（D 列用这一段当音色参考）</div>
    </div>
    <canvas id="refcv" style="width:34%;height:30px;cursor:pointer"></canvas>`;
  const cv = el.querySelector('#refcv');
  requestAnimationFrame(()=>buildWave(cv, DATA.ref.env, getComputedStyle(root).getPropertyValue('--warn').trim()||'#9a6700'));
  el.querySelector('#refplay').onclick = () => {
    if(audio.src.endsWith(DATA.ref.src) && !audio.paused){ audio.pause(); el.querySelector('#refplay').textContent='▶'; }
    else { playPlain(DATA.ref.src, 'REF · c185 参考原声', 0); el.querySelector('#refplay').textContent='❚❚'; }
  };
  cv.onclick = e => {
    const r = cv.getBoundingClientRect();
    playPlain(DATA.ref.src, 'REF · c185 参考原声', (e.clientX-r.left)/r.width*(DATA.ref.dur||0));
  };
}

function render(){
  const list = $('#list');
  list.innerHTML = '';
  DATA.rows.forEach((row, idx) => {
    const card = document.createElement('div');
    card.className = 'card'; card.dataset.idx = idx;
    const lastIdx = row.takes.length - 1;
    const hasC = !row.takes[lastIdx].missing;
    card.innerHTML = `
      <div class="chead">
        <span class="mono">${row.id}</span>
        <span class="who">${row.who}</span>
        ${row.emo?`<span class="pill emo">${row.emo}</span>`:''}
        ${hasC?'':'<span class="pill">新版未生成</span>'}
        ${row.cflag==='WARN'?`<span class="pill warn" title="${row.cnote}">C 有告警</span>`:''}
      </div>
      <div class="line"><span class="q">‘</span>${row.text.replace(/^[‘'"]|[’'"]$/g,'').replace(/^(.*)\.$/,'$1.')}<span class="q">’</span></div>
      ${row.asr?`<div class="asr"><b>ASR 复检${row.asr_src?' · '+row.asr_src+' 列':''}</b>${row.asr}</div>`:''}
      ${row.w2v?`<div class="asr w2v"><b>声学复检 w2v · ${(row.w2v.cov*100).toFixed(0)}%</b><span class="w2vtxt">${row.w2v.text}</span></div>`:''}
      <div class="takes"></div>`;
    const tw = card.querySelector('.takes');
    row.takes.forEach((t, ti) => {
      const d = document.createElement('div');
      d.className = 'take' + (t.missing?' missing':'');
      if(t.missing){
        d.innerHTML = `<div class="thead"><span class="tk">${t.key}</span><span class="tlabel">${t.label}</span></div>
          <div class="gaps">尚未生成</div>`;
      } else {
        const mV = t.wpm!==null? `<span><b>${t.wpm}</b> wpm</span>`:'';
        const mT = t.tilt!==null? `<span><b>${t.tilt.toFixed(3)}</b> tilt</span>`:'';
        const mF = t.f0!==null? `<span><b>${t.f0}</b> Hz</span>`:'';
        d.innerHTML = `
          <div class="thead"><span class="tk">${t.key}</span><span class="tlabel" title="${t.sub}">${t.label}</span>
            <span class="dur">${t.dur? t.dur.toFixed(2)+'s':''}</span></div>
          <div class="wavewrap"><button class="play">▶</button><canvas></canvas></div>
          <div class="metrics">${mV}${mT}${mF}</div>
          ${t.gaps&&t.gaps.length?`<div class="gaps">停顿 ${t.gaps.join(' / ')}s</div>`:''}`;
        const cv = d.querySelector('canvas');
        requestAnimationFrame(()=>buildWave(cv, t.env, colorOf(t.key)));
        d.querySelector('.play').onclick = e => { e.stopPropagation(); toggle(card, ti); };
        cv.onclick = e => {
          const r = cv.getBoundingClientRect();
          const frac = (e.clientX - r.left)/r.width;
          playTake(card, ti, frac * (t.dur||0));
        };
      }
      tw.appendChild(d);
    });
    list.appendChild(card);
  });
}

function markOn(card, ti){
  document.querySelectorAll('.card.active').forEach(c=>{ if(c!==card) c.classList.remove('active'); });
  card.classList.add('active');
  card.querySelectorAll('.take').forEach((el,i)=>el.classList.toggle('on', i===ti));
  const row = DATA.rows[+card.dataset.idx], t = row.takes[ti];
  $('#now').textContent = `${row.id} · ${t.key} ${t.label}`;
}

function playTake(card, ti, offset){
  const row = DATA.rows[+card.dataset.idx], t = row.takes[ti];
  if(t.missing) return;
  if(playing && playing.card===card && playing.ti===ti){
    if(audio.paused){ audio.play(); } else { audio.pause(); }
    return;
  }
  playing = {card, ti};
  markOn(card, ti);
  audio.src = t.src;
  audio.currentTime = offset || 0;
  audio.play().catch(()=>{});
}

function toggle(card, ti){
  const t = DATA.rows[+card.dataset.idx].takes[ti];
  if(t.missing) return;
  if(playing && playing.card===card && playing.ti===ti && !audio.paused){ audio.pause(); }
  else playTake(card, ti, 0);
}

audio.onended = () => {
  if(queue.length){ const n = queue.shift(); n(); }
};
audio.onpause = () => {
  const el = document.querySelector('.take.on .play'); if(el) el.textContent = '▶';
};
audio.onplay = () => {
  const el = document.querySelector('.take.on .play'); if(el) el.textContent = '❚❚';
};

// ---- 批量 ----
function cards(){ return [...document.querySelectorAll('.card')]; }

$('#playall').onclick = () => {
  queue = [];
  cards().forEach((c,i) => {
    const row = DATA.rows[i];
    const last = row.takes.length - 1;
    if(row.takes[last].missing) return;
    queue.push(()=>playTake(c, last, 0));
  });
  if(queue.length) queue.shift()();
};

$('#aball').onclick = () => {
  queue = [];
  cards().forEach((c,i) => {
    const row = DATA.rows[i];
    row.takes.forEach((t,ti) => { if(!t.missing) queue.push(()=>playTake(c, ti, 0)); });
  });
  if(queue.length) queue.shift()();
};

$('#stop').onclick = () => { queue = []; audio.pause(); };

document.querySelectorAll('#speed button').forEach(b => {
  b.onclick = () => {
    document.querySelectorAll('#speed button').forEach(x=>x.classList.remove('on'));
    b.classList.add('on');
    audio.playbackRate = parseFloat(b.dataset.r);
  };
});

// ---- 主题 ----
const root = document.documentElement;
if(localStorage.getItem('lp-theme')==='dark'){ root.dataset.theme='dark'; $('#theme').textContent='◑ 浅色'; }
$('#theme').onclick = () => {
  const dark = root.dataset.theme === 'dark';
  root.dataset.theme = dark ? '' : 'dark';
  localStorage.setItem('lp-theme', dark ? 'light':'dark');
  $('#theme').textContent = dark ? '◐ 深色':'◑ 浅色';
  // canvas 颜色随主题重画
  document.querySelectorAll('.card').forEach((c,i)=>{
    c.querySelectorAll('canvas').forEach((cv,ti)=>{
      const t = DATA.rows[i].takes[ti]; if(!t.missing) buildWave(cv, t.env, colorOf(t.key));
    });
  });
};

window.addEventListener('resize', ()=>{
  document.querySelectorAll('.card').forEach((c,i)=>{
    c.querySelectorAll('canvas').forEach((cv,ti)=>{
      const t = DATA.rows[i].takes[ti]; if(!t.missing) buildWave(cv, t.env, colorOf(t.key));
    });
  });
});

function wordDiff(gold, hyp){
  // 简易 LCS：hyp 里不在最长公共子序列中的词判为「听不出来/发错」
  const g = gold.toUpperCase().replace(/[^A-Z ]+/g,' ').split(/\s+/).filter(Boolean);
  const h = hyp.toUpperCase().replace(/[^A-Z ]+/g,' ').split(/\s+/).filter(Boolean);
  const n=g.length, m=h.length;
  const dp = Array.from({length:n+1},()=>new Int32Array(m+1));
  for(let i=n-1;i>=0;i--) for(let j=m-1;j>=0;j--)
    dp[i][j] = g[i]===h[j] ? dp[i+1][j+1]+1 : Math.max(dp[i+1][j], dp[i][j+1]);
  const keep = new Set();
  let i=0,j=0;
  while(i<n&&j<m){
    if(g[i]===h[j]){ keep.add(j); i++; j++; }
    else if(dp[i+1][j] >= dp[i][j+1]) i++;
    else j++;
  }
  return h.map((w,k)=> keep.has(k)? w : `<em>${w}</em>`).join(' ');
}

renderRef();
render();
DATA.rows.forEach((row, idx)=>{
  if(!row.w2v) return;
  const card = document.querySelectorAll('.card')[idx];
  if(!card) return;
  const el = card.querySelector('.w2vtxt');
  if(el) el.innerHTML = wordDiff(row.text, row.w2v.text);
});
if(DATA.note) $('#foot').innerHTML = DATA.note;
</script></body></html>
"""

if __name__ == "__main__":
    main()
