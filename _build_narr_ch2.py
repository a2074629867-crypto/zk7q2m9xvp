# -*- coding: utf-8 -*-
"""旁白第二章试听页（自包含 HTML + 相对音频路径）。

每条 = 一句旁白，同屏给出：
  1) 正文：重音词加粗、慢读句标 0.84×、停顿槽按三档上色（inner/bound/clause）
  2) 波形包络（点击任意位置播放/跳转）
  3) 实测：时长 / 吐字语速 / 静音处数与中位
  4) 音源可切：三档停顿版（out_paused_narr，生产候选）↔ 验收版（out，PASS 712 基线）

用法：
  G:/Python310/python.exe -u _build_narr_ch2.py
  G:/Python310/python.exe -u _build_narr_ch2.py --chapter "Chapter Two" --out _narr_ch2_listen.html
"""
import argparse
import io
import json
import os
import re
import time

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
sys_path = ROOT
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)
import _speedlib  # 句中语速（唯一口径）
A_NEW = "_audio_ch123/out_paused_narr"   # 三档停顿（候选）
A_OLD = "_audio_ch123/out"               # 已验收基线
PLAN = "_narr_plan_for_pause.jsonl"
PAUSE = "pause_llm_narr_v3.json"
STRESS = "stress_tts_narr.json"
RATE = "rate_narr_sent_v1.json"
# 返工 take：本轮重生成并已按 cov/喊叫/缺词 选出来的新版本（_sweep/cand53/pick）。
# 只内联进页面给人耳 AB，**不回填**到 out_paused_narr —— 回填要等点头。
REWORK = "_sweep/cand53/pick"


def load_json(p):
    with io.open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)


