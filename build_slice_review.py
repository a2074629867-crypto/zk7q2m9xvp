# -*- coding: utf-8 -*-
"""训练前标注审阅页（切片级）—— Parakeet TDT v3 + 定点修正

输出: reader/_voice_lab/review_slices.html
"""
import html
import json
import os
import re

D = "G:/GPT-SoVITS/_dataset_v5full"
OUT = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_voice_lab/review_slices.html"
MP3 = "wonder_review.mp3"
SR = 32000

LIST = json.load(open(D + "/wonder_parakeet_fixes.json", encoding="utf-8"))
WORDS = json.load(open(D + "/wonder_parakeet_words.json", encoding="utf-8"))
SLICES = {s["file"]: s for s in WORDS["slices"]}

fix_of = {}
for x in LIST["fixes"]:
    fix_of.setdefault(x["file"], []).append(x)
flag_of = {}
for x in LIST["flagged"]:
    flag_of.setdefault(x["file"], []).append(x)

rows = []
for line in open(D + "/wonder_v5full_parakeet_fixed.list", encoding="utf-8"):
    line = line.rstrip("\n")
    if not line:
        continue
    f, spk, lang, txt = line.split("|", 3)
    s = SLICES.get(f)
    if s is None:
        continue
    rows.append(dict(f=f, t0=s["t0"], t1=s["t1"], txt=txt,
                     n=len(txt.split()), dur=s["t1"] - s["t0"],
                     fix=fix_of.get(f, []), flag=flag_of.get(f, [])))

# 补上完全没词的切片（从 slices_df3 里找）
allf = {s["file"] for s in WORDS["slices"]}
inlist = {r["f"] for r in rows}
for s in WORDS["slices"]:
    if s["file"] not in inlist:
        rows.append(dict(f=s["file"], t0=s["t0"], t1=s["t1"], txt="",
                         n=0, dur=s["t1"] - s["t0"], fix=[], flag=[]))
rows.sort(key=lambda r: r["t0"])

tot_dur = sum(r["dur"] for r in rows)
tot_w = sum(r["n"] for r in rows)
n_empty = sum(1 for r in rows if r["n"] == 0)
n_short = sum(1 for r in rows if 0 < r["n"] < 3)
n_fix = sum(1 for r in rows if r["fix"])
n_flag = sum(1 for r in rows if r["flag"])

