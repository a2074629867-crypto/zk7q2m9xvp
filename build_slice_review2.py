# -*- coding: utf-8 -*-
"""训练前标注审阅页 v2（切片级）—— Parakeet TDT v3 长上下文分块 + 人工修正

数据源: G:/GPT-SoVITS/_dataset_v5full/wonder_hp.json
输出:   reader/_voice_lab/review_slices.html
"""
import html
import json
import os
import statistics

D = "G:/GPT-SoVITS/_dataset_v5full"
OUT = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_voice_lab/review_slices.html"
MP3 = "wonder_review.mp3"

SL = json.load(open(D + "/wonder_hp.json", encoding="utf-8"))["slices"]

# 已修正的片（t0 -> 说明）—— 与 apply_fixes.py 的 FIXES 对应
FIXED = {
    1590.19: "So he drifts off → Zoe drifted off；并合并了被切碎的切片（sleeps 原跨边界）",
    1465.30: "So he closed her eyes → Zoe closed her eyes（small.en 佐证）",
    60.46: "thumbtags → thumbtacks（small.en 佐证）",
    1246.41: "thousand of → thousands of（small.en 佐证）",
    360.66: "so explained → Zoe explained（small.en 佐证）",
    50.92: "Stock of prize → A stock of prized（small.en 佐证）",
    408.26: "Grandma said, staring off the stars → Grandpa said, staring off at the stars（small.en 佐证）",
    358.09: "补回句首 As",
}

rows = []
for s in SL:
    txt = s["text"]
    fix = None
    for t0, why in FIXED.items():
        if abs(s["t0"] - t0) < 0.05:
            fix = why
            break
    rows.append(dict(f=s["file"], t0=s["t0"], t1=s["t1"], txt=txt,
                     n=len(txt.split()), dur=s["t1"] - s["t0"], fix=fix))
rows.sort(key=lambda r: r["t0"])

tot_dur = sum(r["dur"] for r in rows)
tot_w = sum(r["n"] for r in rows)
n_empty = sum(1 for r in rows if r["n"] == 0)
n_short = sum(1 for r in rows if 0 < r["n"] < 3)
n_fix = sum(1 for r in rows if r["fix"])
med = int(statistics.median([r["n"] for r in rows if r["n"] > 0]))

