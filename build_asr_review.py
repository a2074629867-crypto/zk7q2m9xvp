# -*- coding: utf-8 -*-
"""三方 ASR 对照审阅页 v2 —— 用全局词级对齐（准）

输出: reader/_voice_lab/review_asr.html
"""
import html
import json
import os
import re
import difflib

D = "G:/GPT-SoVITS/_dataset_v5full"
OUT = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_voice_lab/review_asr.html"
MP3 = "wonder_review.mp3"

HALL = ["to be continued", "the dark", "thank you", "subscribe", "subtitle", "amara",
        "www.", ".com", "bye bye", "unlocking the clothes", "so sleepy and i'm so",
        "i'll see you in the next video", "scratching my head", "the night", "of the day"]


def norm(w):
    w = w.lower().replace("\u2019", "'")
    return re.sub(r"[^a-z0-9']", "", w)


PKSEG = json.load(open(D + "/wonder_parakeet.json", encoding="utf-8"))["segments"]
SESEG = [s for s in json.load(open(D + "/asr_full.json", encoding="utf-8"))["segments"]
         if s.get("start") is not None]
TBW = json.load(open(D + "/v2_turbo.json", encoding="utf-8"))


def spread(text, a, b):
    """把段内词按序均匀铺开 → [(word, t)]"""
    ws = text.split()
    if not ws:
        return []
    step = (b - a) / len(ws)
    return [(w, a + step * (i + 0.5)) for i, w in enumerate(ws)]


# 全量词流（带时间）
pk_words, pk_seg_of = [], []
for si, s in enumerate(PKSEG):
    for w, t in spread(s["text"], s["start"], s["end"]):
        pk_words.append(w)
        pk_seg_of.append(si)

se_words, se_t = [], []
for s in SESEG:
    for w, t in spread(s.get("text", ""), s["start"], s["end"]):
        se_words.append(w)
        se_t.append(t)

tb_words, tb_t = [], []
for s in TBW.get("slices", []):
    for a, b, w in (s.get("words") or []):
        tb_words.append(w)
        tb_t.append(float(a))

npk = [norm(w) for w in pk_words]
nse = [norm(w) for w in se_words]
ntb = [norm(w) for w in tb_words]

# --- 全局对齐 PK ↔ SE ---
sm1 = difflib.SequenceMatcher(None, npk, nse, autojunk=False)
pk_ok = [False] * len(npk)
for blk in sm1.get_matching_blocks():
    for k in range(blk.size):
        pk_ok[blk.a + k] = True

# --- 全局对齐 SE ↔ TB ---
sm2 = difflib.SequenceMatcher(None, nse, ntb, autojunk=False)
se_ok = [False] * len(nse)
for blk in sm2.get_matching_blocks():
    for k in range(blk.size):
        se_ok[blk.a + k] = True

tot_match = sum(pk_ok)
print("PK 词 %d | SE 词 %d | TB 词 %d" % (len(npk), len(nse), len(ntb)))
print("全局词级一致: PK↔SE %d (%.2f%% of SE)" % (tot_match, 100 * tot_match / max(1, len(nse))))
print("全局词级一致: SE↔TB %d (%.2f%% of SE)" % (sum(se_ok), 100 * sum(se_ok) / max(1, len(nse))))

# turbo 污染窗（幻觉短语 or 3-gram 重复）
POLLUTED_WINS = []
for w in TBW["windows"]:
    low = (w.get("text") or "").lower()
    toks = [x for x in (norm(t) for t in low.split()) if x]
    rep = any(toks[k:k + 3] == toks[k + 3:k + 6] for k in range(max(0, len(toks) - 5)))
    if any(h in low for h in HALL) or rep:
        POLLUTED_WINS.append(w)
print("turbo 污染窗 %d / %d" % (len(POLLUTED_WINS), len(TBW["windows"])))

# 每段统计
seg_pk = [[] for _ in PKSEG]
for j, w in enumerate(pk_words):
    seg_pk[pk_seg_of[j]].append((w, pk_ok[j]))

