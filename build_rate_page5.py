# -*- coding: utf-8 -*-
"""语速 v5 对照页：分级目标（短句更慢）+ 只降不升。"""
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
TMP = "G:/_setup/_mp3v5"
OUT = "G:/_setup/castle_rate5.html"
os.makedirs(TMP, exist_ok=True)

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
    p0, p1 = "G:/_setup/ch123/%s.wav" % k, "G:/_setup/ch123_v5/%s.wav" % k
    if not (os.path.exists(p0) and os.path.exists(p1)):
        continue
    n = WORDS[k]
    r0, d0 = rate(p0, n)
    r1, d1 = rate(p1, n)
    rows.append((k, WHO[k], n, r0, r1, d0, d1, mp3(p1)))

rows.sort(key=lambda r: (r[1], r[0]))

body = []
for k, who, n, r0, r1, d0, d1, b64 in rows:
    delta = r1 - r0
    cls = "same" if abs(delta) < 6 else ("down" if delta < 0 else "up")
    short = "short" if n <= 6 else ""
    body.append("""
    <tr class="%s %s">
      <td class="k">%s</td>
      <td class="w">%s</td>
      <td class="nw">%d</td>
      <td class="t">%s</td>
      <td class="n">%d → <b>%d</b></td>
      <td class="d">%.2f → %.2fs</td>
      <td><audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></td>
    </tr>""" % (cls, short, k, NAME[who], n, TEXT[k], round(r0), round(r1), d0, d1, b64))


def rng(who, lo, hi):
    v = [r[4] for r in rows if r[1] == who and lo <= r[2] <= hi]
    d = [r[6] for r in rows if r[1] == who and lo <= r[2] <= hi]
    if not v:
        return "—"
    return "%d–%d wpm" % (min(v), max(v)), "%.2f–%.2fs" % (min(d), max(d))


def card(t, v, s):
    return '<div class="card"><div class="h">%s</div><div class="v">%s</div><div class="s">%s</div></div>' % (t, v, s)


def wr(who):
    v = [r[4] for r in rows if r[1] == who]
    d = [r[6] for r in rows if r[1] == who]
    return ("%d–%d wpm" % (min(v), max(v)), "%.2f–%.2fs" % (min(d), max(d)))

c1v, c1s = wr("C")
e1v, e1s = wr("E")
untouched = sum(1 for r in rows if abs(r[4] - r[3]) < 1.5)
down = sum(1 for r in rows if r[4] < r[3] - 1.5)
HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>语速 v5 · 最多降 30%</title>
<style>
:root{--bg:#0f1115;--fg:#e8ecf1;--dim:#8b96a5;--line:#252b35}
*{box-sizing:border-box}
body{margin:0;padding:26px 18px 60px;background:var(--bg);color:var(--fg);
 font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:19px;margin:0 0 4px}
.sub{color:var(--dim);font-size:12.5px;margin-bottom:18px;line-height:1.75}
.sub b{color:#cbd5e1;font-weight:600}
.sum{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0 22px}
.card{background:#171b22;border:1px solid var(--line);border-radius:9px;padding:11px 15px;min-width:170px}
.card .h{font-size:12px;color:var(--dim)}
.card .v{font-size:18px;font-weight:600;margin-top:3px}
.card .s{font-size:11.5px;color:var(--dim);margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;color:var(--dim);font-weight:500;padding:7px 8px;border-bottom:1px solid var(--line);font-size:11.5px;position:sticky;top:0;background:var(--bg)}
td{padding:6px 8px;border-bottom:1px solid #1b2027;vertical-align:middle}
td.k{font-variant-numeric:tabular-nums;color:var(--dim)}
td.nw{font-variant-numeric:tabular-nums;color:#7c8899;text-align:right}
td.n{font-variant-numeric:tabular-nums;white-space:nowrap}
td.d{color:var(--dim);font-variant-numeric:tabular-nums;white-space:nowrap}
td.t{color:#aab4c2;max-width:400px}
audio{width:196px;height:30px}
tr.down td.n b{color:#5eead4}
tr.up td.n b{color:#fbbf24}
tr.same td.n b{color:var(--dim)}
tr.short td.k{color:#93c5fd}
tr.short{background:#131a24}
.w{color:#7c8899;font-size:11.5px}
.legend{font-size:11.5px;color:var(--dim);margin:0 0 12px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;background:#131a24;border:1px solid #93c5fd;margin:0 4px 0 12px;vertical-align:middle}
</style></head><body>
<h1>语速 v5 · 后期降速，最多到原速 0.7 倍</h1>
<div class="sub">
刻度 <b>voiced wpm</b>＝词数 ÷ 语音段总时长（间隔不计）。<br>
这一版按你的限制重做：<b>任何一条最多只降到原音频的 0.7 倍</b>，原速已经 ≤255wpm 的直接不动。<br>
统一收到 Charles 252 / Hooper 258；<b>只降不升</b>；拉伸后只做整体增益，不再做句内包络。<br>
L090 / L058 / L092 / L078 原速标准的完全没碰。<br><b>L050、L084 已重生成</b>（原速 375 / 353 拉到 0.7 仍不够）；L071、L061 重生成音色不过关（声纹 0.20），保留 0.7 倍版本。</div>
<div class="sum">
  __C1__
  __E1__
  __N1__
  __N2__
</div>
<div class="legend">青色数字 = 降速；灰色 = 原速未动（本来就 ≤255wpm）</div>
<table>
<tr><th>条</th><th>角色</th><th>词</th><th>台词</th><th>voiced wpm（原 → 新）</th><th>时长</th><th>试听（新版）</th></tr>
__BODY__
</table>
</body></html>"""

HTML = (HTML.replace("__C1__", card("Charles", c1v, c1s))
        .replace("__E1__", card("Hooper", e1v, e1s))
        .replace("__N1__", card("降速条数", "%d / %d" % (down, len(rows)), "其余 %d 条原速未动" % untouched))
        .replace("__N2__", card("最大降幅", "30%", "tempo 下限 0.70，硬限制"))
        .replace("__BODY__", "".join(body)))
open(OUT, "w", encoding="utf-8").write(HTML)
print("OK", OUT, round(os.path.getsize(OUT) / 1e6, 2), "MB", len(rows), "条")