def envelope(path, npts=110):
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        return []
    if getattr(y, "ndim", 1) > 1:
        y = y.mean(1)
    if not len(y):
        return []
    win = max(1, len(y) // npts)
    out = [float(np.abs(y[i * win:(i + 1) * win]).max()) if len(y[i * win:(i + 1) * win]) else 0.0
           for i in range(npts)]
    mx = max(out) or 1.0
    return [round(v / mx, 3) for v in out]


def dur_of(path):
    try:
        return round(sf.info(path).duration, 2)
    except Exception:
        return None


def gaps(path, thr=-45.0, min_gap=0.18):
    """能量法静音检测，返回 (处数, 中位秒, 全部秒列表)。"""
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        return 0, None, []
    if getattr(y, "ndim", 1) > 1:
        y = y.mean(1)
    if not len(y):
        return 0, None, []
    hop = max(1, int(sr * 0.01))
    n = len(y) // hop
    if n < 3:
        return 0, None, []
    fr = y[:n * hop].reshape(n, hop)
    db = 20 * np.log10(np.maximum(np.abs(fr).max(1), 1e-9))
    sil = db < thr
    out, run = [], 0
    for v in sil:
        if v:
            run += 1
        else:
            if run >= min_gap / 0.01:
                out.append(round(run * 0.01, 2))
            run = 0
    if run >= min_gap / 0.01:
        out.append(round(run * 0.01, 2))
    # 首尾静音不是停顿，剔掉
    secs = [g for g in out if g >= min_gap]
    if not secs:
        return 0, None, []
    return len(secs), round(float(np.median(secs)), 2), secs[:6]


def stress_html(xml):
    """把 <rate factor> / <pitch> 标记转成 span，返回已转义的 HTML 片段列表（按空格切）。"""
    s = (xml.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    s = re.sub(r'&lt;rate factor="[\d.]+"&gt;', '<b class="st">', s)
    s = re.sub(r'&lt;pitch semitones="-?[\d.]+"&gt;', '<b class="st end">', s)
    s = s.replace("&lt;/rate&gt;", "</b>").replace("&lt;/pitch&gt;", "</b>")
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", default="Chapter Two")
    ap.add_argument("--out", default=os.path.join(ROOT, "_narr_ch2_listen.html"))
    ap.add_argument("--title", default="")
    ap.add_argument("--new", default=A_NEW,
                    help="三档停顿版目录（默认旧库；新标准用 _regen_1123_paused）")
    ap.add_argument("--old", default=A_OLD, help="对照旧版目录")
    ap.add_argument("--rates", default=RATE,
                    help="rate 表；新标准用 _rate_narr_v2.json（1.00/0.84），别用旧的 rate_narr_sent_v1")
    ap.add_argument("--only716", action="store_true",
                    help="只保留 _narr_ids716.json 里的 id（plan 里另有 10 条没音频的旁白行）")
    a = ap.parse_args()
    dNew, dOld = a.new, a.old

    plan = [json.loads(l) for l in io.open(os.path.join(ROOT, PLAN), encoding="utf-8") if l.strip()]
    pause = load_json(PAUSE)
    stress = load_json(STRESS).get("items") or {}
    rates = load_json(a.rates).get("rates") or {}
    keep = None
    if a.only716:
        keep = set(json.load(io.open(os.path.join(ROOT, "_narr_ids716.json"), encoding="utf-8")))

    rows = [r for r in plan if r.get("speaker") == "narrator"
            and (a.chapter == "all" or r.get("chapter") == a.chapter)
            and (keep is None or r["id"] in keep)]
    rows.sort(key=lambda r: r.get("idx", 0))
    print("章节 %s 旁白 %d 句" % (a.chapter, len(rows)))

    out_rows = []
    stat = {"slow": 0, "stress": 0, "pauses": 0, "kinds": {}, "missing": 0, "rework": 0,
            "fallback": 0}
    now = time.time()
    for r in rows:
        i = r["id"]
        text = r.get("text") or ""
        xhtml = stress_html((stress.get(i) or {}).get("xml") or text)
        toks = xhtml.split(" ")
        # 停顿槽：key = 词下标（0 基），插在该词之后
        ps = pause.get(i) or {}
        marks = {}
        for k, v in ps.items():
            try:
                marks[int(k)] = {"d": float(v.get("d") or 0),
                                 "kind": v.get("kind") or "inner",
                                 "why": v.get("why") or ""}
            except (TypeError, ValueError):
                continue
        if marks:
            stat["pauses"] += len(marks)
            for m in marks.values():
                stat["kinds"][m["kind"]] = stat["kinds"].get(m["kind"], 0) + 1
        parts = []
        for ti, tk in enumerate(toks):
            parts.append(tk)
            m = marks.get(ti)
            if m:
                parts.append('<i class="pm %s" title="%s">%s</i>' % (
                    m["kind"], m["why"].replace('"', "'")[:90], ("%.2f" % m["d"])))
        body = " ".join(parts)

        has_st = ('class="st"' in xhtml)
        if has_st:
            stat["stress"] += 1
        rv = rates.get(i)
        slow = (rv is not None and float(rv) < 0.99)
        if slow:
            stat["slow"] += 1

        takes = {}
        for tag, d in (("new", dNew), ("old", dOld)):
            p = os.path.join(ROOT, d, i + ".wav")
            if os.path.exists(p):
                ng, med, secs = gaps(p) if tag == "new" else (None, None, [])
                takes[tag] = {"src": "%s/%s.wav" % (d, i), "dur": dur_of(p),
                              "env": envelope(p),
                              "ng": ng, "gmed": med}
                if tag == "new" and ng is not None:
                    takes[tag]["gaps"] = secs
            else:
                takes[tag] = None

        # 返工版（本轮新 take）：只内联到页面，不替换上两路音源
        rp = os.path.join(ROOT, REWORK, i + ".wav")
        if os.path.exists(rp):
            takes["rework"] = {"src": "%s/%s.wav" % (REWORK, i),
                               "dur": dur_of(rp), "env": envelope(rp)}
            stat["rework"] += 1

        # 没有三档版就退回验收版（这 3 句本来就没标注槽位，改不改都是同一条音频），
        # 不能让卡片变成不可播的"缺音频"。
        if not takes.get("new") and takes.get("old"):
            takes["new"] = dict(takes["old"], fallback=True)
            stat["fallback"] += 1

        d0 = (takes.get("new") or takes.get("old") or {}).get("dur")
        nw = r.get("words") or len(text.split())
        # ★ 2026-11-24 改口径：wpm = 词数 ÷ **句内发声时长**（不含逗号/句号的大间隔）。
        #   旧写法 nw/d0 把停顿算进分母 ⇒ 同一条音频换个停顿就换一个 wpm，
        #   既不是「说得快」也不是「停顿多」，两个变量混在一起没法判断。
        _src = (takes.get("new") or takes.get("old") or {}).get("src")
        _wpm = _speedlib.wpm_in(os.path.join(ROOT, _src), nw) if _src else None
        out_rows.append({
            "id": i, "para": r.get("para"), "part": r.get("part"),
            "text": text, "html": body, "words": nw,
            "wpm": int(round(_wpm)) if _wpm else None,
            "wpm_total": int(round(nw / d0 * 60)) if d0 else None,
            "stress": has_st, "slow": slow, "rate": rv,
            "pauses": len(marks), "takes": takes,
        })
        if not takes.get("new"):
            stat["missing"] += 1

    data = {
        "title": a.title or ("旁白 · %s 试听" % a.chapter.replace("Chapter ", "第").replace("One", "一").replace("Two", "二").replace("Three", "三")),
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "chapter": a.chapter,
        "stat": stat,
        "rows": out_rows,
        "srcNew": dNew, "srcOld": dOld, "srcRework": REWORK,
    }
    html = TEMPLATE.replace("__TITLE__", data["title"]).replace(
        "__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    with io.open(a.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("统计:", json.dumps(stat, ensure_ascii=False))
    print("wrote %s  %.1f KB  用时 %.1fs" % (a.out, os.path.getsize(a.out) / 1024, time.time() - now))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
 --bg:#f6f7f9;--panel:#fff;--line:#e2e5ea;--line2:#eef0f3;
 --tx:#1a1f26;--tx2:#5a6472;--tx3:#8d97a5;
 --brand:#2f6feb;--ok:#1a7f37;--warn:#9a6700;--bad:#cf222e;
 --inner:#2f6feb;--bound:#8250df;--clause:#bf3989;
 --wave:#c9d3e0;
}
html[data-theme="dark"]{
 --bg:#0f1319;--panel:#171c23;--line:#252c36;--line2:#1f252d;
 --tx:#e7edf4;--tx2:#9aa5b3;--tx3:#6c7683;
 --brand:#6ea8fe;--ok:#4ac26b;--warn:#d4a72c;--bad:#ff6b6b;
 --inner:#6ea8fe;--bound:#a17ef0;--clause:#e07bb8;
 --wave:#2c3542;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
 font:14px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
 -webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:24px 20px 96px}
header{display:flex;align-items:flex-start;gap:14px;margin-bottom:4px}
h1{font-size:19px;margin:0;letter-spacing:-.2px}
.sub{color:var(--tx2);font-size:12.5px;margin-top:4px}
.spacer{flex:1}
.iconbtn{background:var(--panel);border:1px solid var(--line);color:var(--tx2);border-radius:8px;
 cursor:pointer;padding:6px 11px;font-size:12.5px}
.iconbtn:hover{border-color:var(--brand);color:var(--brand)}
.stats{display:flex;gap:16px;flex-wrap:wrap;margin:14px 0 12px;font-size:12px;color:var(--tx2)}
.stats b{color:var(--tx);font-variant-numeric:tabular-nums}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 18px;
 padding:10px 12px;background:var(--panel);border:1px solid var(--line);border-radius:11px;
 position:sticky;top:8px;z-index:20;box-shadow:0 2px 10px rgba(16,24,40,.05)}
.btn{background:var(--bg);border:1px solid var(--line);color:var(--tx);border-radius:8px;
 padding:7px 13px;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.btn:hover{border-color:var(--brand);color:var(--brand)}
.btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
.btn.primary:hover{filter:brightness(1.08);color:#fff}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden}
.seg button{background:var(--panel);border:0;color:var(--tx2);padding:7px 11px;font-size:12.5px;cursor:pointer;white-space:nowrap}
.seg button+button{border-left:1px solid var(--line)}
.seg button.on{background:var(--brand);color:#fff}
.hint{color:var(--tx3);font-size:12px;margin-left:auto;font-variant-numeric:tabular-nums}

.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
 padding:13px 16px 12px;margin-bottom:10px;transition:border-color .15s,box-shadow .15s}
.card.active{border-color:var(--brand);box-shadow:0 0 0 3px rgba(47,111,235,.13)}
.chead{display:flex;align-items:center;gap:9px;margin-bottom:7px;flex-wrap:wrap}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11.5px;color:var(--tx2);
 background:var(--bg);border:1px solid var(--line2);border-radius:6px;padding:1px 7px}
.pill{font-size:11px;border:1px solid var(--line);border-radius:20px;padding:0 8px;color:var(--tx2);line-height:1.7}
.pill.slow{border-color:rgba(154,103,0,.45);color:var(--warn)}
.pill.st{border-color:rgba(207,34,46,.35);color:var(--bad)}
.pill.dur{margin-left:auto;border:0;color:var(--tx3);font-variant-numeric:tabular-nums;padding:0}
.pill.rk{border-color:rgba(26,127,55,.55);color:var(--ok)}
.rkrow{display:flex;align-items:center;gap:9px;margin-top:8px;padding:6px 10px;
 background:color-mix(in srgb,var(--ok) 7%,var(--bg));border:1px dashed rgba(26,127,55,.45);
 border-radius:9px;font-size:11.5px;color:var(--tx2)}
html[data-theme="dark"] .rkrow{background:color-mix(in srgb,var(--ok) 13%,var(--bg));border-color:rgba(74,194,107,.5)}
.rktag{font-size:10.5px;font-weight:700;color:#fff;background:var(--ok);border-radius:5px;
 padding:1px 6px;letter-spacing:.4px;flex:none}
.play.sm{width:24px;height:24px;min-width:24px;font-size:10px}
.rkd{font-variant-numeric:tabular-nums}
.line{font-size:15px;line-height:2.05;margin:1px 0 9px;color:var(--tx)}
.line b.st{color:var(--bad);font-weight:700;border-bottom:2px solid rgba(207,34,46,.35)}
html[data-theme="dark"] .line b.st{color:#ff8f8f;border-bottom-color:rgba(255,143,143,.35)}
.line b.st.end{border-bottom-style:dotted}
.line i.pm{font-style:normal;font-size:10.5px;font-family:ui-monospace,Consolas,monospace;
 padding:0 3px;margin:0 1px;border-radius:4px;vertical-align:1px;color:#fff;opacity:.85}
.line i.pm.inner{background:var(--inner)}
.line i.pm.bound{background:var(--bound)}
.line i.pm.clause{background:var(--clause)}
.player{display:flex;align-items:center;gap:10px}
.play{width:32px;height:32px;min-width:32px;border-radius:50%;border:1px solid var(--line);
 background:var(--bg);color:var(--tx);cursor:pointer;font-size:12px;display:grid;place-items:center}
.play:hover{border-color:var(--brand);color:var(--brand)}
.card.playing .play{background:var(--brand);border-color:var(--brand);color:#fff}
canvas{flex:1;height:34px;display:block;cursor:pointer;min-width:0}
.meta{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--tx3);margin-top:6px;
 font-variant-numeric:tabular-nums}
.meta b{color:var(--tx2);font-weight:600}
.foot{color:var(--tx3);font-size:12px;margin-top:24px;line-height:1.9}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--tx3);margin:4px 0 14px}
.legend i{font-style:normal;display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:5px;vertical-align:0}
</style></head><body><div class="wrap">
<header>
  <div><h1 id="h1"></h1><div class="sub" id="sub"></div></div>
  <div class="spacer"></div>
  <button class="iconbtn" id="theme">◐ 深色</button>
</header>
<div class="stats" id="stats"></div>
<div class="toolbar">
  <button class="btn primary" id="playall">▶ 从头顺序听</button>
  <button class="btn" id="pause">❚❚</button>
  <button class="btn" id="next">下一句 ▸</button>
  <div class="seg" id="src">
    <button data-k="new" class="on">三档停顿版</button><button data-k="old">验收版</button>
  </div>
  <div class="seg" id="filter">
    <button data-f="all" class="on">全部</button><button data-f="slow">慢读</button><button data-f="stress">有重音</button><button data-f="rework">仅返工</button>
  </div>
  <div class="seg" id="speed">
    <button data-r="0.9">0.9×</button><button data-r="1" class="on">1×</button><button data-r="1.1">1.1×</button>
  </div>
  <div class="hint" id="now">—</div>
</div>
<div class="legend">
  <span><i style="background:var(--inner)"></i>inner 0.51s</span>
  <span><i style="background:var(--bound)"></i>bound 1.135s</span>
  <span><i style="background:var(--clause)"></i>clause 1.695s</span>
  <span><b style="color:var(--bad)">红色词</b> = 标注重音</span>
  <span><b style="color:var(--warn)">0.84×</b> = 标注慢读句</span>
</div>
<div id="list"></div>
<div class="foot" id="foot"></div>
</div>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
const root = document.documentElement;
let audio = new Audio(); audio.preload = 'auto';
let cur = 0, src = 'new', filter = 'all', seq = null, seqIdx = 0, playingCard = null;

$('#h1').textContent = DATA.title;
const st = DATA.stat;
$('#sub').textContent = '生成于 ' + DATA.generated + ' · ' + DATA.rows.length + ' 句 · ' +
  '点击波形任意位置跳转';

function fmt(v, s){ return (v===null||v===undefined)? '—' : v + (s||''); }

function renderStats(){
  $('#stats').innerHTML =
    '<span>句数 <b>'+DATA.rows.length+'</b></span>'+
    '<span>慢读句 <b>'+st.slow+'</b></span>'+
    '<span>有重音 <b>'+st.stress+'</b></span>'+
    '<span>停顿槽 <b>'+st.pauses+'</b>（inner '+(st.kinds.inner||0)+' / bound '+(st.kinds.bound||0)+' / clause '+(st.kinds.clause||0)+'）</span>'+
    (st.rework? '<span style="color:var(--ok)">返工句 <b>'+st.rework+'</b></span>':'')+
    (st.fallback? '<span>无三档版→用验收版 <b>'+st.fallback+'</b></span>':'')+
    (st.missing? '<span style="color:var(--bad)">缺音频 <b>'+st.missing+'</b></span>':'');
}

function colorOf(){
  const dark = root.dataset.theme === 'dark';
  return dark ? '#7aa2ff' : '#2f6feb';
}

function drawWave(cv, env){
  const dpr = window.devicePixelRatio||1;
  const w = cv.clientWidth||300, h = 34;
  cv.width = w*dpr; cv.height = h*dpr;
  const g = cv.getContext('2d'); g.setTransform(dpr,0,0,dpr,0,0); g.clearRect(0,0,w,h);
  const n = env.length; if(!n) return;
  const bw = w/n, c = colorOf();
  for(let i=0;i<n;i++){
    const v = Math.max(env[i], 0.015);
    const bh = Math.max(1.2, v*(h-6));
    g.fillStyle = env[i] < 0.05 ? 'rgba(207,34,46,.28)' : c;
    g.fillRect(i*bw, (h-bh)/2, Math.max(bw*0.7, .7), bh);
  }
}

function render(){
  const list = $('#list'); list.innerHTML = '';
  DATA.rows.forEach((r, idx) => {
    const t = r.takes[src];
    const card = document.createElement('div');
    card.className = 'card'; card.dataset.idx = idx;
    card.dataset.slow = r.slow?1:0; card.dataset.stress = r.stress?1:0;
    card.dataset.rk = r.takes.rework?1:0;
    card.innerHTML = `
      <div class="chead">
        <span class="mono">${r.id}</span>
        <span class="pill">段 ${r.para}${r.part?'.'+r.part:''}</span>
        ${r.slow?`<span class="pill slow">慢读 ${r.rate}×</span>`:''}
        ${r.stress?`<span class="pill st">重音 ${r.pauses?'':''}</span>`:''}
        ${r.pauses?`<span class="pill">停顿 ${r.pauses}</span>`:''}
        ${r.takes.rework?`<span class="pill rk">已返工</span>`:''}
        ${(src==='new'&&t&&t.fallback)?`<span class="pill">无三档版 · 播验收版</span>`:''}
        <span class="pill dur">${t&&t.dur? t.dur.toFixed(2)+'s':''}</span>
      </div>
      <div class="line">${r.html}</div>
      <div class="player">
        <button class="play">▶</button>
        <canvas></canvas>
      </div>
      ${r.takes.rework?`<div class="rkrow">
        <span class="rktag">返工版</span>
        <button class="play sm">▶</button>
        <span class="rkd">${r.takes.rework.dur.toFixed(2)}s · 5s 单句参考 · 本轮新 take（未回填）</span>
      </div>`:''}
      <div class="meta">
        <span title="句中语速：词数 ÷ 句内发声时长，不含逗号句号的大间隔"><b>${fmt(r.wpm)}</b> wpm<small style="color:var(--tx3)"> 句中</small></span>
        <span><b>${fmt(r.words)}</b> 词</span>
        ${t&&t.ng!==null&&t.ng!==undefined?`<span>静音 <b>${t.ng}</b> 处 · 中位 <b>${fmt(t.gmed)}</b>s</span>`:''}
        <span style="color:var(--tx3)">${src==='new'?'三档停顿版':'验收版'}</span>
      </div>`;
    const cv = card.querySelector('canvas');
    requestAnimationFrame(()=>{ if(t) drawWave(cv, t.env||[]); });
    card.querySelector('.play').onclick = e => { e.stopPropagation(); toggle(card); };
    cv.onclick = e => {
      if(!t) return;
      const rc = cv.getBoundingClientRect();
      play(card, (e.clientX-rc.left)/rc.width*(t.dur||0));
    };
    const rk = card.querySelector('.rkrow .play');
    if(rk) rk.onclick = e => { e.stopPropagation(); playRework(card); };
    list.appendChild(card);
  });
  applyFilter();
}

function applyFilter(){
  document.querySelectorAll('.card').forEach(c=>{
    const ok = filter==='all' || (filter==='slow'&&c.dataset.slow==='1') || (filter==='stress'&&c.dataset.stress==='1') || (filter==='rework'&&c.dataset.rk==='1');
    c.style.display = ok? '' : 'none';
  });
}

function visibleCards(){
  return [...document.querySelectorAll('.card')].filter(c=>c.style.display!=='none');
}

function mark(card){
  document.querySelectorAll('.card.playing').forEach(c=>c.classList.remove('playing'));
  document.querySelectorAll('.card.active').forEach(c=>c.classList.remove('active'));
  if(card){ card.classList.add('playing','active'); }
}

function play(card, offset){
  const r = DATA.rows[+card.dataset.idx], t = r.takes[src];
  if(!t) return;
  cur = +card.dataset.idx;
  if(audio.src.indexOf(t.src)>=0 && offset===undefined){
    if(audio.paused){ audio.play(); } else { audio.pause(); }
    return;
  }
  playingCard = card; mark(card);
  audio.src = t.src; audio.currentTime = offset||0;
  audio.play().catch(()=>{});
  $('#now').textContent = r.id + ' · ' + (src==='new'?'三档':'验收') + ' · ' + (cur+1) + '/' + DATA.rows.length;
}

function toggle(card){
  const r = DATA.rows[+card.dataset.idx], t = r.takes[src];
  if(!t) return;
  if(audio.src.indexOf(t.src)>=0 && !audio.paused){ audio.pause(); return; }
  play(card, 0);
}

// 返工版单独播：不参与 src 切换与顺序播放，只在卡片里就地 AB
function playRework(card){
  const r = DATA.rows[+card.dataset.idx], t = r.takes.rework;
  if(!t) return;
  cur = +card.dataset.idx; playingCard = card; seq = null;
  if(audio.src.indexOf(t.src)>=0 && !audio.paused){ audio.pause(); return; }
  mark(card);
  audio.src = t.src; audio.currentTime = 0;
  audio.play().catch(()=>{});
  $('#now').textContent = r.id + ' · 返工版 · ' + t.dur.toFixed(2) + 's';
}

audio.onended = () => {
  if(seq){ nextInSeq(); return; }
  const c = playingCard; if(c) c.classList.remove('playing');
};
audio.onplay = () => { if(playingCard) playingCard.classList.add('playing'); };
audio.onpause = () => { if(playingCard) playingCard.classList.remove('playing'); };

function nextInSeq(){
  seqIdx++;
  const cards = visibleCards();
  if(seqIdx >= cards.length){ seq = null; $('#now').textContent='播完 · 共 '+cards.length+' 句'; return; }
  const c = cards[seqIdx];
  c.scrollIntoView({block:'center', behavior:'smooth'});
  play(c, 0);
}

$('#playall').onclick = () => {
  const cards = visibleCards(); if(!cards.length) return;
  seq = true; seqIdx = 0; play(cards[0], 0);
  cards[0].scrollIntoView({block:'center', behavior:'smooth'});
};
$('#pause').onclick = () => { seq=null; audio.pause(); };
$('#next').onclick = () => {
  const cards = visibleCards(); if(!cards.length) return;
  const i = cards.findIndex(c=>+c.dataset.idx===cur);
  const n = cards[(i+1) % cards.length];
  n.scrollIntoView({block:'center', behavior:'smooth'});
  play(n, 0);
};

document.querySelectorAll('#src button').forEach(b=>{
  b.onclick = () => {
    document.querySelectorAll('#src button').forEach(x=>x.classList.remove('on'));
    b.classList.add('on'); src = b.dataset.k;
    seq = null; audio.pause();
    render();
  };
});
document.querySelectorAll('#filter button').forEach(b=>{
  b.onclick = () => {
    document.querySelectorAll('#filter button').forEach(x=>x.classList.remove('on'));
    b.classList.add('on'); filter = b.dataset.f; applyFilter();
  };
});
document.querySelectorAll('#speed button').forEach(b=>{
  b.onclick = () => {
    document.querySelectorAll('#speed button').forEach(x=>x.classList.remove('on'));
    b.classList.add('on'); audio.playbackRate = parseFloat(b.dataset.r);
  };
});

if(localStorage.getItem('narr-theme')==='dark'){ root.dataset.theme='dark'; $('#theme').textContent='◑ 浅色'; }
$('#theme').onclick = () => {
  const dark = root.dataset.theme === 'dark';
  root.dataset.theme = dark? '' : 'dark';
  localStorage.setItem('narr-theme', dark? 'light':'dark');
  $('#theme').textContent = dark? '◐ 深色' : '◑ 浅色';
  render();
};

window.addEventListener('resize', ()=>{ render(); });

renderStats(); render();
$('#foot').innerHTML = '音源：<b>三档停顿版</b> <span class="mono">'+DATA.srcNew+'</span>（716/716 注入完成，物理闸同数 PASS 712）　·　<b>验收版</b> <span class="mono">'+DATA.srcOld+'</span>（PASS 712 基线）。两版同句 AB 可直接切换对比。'
  + (DATA.stat.rework? '<br><b style="color:var(--ok)">返工版</b> <span class="mono">'+DATA.srcRework+'</span>：' + DATA.stat.rework + ' 句换成 2026-11-21 00:4x 按 5s 单句参考重生成的 take（已按 cov / 像喊 / 缺词 筛过种子）。<b>尚未回填</b>到上面的音源目录，听感点头后再回填。' : '')
  + '<br><b>语速已按真人母带校准</b>：每句 tempo 逐句压缩到 175 wpm（真人 p50），0.84 慢读档落在 147 wpm；'
  + '红字重音仍只存在于标注层（词级 rate 标签 11-21 实测无效，改走换 seed 择优）'
  + '（factor 0.70 与 1.40 输出时长完全相同，被点名的词一次都没被拉长），详见 DECISIONS.md 2026-11-21 那条。'
  + '听感与标注不一致是预期内的，不是漏做。';
</script></body></html>
"""

if __name__ == "__main__":
    main()