rows = []
for si, s in enumerate(PKSEG):
    a, b = s["start"], s["end"]
    items = seg_pk[si]
    n = len(items)
    m = sum(1 for _, ok in items if ok)
    se_here = [(w, ok) for w, t, ok in zip(se_words, se_t, se_ok) if a <= t < b]
    se_txt = " ".join(w for w, _ in se_here)
    # turbo 在该段内的实际输出（词级时间戳）
    tb_here = [w for w, t in zip(tb_words, tb_t) if a <= t < b]
    tb_txt = " ".join(tb_here)
    mid = (a + b) / 2
    tb_hall = any(w["t0"] <= mid < w["t1"] for w in POLLUTED_WINS)
    rate = m / n if n else 0.0
    # 高亮 PK 里未匹配的词
    parts = []
    for w, ok in items:
        parts.append(html.escape(w) if ok else '<u>%s</u>' % html.escape(w))
    rows.append(dict(
        a=a, b=b, n=n, m=m, rate=rate,
        pk_html=" ".join(parts), se=se_txt, tb=tb_txt[:200],
        tb_hall=tb_hall,
        dis=rate < 0.7, empty=(n == 0)))

n_dis = sum(1 for r in rows if r["dis"])
n_hall = sum(1 for r in rows if r["tb_hall"])
avg = sum(r["rate"] for r in rows) / max(1, len(rows))
n_empty = sum(1 for r in rows if r["empty"])

