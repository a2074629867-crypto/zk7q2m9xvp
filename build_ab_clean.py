# -*- coding: utf-8 -*-
"""A/B 页：v5（慢包络+限幅+降速） vs clean（仅整体增益、原速）。"""
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
TMP = "G:/_setup/_mp3ab"
OUT = "G:/_setup/castle_ab_clean.html"
os.makedirs(TMP, exist_ok=True)

NAME = {"C": "Charles", "E": "Hooper"}
TEXT = {"L%03d" % i: t for i, _, _, t in PLAN}
WHO = {"L%03d" % i: w for i, w, _, _ in PLAN}
for i, (tag, w, e, t) in enumerate(INNER):
    TEXT["I%02d" % i] = t
    WHO["I%02d" % i] = w


def mp3(p):
    m = os.path.join(TMP, os.path.basename(p) + ".mp3")
    if not os.path.exists(m):
        subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                        "-codec:a", "libmp3lame", "-b:a", "96k", "-ar", "24000", "-ac", "1", m],
                       capture_output=True)
    with open(m, "rb") as f:
        return base64.b64encode(f.read()).decode()


def stat(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(1)
    return dict(dur=len(a) / sr, db=RB.rms_voiced_db(a, sr), pk=float(np.abs(a).max()))


# 用户点名的 + 典型长句
ITEMS = [
    ("L088", "He's old, I told you. When he was in the Battle of Britain, he was twenty. That was the war."),
    ("L090", "In Wales."),
    ("L077", "Is it a picture of him in the Battle?"),
    ("L083", "Here's the picture. Look, that's my father."),
    ("L068", "Well, my mother can't afford to buy us a house, can she? We can't help that."),
    ("L078", "No. But..."),
    ("L059", "My grandfather died in this room. Not very long ago, either. He lay and died in that bed. Now it's your bed."),
]

rows = []
for k, txt in ITEMS:
    old = "G:/_setup/ch123_v5/%s.wav" % k
    new = "G:/_setup/ch123_clean/%s.wav" % k
    if not (os.path.exists(old) and os.path.exists(new)):
        continue
    so, sn = stat(old), stat(new)
    rows.append((k, txt, WHO.get(k, ""), so, sn, mp3(old), mp3(new)))

cards = []
for k, txt, who, so, sn, mo, mn in rows:
    cards.append("""
<div class="c">
  <div class="hd"><span class="id">%s</span><span class="who %s">%s</span></div>
  <div class="tx">%s</div>
  <div class="ab">
    <div class="side"><div class="lbl bad">旧 · v5（包络+限幅+降速）</div>
      <div class="m">%.2fs · %.0fdB</div>
      <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>
    <div class="side"><div class="lbl good">新 · clean（仅整体增益，原速）</div>
      <div class="m">%.2fs · %.0fdB</div>
      <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>
  </div>
</div>""" % (k, "c" if who == "C" else "e", NAME.get(who, ""), txt,
             so["dur"], so["db"], mo, sn["dur"], sn["db"], mn))

BODY = "\n".join(cards)

HTML = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A/B · clean vs v5</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--line:#272b35;--tx:#e6e8ee;--dim:#8b93a7;
--red:#e05c5c;--green:#4bbf7a;--blue:#5b9bd5}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:21px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;line-height:1.75;margin-bottom:22px}
.sub b{color:var(--tx)}
.c{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 16px;margin-bottom:14px}
.hd{display:flex;align-items:center;gap:9px;margin-bottom:6px}
.id{font-family:ui-monospace,Consolas,monospace;font-size:13px;color:var(--blue);font-weight:600}
.who{font-size:11px;padding:1px 7px;border-radius:20px;border:1px solid var(--line);color:var(--dim)}
.who.c{color:#e0a35c;border-color:#5a4225}
.who.e{color:#7fb3e0;border-color:#2a4a68}
.tx{color:#c3c9d6;font-size:13.5px;line-height:1.65;margin-bottom:10px}
.ab{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:640px){.ab{grid-template-columns:1fr}}
.side{background:#12151b;border:1px solid var(--line);border-radius:9px;padding:9px 10px}
.lbl{font-size:11.5px;margin-bottom:3px}
.lbl.bad{color:var(--red)}
.lbl.good{color:var(--green)}
.m{font-size:11px;color:var(--dim);font-family:ui-monospace,monospace;margin-bottom:6px}
audio{width:100%;height:32px}
</style></head><body><div class="wrap">
<h1>A/B · clean（只做整体增益） vs v5（三重处理）</h1>
<div class="sub">
旧版链路：<b>句内慢包络 → 不限峰增益 → lookahead 限幅 → rubberband 降速</b>。<br>
新版链路：<b>只做一次整体增益到 −24dBFS</b>，不做包络、不做限幅、<b>不降速</b>。<br>
两边响度一致（都 −24dBFS），差别只在处理痕迹与语速。<br>
重点听：<b>尾音是否还被拖长</b>（L088 / L090）、<b>father 是否还断</b>（L083）、<b>还有没有"炸"</b>。
</div>
__BODY__
</div></body></html>"""

html = HTML.replace("__BODY__", BODY)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("wrote", OUT, "%.2f MB" % (os.path.getsize(OUT) / 1e6), "条", len(rows))
