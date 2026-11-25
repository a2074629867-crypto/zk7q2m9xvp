# -*- coding: utf-8 -*-
"""_build_ab_native.py —— 「原生生成 vs 后处理」对比页。

四列同一句：
  ① 现役成品（think 140ms）
  ② 原生 seed44（think 400ms，模型自己生成，零后处理）
  ③ 原生 seed45（think 360ms）
  ④ 后处理轻拉（think 168ms，rubberband 只拉元音）
"""
import base64
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")

ID = "c2_0368"
TEXT = "I think... I don't know. I think it's free."


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


def m(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    f = f[f > 0]
    return "总 %.2fs · F0 %d · peak %.2f" % (
        len(y) / sr, int(np.median(f)) if len(f) else 0, float(np.abs(y).max()))


VERS = [
    ("现役成品（think 140ms）", "G:/_setup/_audio_ch123/out/c2_0368.wav", "#8b949e"),
    ("★ 原生 seed44（think 400ms，零后处理）", "G:/_setup/_seedpick/c2_0368/s44.wav", "#56d364"),
    ("原生 seed45（think 360ms）", "G:/_setup/_seedpick/c2_0368/s45.wav", "#56d364"),
    ("后处理轻拉（think 168ms）", "G:/_setup/_elong/c2_0368_elong.wav", "#e3b341"),
]

HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>延长：原生 vs 后处理</title>
<style>
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#14171a;color:#e6e8ea;margin:0;padding:26px;max-width:900px}
h1{font-size:19px;margin:0 0 6px}
.sub{color:#9aa3ad;font-size:13px;line-height:1.75;margin-bottom:20px}
.txt{color:#d5d9dd;font-size:16px;line-height:1.7;padding:12px 16px;background:#1b1f23;border-left:3px solid #2b3036;border-radius:0 6px 6px 0;margin-bottom:20px}
.row{display:flex;align-items:center;gap:12px;margin:10px 0;padding:10px 12px;background:#1b1f23;border:1px solid #2b3036;border-radius:8px}
.lbl{flex:1;font-size:14px}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:7px 16px;font-size:13px;cursor:pointer;min-width:66px}
.btn:hover{background:#388bfd}
.btn.on{background:#da3633}
.mono{font-family:ui-monospace,monospace;font-size:12px;color:#8b949e;min-width:210px;text-align:right}
</style></head><body>
<h1>c2_0368 省略号延长：原生生成 vs 后处理</h1>
<div class="sub">同一文本、同一参考（Charles_soft）、同一参数，唯一变量是 seed。<br>
「原生」= 模型自己把 think 生成得更长，音频未做任何处理；「后处理」= 生成的短 take 再用 rubberband 只拉元音。</div>
<div class="txt">‘I think... I don't know. I think it's free.’</div>
__ROWS__
<script>
let cur=null;
document.querySelectorAll('.btn').forEach(b=>{
  b.onclick=()=>{
    if(cur){cur.pause();cur=null;}
    document.querySelectorAll('.btn').forEach(x=>{x.classList.remove('on');x.textContent='▶ 播放';});
    if(b.classList.contains('on')){return;}
    const a=new Audio(b.dataset.src);
    a.play();cur=a;b.classList.add('on');b.textContent='■ 停止';
    a.onended=()=>{b.classList.remove('on');b.textContent='▶ 播放';cur=null;};
  };
});
</script></body></html>"""

ROW = """<div class="row"><div class="lbl" style="color:__C__">__LBL__</div>
<button class="btn" data-src="__SRC__">▶ 播放</button>
<span class="mono">__INFO__</span></div>"""

rows = []
for lbl, p, c in VERS:
    if not os.path.exists(p):
        rows.append('<div class="row"><div class="lbl">%s</div><span class="mono">缺文件</span></div>' % lbl)
        continue
    rows.append(ROW.replace("__LBL__", lbl).replace("__C__", c)
                .replace("__SRC__", b64(p)).replace("__INFO__", m(p)))

out = "G:/_setup/_ab_native_elong.html"
open(out, "w", encoding="utf-8").write(HTML.replace("__ROWS__", "\n".join(rows)))
print("%s  %.2f MB" % (out, os.path.getsize(out) / 1e6))