body = []
for r in rows:
    cls = []
    if r["n"] == 0:
        cls.append("empty")
    elif r["n"] < 3:
        cls.append("short")
    if r["fix"]:
        cls.append("fixed")
    txt = html.escape(r["txt"]) or '<span class="nil">（空片 · 无文本）</span>'
    if r["fix"]:
        txt = '<mark title="%s">%s</mark>' % (html.escape(r["fix"]), txt)
    tags = ""
    if r["fix"]:
        tags += '<span class="tag f" title="%s">已修正</span>' % html.escape(r["fix"])
    if r["n"] == 0:
        tags += '<span class="tag e">空片</span>'
    elif r["n"] < 3:
        tags += '<span class="tag s">极短</span>'
    body.append(
        '<div class="row %s" data-empty="%d" data-short="%d" data-fix="%d">'
        '<div class="tm"><button class="play" data-t="%.2f">%d:%04.1f</button>'
        '<span class="dur">%.1fs</span></div>'
        '<div class="tx">%s</div>'
        '<div class="meta"><span class="wc">%d 词</span>%s</div></div>'
        % (" ".join(cls), 1 if r["n"] == 0 else 0, 1 if 0 < r["n"] < 3 else 0,
           1 if r["fix"] else 0,
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
.row.fixed{background:#121d17}
.tm{font-variant-numeric:tabular-nums}
.play{background:#1e2531;border:1px solid #2f3748;color:#7fb0ff;border-radius:6px;padding:3px 8px;
font-size:12px;cursor:pointer;font-variant-numeric:tabular-nums}
.play:hover{background:#26314a}
.dur{display:block;color:#5d6678;font-size:11px;margin-top:3px}
.tx{color:#e8f5ee}
.tx mark{background:transparent;color:#8ff0bb;border-bottom:1px dashed #2f6b4c;border-radius:3px;padding:0 2px}
.nil{color:#6b7488}
.meta{text-align:right;font-size:11px;color:#6b7488}
.wc{display:block;font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:10.5px;border-radius:999px;padding:1px 7px;margin:2px 0 0 4px;cursor:help}
.tag.f{background:#173a2a;color:#8ff0bb}
.tag.e{background:#3a1d22;color:#ff9c9c}
.tag.s{background:#2a2f3d;color:#a8b4cc}
.hide{display:none}
.note{background:#151a24;border:1px solid #232733;border-radius:10px;padding:13px 15px;
margin-bottom:14px;font-size:12.8px;color:#aab3c4}
.note b{color:#e6e8ec}
.note code{background:#0b0e14;padding:1px 5px;border-radius:4px;color:#8fd0ff}
</style></head><body>
<header>
<h1>训练标注审阅 · Matthew McConaughey《Wonder》(Calm) · __NSL__ 切片</h1>
<div class="sub">NVIDIA Parakeet TDT 0.6B v3（DirectML / RX 580，37× 实时）· 点时间码跳转试听 · 绿色 = 已修正</div>
<div class="stats">
<div class="st">切片 <b>__NSL__</b> / 覆盖 <b>__DUR__ min</b></div>
<div class="st">有词 <b>__NOK__</b> · 空片 <b>__NEMP__</b> · 极短 <b>__NSH__</b></div>
<div class="st">总词 <b>__NW__</b> · 中位 <b>__MED__</b> 词/片</div>
<div class="st w">已修正 <b>__NFIX__</b></div>
</div>
<audio id="au" controls preload="none" src="__MP3__"></audio>
<div class="filters">
<button class="on" data-f="all">全部</button>
<button data-f="fix">已修正</button>
<button data-f="short">极短片</button>
</div>
</header>
<main>
<div class="note">
<b>这一版标注怎么来的（相对上一版的三处改进）：</b><br>
① <b>换转写引擎</b>：faster-whisper large-v3-turbo 在 McConaughey 这段气声朗读上<b>大面积幻觉</b>
（67 窗中 27 窗污染、<code>unlocking the clothes</code> 重复 109 次），已弃用；
改用 <b>NVIDIA Parakeet TDT 0.6B v3</b>，输出自带标点与大小写。<br>
② <b>换切块策略</b>（关键）：实测无 VAD 直接喂 <b>14s 会丢词</b>、<b>120s 会在低能量段整段跳过</b>
（1196.5–1212.9s 曾丢 16 秒）、<b>VAD 逐段喂会退化</b>（<code>sleeps→sleep</code>、<code>of dreams→A dream</code>）。
最终用 <b>VAD 段边界合并成 ≤28s 的块</b>——块边界落在真实停顿上，块内不加 VAD 直接转写 ⇒
<b>460 片全部有词、0 空片</b>。<br>
③ <b>音频源</b>：ASR 跑在<b>原始音频</b>上（不是 DF3 降噪版）—— DF3 把停顿清成数字零（−85dB），
Parakeet 会截断（whisper 则是直接编造）。词时间戳照旧映射到 DF3 切片。<br><br>
<b>已修正 __NFIX__ 处</b>（每条都有 small.en 或上下文佐证，鼠标悬停看依据）；
另合并了 1 处<b>被切片边界切碎的词</b>：<code>sleeps</code> 原跨 1593.11 边界被切成两半，已把两片合并为 4.11s。
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
        || (f==='fix'   && r.dataset.fix==='1')
        || (f==='short' && r.dataset.short==='1');
      r.classList.toggle('hide', !show);
    });
  };
});
</script></body></html>"""

out = (HTML.replace("__NSL__", str(len(rows)))
       .replace("__DUR__", "%.1f" % (tot_dur / 60))
       .replace("__NOK__", str(len(rows) - n_empty))
       .replace("__NEMP__", str(n_empty))
       .replace("__NSH__", str(n_short))
       .replace("__NW__", str(tot_w))
       .replace("__MED__", str(med))
       .replace("__NFIX__", str(n_fix))
       .replace("__MP3__", MP3)
       .replace("__ROWS__", "\n".join(body)))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write(out)
print("切片 %d | 覆盖 %.1f min | 有词 %d | 空 %d | 极短 %d | 总词 %d | 修正 %d"
      % (len(rows), tot_dur / 60, len(rows) - n_empty, n_empty, n_short, tot_w, n_fix))
print("写出", OUT)