body = []
for i, r in enumerate(rows):
    cls = []
    if r["n"] == 0:
        cls.append("empty")
    elif r["n"] < 3:
        cls.append("short")
    if r["fix"]:
        cls.append("fixed")
    if r["flag"]:
        cls.append("flagged")
    txt = html.escape(r["txt"]) or '<span class="nil">（空片 · 无文本）</span>'
    for x in r["fix"]:
        txt = txt.replace(html.escape(x["after"]),
                          '<mark title="原: %s">%s</mark>' % (
                              html.escape(x["before"]), html.escape(x["after"])), 1)
    tags = ""
    for x in r["fix"]:
        tags += '<span class="tag f" title="%s">已修正</span>' % html.escape(x["why"])
    for x in r["flag"]:
        tags += '<span class="tag q" title="%s">待裁决</span>' % html.escape(x["why"])
    if r["n"] == 0:
        tags += '<span class="tag e">空片</span>'
    elif r["n"] < 3:
        tags += '<span class="tag s">极短</span>'
    body.append(
        '<div class="row %s" data-empty="%d" data-short="%d" data-fix="%d" data-flag="%d">'
        '<div class="tm"><button class="play" data-t="%.2f">%d:%04.1f</button>'
        '<span class="dur">%.1fs</span></div>'
        '<div class="tx">%s</div>'
        '<div class="meta"><span class="wc">%d 词</span>%s</div></div>'
        % (" ".join(cls), 1 if r["n"] == 0 else 0, 1 if 0 < r["n"] < 3 else 0,
           1 if r["fix"] else 0, 1 if r["flag"] else 0,
           r["t0"], int(r["t0"] // 60), r["t0"] % 60, r["dur"], txt, r["n"], tags))

HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>训练标注审阅 · Wonder (Calm) · Parakeet TDT v3</title>
<style>
*{box-sizing:border-box}
body{margin:0;font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
background:#0f1115;color:#e6e8ec}
header{padding:18px 24px 12px;border-bottom:1px solid #232733;position:sticky;top:0;background:#0f1115;z-index:10}
h1{margin:0 0 5px;font-size:16.5px;font-weight:600}
.sub{color:#8b93a5;font-size:12.5px}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:11px 0 9px;font-size:12.5px}
.st{background:#171a22;border:1px solid #232733;border-radius:8px;padding:5px 11px}
.st b{color:#5ee0a0;font-weight:600}
.st.w b{color:#ffb454}
audio{width:100%;height:32px;margin-top:6px}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}
.filters button{background:#171a22;border:1px solid #2b3040;color:#c8cede;border-radius:999px;
padding:4px 12px;font-size:12.5px;cursor:pointer}
.filters button.on{background:#2b6cb0;border-color:#3b82d6;color:#fff}
main{padding:12px 24px 70px}
.row{display:grid;grid-template-columns:104px 1fr 130px;gap:14px;padding:9px 12px;
border-bottom:1px solid #1b1f29;border-radius:8px;align-items:start}
.row:hover{background:#141821}
.row.empty{opacity:.45}
.row.flagged{background:#1d1a12}
.tm{font-variant-numeric:tabular-nums}
.play{background:#1e2531;border:1px solid #2f3748;color:#7fb0ff;border-radius:6px;padding:3px 8px;
font-size:12px;cursor:pointer;font-variant-numeric:tabular-nums}
.play:hover{background:#26314a}
.dur{display:block;color:#5d6678;font-size:11px;margin-top:3px}
.tx{color:#e8f5ee}
.tx mark{background:#1d3b2a;color:#8ff0bb;border-radius:3px;padding:0 3px}
.nil{color:#6b7488}
.meta{text-align:right;font-size:11px;color:#6b7488}
.wc{display:block;font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:10.5px;border-radius:999px;padding:1px 7px;margin:2px 0 0 4px;cursor:help}
.tag.f{background:#173a2a;color:#8ff0bb}
.tag.q{background:#4a3a1d;color:#ffd08a}
.tag.e{background:#3a1d22;color:#ff9c9c}
.tag.s{background:#2a2f3d;color:#a8b4cc}
.hide{display:none}
.note{background:#151a24;border:1px solid #232733;border-radius:10px;padding:13px 15px;
margin-bottom:14px;font-size:12.8px;color:#aab3c4}
.note b{color:#e6e8ec}
.note code{background:#0b0e14;padding:1px 5px;border-radius:4px;color:#8fd0ff}
</style></head><body>
<header>
<h1>训练标注审阅 · Matthew McConaughey《Wonder》(Calm) · 461 切片</h1>
<div class="sub">NVIDIA Parakeet TDT 0.6B v3（DirectML / RX 580）· 点时间码跳转试听 · 绿色高亮 = 已修正</div>
<div class="stats">
<div class="st">切片 <b>__NSL__</b> / 覆盖 <b>__DUR__ min</b></div>
<div class="st">有词 <b>__NOK__</b> · 空片 <b>__NEMP__</b> · 极短 <b>__NSH__</b></div>
<div class="st">总词 <b>__NW__</b> · 中位 <b>__MED__</b> 词/片</div>
<div class="st w">已修正 <b>__NFIX__</b> · 待裁决 <b>__NFLAG__</b></div>
</div>
<audio id="au" controls preload="none" src="__MP3__"></audio>
<div class="filters">
<button class="on" data-f="all">全部</button>
<button data-f="flag">待裁决</button>
<button data-f="fix">已修正</button>
<button data-f="empty">空片</button>
<button data-f="short">极短片</button>
</div>
</header>
<main>
<div class="note">
<b>这一版标注怎么来的：</b>
训练音频 = <code>wonder_train_df3.wav</code>（② DF3 纯降噪），切 <b>461 片 / 26.67 min / 覆盖 99.1%</b>，
完整性校验 10/10 相关系数 = 1.00000。<br>
转写 = <b>NVIDIA Parakeet TDT 0.6B v3</b>（整段 + Silero VAD，跑在 <code>DirectML</code> 上，RX 580 GPU，37× 实时），
输出自带标点与大小写；再按 <b>VAD 段 + 词级时间戳</b>把词挂回切片。<br>
交叉验证 = 与 faster-whisper small.en 整段做<b>全局词级对齐，一致率 94.48%</b>；
large-v3-turbo 只有 <b>16.56%</b>（已废弃）。<br>
<b>定点修正</b> = 8 处（每条都有 small.en 或上下文佐证，鼠标悬停看依据）；
<b>待裁决</b> = 7 处证据不足，留给你判断。
</div>
__ROWS__
</main>
<script>
var au=document.getElementById('au');
document.querySelectorAll('.play').forEach(function(b){
  b.onclick=function(){au.currentTime=parseFloat(b.dataset.t);au.play();};
});
document.querySelectorAll('.filters button').forEach(function(b){
  b.onclick=function(){
    document.querySelectorAll('.filters button').forEach(function(x){x.classList.remove('on');});
    b.classList.add('on'); var f=b.dataset.f;
    document.querySelectorAll('.row').forEach(function(r){
      var show = f==='all'
        || (f==='flag'  && r.dataset.flag==='1')
        || (f==='fix'   && r.dataset.fix==='1')
        || (f==='empty' && r.dataset.empty==='1')
        || (f==='short' && r.dataset.short==='1');
      r.classList.toggle('hide', !show);
    });
  };
});
</script></body></html>"""

import statistics
med = int(statistics.median([r["n"] for r in rows if r["n"] > 0]))
out = (HTML.replace("__NSL__", str(len(rows)))
       .replace("__DUR__", "%.1f" % (tot_dur / 60))
       .replace("__NOK__", str(len(rows) - n_empty))
       .replace("__NEMP__", str(n_empty))
       .replace("__NSH__", str(n_short))
       .replace("__NW__", str(tot_w))
       .replace("__MED__", str(med))
       .replace("__NFIX__", str(n_fix))
       .replace("__NFLAG__", str(n_flag))
       .replace("__MP3__", MP3)
       .replace("__ROWS__", "\n".join(body)))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write(out)
print("切片 %d | 覆盖 %.1f min | 有词 %d | 空 %d | 极短 %d | 总词 %d | 修正 %d | 待裁决 %d"
      % (len(rows), tot_dur / 60, len(rows) - n_empty, n_empty, n_short, tot_w, n_fix, n_flag))
print("写出", OUT)