body = []
for i, r in enumerate(rows):
    cls = "dis" if r["dis"] else ("empty" if r["empty"] else "")
    tag = ""
    if r["dis"]:
        tag += '<span class="tag d">分歧 %.0f%%</span>' % (r["rate"] * 100)
    if r["tb_hall"]:
        tag += '<span class="tag h">turbo 幻觉</span>'
    body.append(
        '<div class="row %s" data-dis="%d" data-hall="%d" data-empty="%d">'
        '<div class="tm"><button class="play" data-t="%.2f">%d:%04.1f</button>'
        '<span class="dur">%.1fs · %d词</span></div>'
        '<div class="txt">'
        '<div class="ln pk"><span class="lb">Parakeet</span><span>%s</span>'
        '<span class="sc">%.0f%%</span></div>'
        '<div class="ln se"><span class="lb">small.en</span><span>%s</span></div>'
        '</div><div class="mk">%s</div></div>'
        % (cls, 1 if r["dis"] else 0, 1 if r["tb_hall"] else 0, 1 if r["empty"] else 0,
           r["a"], int(r["a"] // 60), r["a"] % 60, r["b"] - r["a"], r["n"],
           r["pk_html"], r["rate"] * 100, html.escape(r["se"]), tag))

HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASR 三方对照 · Wonder (Calm)</title>
<style>
*{box-sizing:border-box}
body{margin:0;font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
background:#0f1115;color:#e6e8ec}
header{padding:18px 24px 12px;border-bottom:1px solid #232733;position:sticky;top:0;background:#0f1115;z-index:10}
h1{margin:0 0 5px;font-size:16.5px;font-weight:600}
.sub{color:#8b93a5;font-size:12.5px}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin:11px 0 9px;font-size:12.5px}
.st{background:#171a22;border:1px solid #232733;border-radius:8px;padding:5px 11px}
.st b{color:#5ee0a0;font-weight:600}
.st.w b{color:#ff8b8b}
audio{width:100%;height:32px;margin-top:6px}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}
.filters button{background:#171a22;border:1px solid #2b3040;color:#c8cede;border-radius:999px;
padding:4px 12px;font-size:12.5px;cursor:pointer}
.filters button.on{background:#2b6cb0;border-color:#3b82d6;color:#fff}
main{padding:12px 24px 70px}
.row{display:grid;grid-template-columns:100px 1fr 160px;gap:14px;padding:10px 12px;
border-bottom:1px solid #1b1f29;border-radius:8px}
.row:hover{background:#141821}
.row.dis{background:#1d1a12}
.row.empty{opacity:.5}
.tm{font-variant-numeric:tabular-nums}
.play{background:#1e2531;border:1px solid #2f3748;color:#7fb0ff;border-radius:6px;padding:3px 8px;
font-size:12px;cursor:pointer;font-variant-numeric:tabular-nums}
.play:hover{background:#26314a}
.dur{display:block;color:#5d6678;font-size:11px;margin-top:3px}
.ln{display:grid;grid-template-columns:74px 1fr auto;gap:10px;margin-bottom:2px}
.lb{font-size:11px;color:#6b7488;padding-top:2px}
.ln.pk span:nth-child(2){color:#e8f5ee}
.ln.pk u{text-decoration:none;background:#4a2a1d;color:#ffc08a;border-radius:3px;padding:0 2px}
.ln.se span:nth-child(2){color:#93a0b5}
.sc{font-size:11px;color:#5ee0a0}
.tag{display:inline-block;font-size:11px;border-radius:999px;padding:2px 8px;margin-right:5px}
.tag.h{background:#4a1d22;color:#ff9c9c}
.tag.d{background:#4a3a1d;color:#ffd08a}
.hide{display:none}
.note{background:#151a24;border:1px solid #232733;border-radius:10px;padding:13px 15px;
margin-bottom:14px;font-size:12.8px;color:#aab3c4}
.note b{color:#e6e8ec}
.note code{background:#0b0e14;padding:1px 5px;border-radius:4px;color:#8fd0ff}
</style></head><body>
<header>
<h1>ASR 三方对照 · Matthew McConaughey《Wonder》(Calm) · 26:55</h1>
<div class="sub">__NSEG__ 个 VAD 段 · 点时间码跳转试听 · <u style="color:#ffc08a;text-decoration:none">橙色下划线</u> = 与 small.en 不一致的词</div>
<div class="stats">
<div class="st">Parakeet ↔ small.en 词级一致率 <b>__AVG__%</b></div>
<div class="st">分歧段（&lt;70%）<b>__NDIS__</b></div>
<div class="st w">turbo 幻觉段 <b>__NHALL__</b></div>
<div class="st">空段 <b>__NEMPTY__</b></div>
</div>
<audio id="au" controls preload="none" src="__MP3__"></audio>
<div class="filters">
<button class="on" data-f="all">全部</button>
<button data-f="dis">仅分歧段</button>
<button data-f="hall">仅 turbo 幻觉</button>
<button data-f="clean">仅一致段</button>
</div>
</header>
<main>
<div class="note">
<b>Parakeet</b> = NVIDIA Parakeet TDT 0.6B v3（整段 + Silero VAD），跑在 <code>DirectML / RX 580 GPU</code>，37× 实时，自带标点与大小写 —— 这是拟采用的转写。<br>
<b>small.en</b> = faster-whisper small.en 整段（<code>vad_filter=True</code>），此前当"真值"用，现在降为参考。<br>
<b>turbo</b> = faster-whisper large-v3-turbo 分块 —— 已确认大面积幻觉，只作反面参照，不逐行展示。<br>
一致率 = 全局词级 difflib 对齐后，该段内匹配上的词占比。
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
        || (f==='dis'   && r.dataset.dis==='1')
        || (f==='hall'  && r.dataset.hall==='1')
        || (f==='clean' && r.dataset.dis==='0' && r.dataset.empty==='0');
      r.classList.toggle('hide', !show);
    });
  };
});
</script></body></html>"""

out = (HTML.replace("__NSEG__", str(len(rows)))
       .replace("__AVG__", "%.2f" % (avg * 100))
       .replace("__NDIS__", str(n_dis))
       .replace("__NHALL__", str(n_hall))
       .replace("__NEMPTY__", str(n_empty))
       .replace("__MP3__", MP3)
       .replace("__ROWS__", "\n".join(body)))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write(out)
print("段 %d | 平均一致率 %.2f%% | 分歧 %d | turbo幻觉 %d | 空段 %d"
      % (len(rows), avg * 100, n_dis, n_hall, n_empty))
print("写出", OUT)
