# -*- coding: utf-8 -*-
"""语速统一对照页：原速 vs 统一后。"""
import base64
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import soundfile as sf

import ch123_rebuild as RB
from ch123_plan import INNER, PLAN

FF = "E:/tool/oopz/ffmpeg.exe"
TMP = "G:/_setup/_mp3rate"
OUT = "G:/_setup/castle_rate.html"
os.makedirs(TMP, exist_ok=True)

TARGET = {"C": 205, "E": 220}
NAME = {"C": "Charles", "E": "Hooper"}

WORDS = {"L%03d" % i: len(t.split()) for i, _, _, t in PLAN}
TEXT = {"L%03d" % i: t for i, _, _, t in PLAN}
WHO = {"L%03d" % i: w for i, w, _, _ in PLAN}
for i, (tag, w, e, t) in enumerate(INNER):
    WORDS["I%02d" % i] = len(t.split())
    TEXT["I%02d" % i] = t
    WHO["I%02d" % i] = w


def mp3(p):
    m = os.path.join(TMP, os.path.basename(p) + ".mp3")
    if not os.path.exists(m):
        subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                        "-codec:a", "libmp3lame", "-b:a", "80k", "-ar", "22050", "-ac", "1", m],
                       capture_output=True)
    with open(m, "rb") as f:
        return base64.b64encode(f.read()).decode()


def rate(p, n):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(1)
    segs = RB.split_at_silence(a, sr, min_gap=0.22)
    v = sum(b - c for c, b in segs)
    return (n / v * 60 if v else 0), len(a) / sr


rows = []
for k in sorted(WORDS):
    p0, p1 = "G:/_setup/ch123/%s.wav" % k, "G:/_setup/ch123_rate/%s.wav" % k
    if not (os.path.exists(p0) and os.path.exists(p1)):
        continue
    n = WORDS[k]
    r0, d0 = rate(p0, n)
    r1, d1 = rate(p1, n)
    rows.append((k, WHO[k], r0, r1, d0, d1, mp3(p1)))

order = {"C": 0, "E": 1}
rows.sort(key=lambda r: (r[1], r[0]))

body = []
for k, who, r0, r1, d0, d1, b64 in rows:
    delta = r1 - r0
    cls = "same" if abs(delta) < 4 else ("down" if delta < 0 else "up")
    body.append("""
    <tr class="%s">
      <td class="k">%s</td>
      <td class="w">%s</td>
      <td class="t">%s</td>
      <td class="n">%d → <b>%d</b></td>
      <td class="d">%.2f → %.2fs</td>
      <td><audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></td>
    </tr>""" % (cls, k, NAME[who], TEXT[k], round(r0), round(r1), d0, d1, b64))

HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>语速统一对照</title>
<style>
:root{--bg:#0f1115;--fg:#e8ecf1;--dim:#8b96a5;--line:#252b35}
*{box-sizing:border-box}
body{margin:0;padding:26px 18px 60px;background:var(--bg);color:var(--fg);
 font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:19px;margin:0 0 4px}
.sub{color:var(--dim);font-size:12.5px;margin-bottom:18px;line-height:1.7}
.sum{display:flex;gap:26px;flex-wrap:wrap;margin:14px 0 20px}
.card{background:#171b22;border:1px solid var(--line);border-radius:9px;padding:12px 16px;min-width:190px}
.card .h{font-size:12px;color:var(--dim)}
.card .v{font-size:19px;font-weight:600;margin-top:3px}
.card .s{font-size:11.5px;color:var(--dim);margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;color:var(--dim);font-weight:500;padding:7px 8px;border-bottom:1px solid var(--line);font-size:11.5px}
td{padding:6px 8px;border-bottom:1px solid #1b2027;vertical-align:middle}
td.k{font-variant-numeric:tabular-nums;color:var(--dim)}
td.n{font-variant-numeric:tabular-nums;white-space:nowrap}
td.n b{color:#5eead4}
td.d{color:var(--dim);font-variant-numeric:tabular-nums;white-space:nowrap}
td.t{color:#aab4c2;max-width:430px}
audio{width:210px;height:30px}
tr.down td.n b{color:#5eead4}
tr.up td.n b{color:#fbbf24}
tr.same td.n b{color:var(--dim)}
.w{color:#7c8899;font-size:11.5px}
</style></head><body>
<h1>语速统一 · 按发音时长计</h1>
<div class="sub">
刻度用 <b>voiced wpm</b>＝词数 ÷ 语音段总时长，间隔全部排除。<br>
做法：把每条按静音切段，只对各语音段做 rubberband 保音高变速（音高、共振峰不动），段间静音原样保留。<br>
目标按角色分：Charles 205 / Hooper 220；拉伸范围 0.66–1.30。<br>
<b>例外：L084</b> 拉伸后 "I said" 必糊（0.70/0.74/0.78 全档 ASR 都错），保持原速。
</div>
<div class="sum">
  <div class="card"><div class="h">Charles</div><div class="v">168 – 265</div><div class="s">原 130–375（跨度 245）→ 跨度 97</div></div>
  <div class="card"><div class="h">Hooper</div><div class="v">209 – 251</div><div class="s">原 168–353（跨度 185）→ 跨度 42</div></div>
  <div class="card"><div class="h">全库中位</div><div class="v">213 wpm</div><div class="s">改动前 255 wpm</div></div>
</div>
<table>
<tr><th>条</th><th>角色</th><th>台词</th><th>语速（原 → 新）</th><th>时长</th><th>试听（统一后）</th></tr>
__BODY__
</table>
</body></html>"""

HTML = HTML.replace("__BODY__", "".join(body))
open(OUT, "w", encoding="utf-8").write(HTML)
print("OK", OUT, round(os.path.getsize(OUT) / 1e6, 2), "MB", len(rows), "条")
