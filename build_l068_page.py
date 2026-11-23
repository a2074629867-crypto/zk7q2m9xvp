# -*- coding: utf-8 -*-
"""L068 逐段音色修复对照页"""
import base64, os

def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()

ROWS = [
    ("旧版 · 第二句跳 59Hz", "ch123_pre_l53/L068_old.wav",
     "p0 F0 206Hz → p1 F0 265Hz。整条声纹 0.83 很高，但音高突变 —— 你听到的「怪物」是音高跳，不是音色变。"),
    ("A · s44 只降速（推荐）", "_l068try/L068_s44_only.wav",
     "p0 270 / p1 265，跨度只有 5Hz。段间声纹 0.708、锚点 0.743、ASR 全对、253wpm。"),
    ("B · s44 再降 2 半音", "_l068try/L068_s44_p2.wav",
     "p0 241 / p1 251，音高落回 Charles 正常区，但共振峰跟着降 ⇒ 声纹掉到 0.517。"),
]

cards = []
for title, path, desc in ROWS:
    if not os.path.exists(path):
        continue
    cards.append("""
<div class="card">
  <div class="t">%s</div>
  <div class="d">%s</div>
  <audio controls preload="none" src="%s"></audio>
</div>""" % (title, desc, b64(path)))

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>L068 逐段音色</title>
<style>
body{margin:0;padding:28px 20px;background:#14161a;color:#e6e8ec;
     font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:19px;margin:0 0 6px}
.sub{color:#8b93a1;font-size:13px;margin-bottom:22px}
.card{background:#1c1f25;border:1px solid #2a2f38;border-radius:10px;
      padding:14px 16px;margin-bottom:12px}
.t{font-weight:600;color:#8fd3ff;margin-bottom:4px}
.d{color:#8b93a1;font-size:13px;margin-bottom:10px}
audio{width:100%;height:34px}
</style></head><body>
<h1>L068　Well, my mother can't afford to buy us a house, can she? We can't help that.</h1>
<div class="sub">逐段测出来的真因：不是音色变了，是<b>第二句音高跳了 59Hz</b>。</div>
__CARDS__
</body></html>"""

open("castle_l068.html", "w", encoding="utf-8").write(html.replace("__CARDS__", "".join(cards)))
print("ok", os.path.getsize("castle_l068.html"))
