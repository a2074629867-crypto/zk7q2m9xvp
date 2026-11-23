# -*- coding: utf-8 -*-
"""L078「No. But...」拖音三版对照页"""
import base64, os

def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()

ROWS = [
    ("旧版（But 0.23s，没拖）", "ch123/L078.wav", "剪贴拼接，But 只有 0.23s，省略号完全没体现"),
    ("电音版（OLA 拉伸，作废）", "_l078_A.wav", "OLA 拉 2.65 倍：F0 抖动 4.0%→49.4%，就是你说的电音"),
    ("定版 · rubberband 只拉元音", "_l078_A2.wav", "元音 0.132→0.264s，HNR 6.0→6.1dB、抖动 4.0→4.5%，But 总 0.36s"),
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
<title>L078 But 拖音</title>
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
<h1>L078　No. But...</h1>
<div class="sub">只拉元音 /ʌ/（0.13s），/b/ 和 /t/ 保持原速 —— 这才是自然拖音，不是整段慢放。</div>
__CARDS__
</body></html>"""

open("castle_l078.html", "w", encoding="utf-8").write(html.replace("__CARDS__", "".join(cards)))
print("ok", os.path.getsize("castle_l078.html"))
