# -*- coding: utf-8 -*-
"""生成 RDR 听感校验页。"""
import json

d = json.load(open("_rdr_gate_ch1.json", encoding="utf-8"))
rows = {r["uid"]: r for r in d["rows"]}
J = [r["uid"] for r in json.load(open("_chap_ch1_v4b.json", encoding="utf-8"))["rows"]]

SEG = [
    ("A", 94, "2.60", "N0163", "N0167", "rdr_A.mp3"),
    ("B", 64, "2.31", "N0111", "N0115", "rdr_B.mp3"),
    ("C", 45, "2.13", "N0058", "N0062", "rdr_C.mp3"),
    ("D", 6,  "1.84", "N0007", "N0010", "rdr_D.mp3"),
    ("E", 44, "1.20", "N0050", "N0053", "rdr_E.mp3"),
]

def bars(uids):
    mx = max(rows[u]["rate_B"] for u in uids if u in rows)
    out = []
    for u in uids:
        if u not in rows:
            continue
        w = rows[u]["w"]; r = rows[u]["rate_B"]
        pct = r / mx * 100
        hot = "hot" if (r > 190 or r < 90) else ""
        out.append(
            f'<div class="ln"><span class="w">{w}w</span>'
            f'<span class="bar"><i class="{hot}" style="width:{pct:.1f}%"></i></span>'
            f'<span class="r">{r:.0f}</span></div>'
            f'<div class="tx">{rows[u]["text"]}</div>')
    return "\n".join(out)

cards = []
for tag, pid, ratio, u0, u1, mp3 in SEG:
    seg = J[J.index(u0):J.index(u1) + 1]
    ctrl = tag == "E"
    cls = "ctrl" if ctrl else "bad"
    head = ("对照 · 段 %d" % pid) if ctrl else ("段 %d" % pid)
    pill = ('<span class="pill ok">最平 1.20×</span>' if ctrl
            else '<span class="pill ng">跳变 %s×</span>' % ratio)
    cards.append(f'''
<section class="card {cls}">
  <div class="hd"><b>{tag}</b><span class="t">{head}</span>{pill}</div>
  <audio controls preload="none" src="{mp3}"></audio>
  <div class="chart">{bars(seg)}</div>
</section>''')

html = f'''<!DOCTYPE html>
<meta charset="utf-8">
<title>语速接缝听感校验 · ch1</title>
<style>
:root{{
  --bg:#f6f7f9; --card:#fff; --line:#e3e6ea; --txt:#1b1f24; --dim:#6b7480;
  --bad:#d94a3d; --ok:#2f9e6e; --bar:#9fb4c7; --bar-hot:#d94a3d;
}}
*{{box-sizing:border-box}}
body{{margin:0;padding:28px 20px 60px;background:var(--bg);color:var(--txt);
  font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
.wrap{{max-width:760px;margin:0 auto}}
h1{{font-size:21px;margin:0 0 6px;letter-spacing:-.2px}}
.sub{{color:var(--dim);font-size:13.5px;margin-bottom:20px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px 12px;margin-bottom:14px}}
.card.bad{{border-left:3px solid var(--bad)}}
.card.ctrl{{border-left:3px solid var(--ok)}}
.hd{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.hd b{{font-size:16px;width:18px}}
.hd .t{{color:var(--dim);font-size:13.5px}}
.pill{{margin-left:auto;font-size:12px;padding:2px 9px;border-radius:99px;font-weight:600}}
.pill.ng{{background:#fdecea;color:var(--bad)}}
.pill.ok{{background:#e8f6ef;color:var(--ok)}}
audio{{width:100%;height:34px;margin-bottom:12px}}
.chart{{font-size:12px}}
.ln{{display:flex;align-items:center;gap:8px;margin-top:7px}}
.ln .w{{width:26px;text-align:right;color:var(--dim);font-variant-numeric:tabular-nums}}
.ln .bar{{flex:1;height:9px;background:#f0f2f5;border-radius:99px;overflow:hidden}}
.ln .bar i{{display:block;height:100%;background:var(--bar);border-radius:99px}}
.ln .bar i.hot{{background:var(--bar-hot)}}
.ln .r{{width:34px;color:var(--dim);font-variant-numeric:tabular-nums}}
.tx{{color:#3d454f;font-size:12.5px;margin:1px 0 6px 42px;line-height:1.45}}
.note{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 18px;
  margin-bottom:16px;font-size:13.5px}}
.note b{{color:var(--txt)}}
.note code{{background:#f0f2f5;padding:1px 5px;border-radius:4px;font-size:12.5px}}
ol{{margin:8px 0 0;padding-left:20px}}
li{{margin:4px 0}}
</style>
<div class="wrap">
<h1>语速接缝听感校验</h1>
<div class="sub">ch1 · 原速不降速 · 只压缩了停顿 · 每段都是整章里的真实片段，不是单独拼的</div>

<div class="note">
  <b>只判断一件事：相邻两句之间，语速接不接得上。</b>不用管音色、内容、停顿长短。
  <ol>
    <li>A～D 是闸门判"超标"的 4 段，E 是全部段落里最平的一段（当对照）</li>
    <li>条形 = 逐句语速，<span style="color:var(--bad);font-weight:600">红色</span>
        表示 &gt;190 或 &lt;90 wpm 的离群句</li>
    <li>要你回答的是：<b>哪几段听着能明显觉出"这句突然快了/慢了"</b></li>
  </ol>
</div>
{"".join(cards)}
<div class="note" style="color:var(--dim)">
  闸门总账：95 个接缝，<b>30 个</b>超 1.5×（32%），涉及 37 组里的 14 组 → RDR 0.378。
  马修母带同一口径下超 1.5× 的比例是 13%。
</div>
</div>
'''
open("_ab/rdr_report.html", "w", encoding="utf-8").write(html)
print("wrote _ab/rdr_report.html")
