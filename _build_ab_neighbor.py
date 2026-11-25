# -*- coding: utf-8 -*-
"""_build_ab_neighbor.py —— 上下文连贯性检查：相邻三句 + 新旧 c3_0853

为什么要单独做一页：s50 是单独听着选的，它在整章语流里会不会「突然变低变沉」，
得和前后句一起听才知道。全部等响（voiced RMS −24dBFS），否则又是音量骗人。
"""
import base64
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _loud  # noqa: E402

OUT = "G:/_setup/_ab_neighbor.html"
OUTD = "G:/_setup/_audio_ch123/out"

ITEMS = [
    ("c3_0851", None, "上一句"),
    ("c3_0853", "G:/_setup/_bak_s50_1125/c3_0853.before.wav", "本条 · 旧（断成两截、cam）"),
    ("c3_0853", None, "本条 · 新（s50，口吃 0.11s）"),
    ("c3_0855", None, "下一句"),
]


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


def med_f0(p):
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    f = f[f > 0]
    return int(np.median(f)) if len(f) else 0


HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>c3_0853 上下文连贯性</title>
<style>
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#14171a;color:#e6e8ea;margin:0;padding:24px;max-width:820px}
h1{font-size:18px;margin:0 0 8px}
.sub{color:#9aa3ad;font-size:13px;line-height:1.8;border-left:3px solid #2b3036;padding-left:12px;margin-bottom:16px}
.card{background:#1b1f23;border:1px solid #2b3036;border-radius:10px;padding:12px 15px;margin:11px 0;display:flex;align-items:center;gap:14px}
.card.new{border-color:#238636}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:6px 14px;font-size:12.5px;cursor:pointer;min-width:62px}
.btn.on{background:#da3633}
.m{font-family:ui-monospace,monospace;font-size:11.5px;color:#9aa3ad}
.l{font-size:13px;color:#c9d1d9;flex:1}
</style></head><body>
<h1>c3_0853 · 放回上下文听</h1>
<div class="sub">全部等响 −24dBFS。重点听<b>音区是否接得上</b>：新条的中位 F0 是 195Hz，
上一句/下一句是 233Hz —— 单独听不出来，连着听能听出「沉下去」。</div>
__CARDS__
<script>
let cur=null;
document.querySelectorAll('.btn').forEach(b=>{b.onclick=()=>{
 if(cur){cur.pause();cur=null;}
 document.querySelectorAll('.btn').forEach(x=>{x.classList.remove('on');x.textContent='▶';});
 if(b.classList.contains('on'))return;
 const a=new Audio(b.dataset.src);a.play();cur=a;b.classList.add('on');b.textContent='■';
 a.onended=()=>{b.classList.remove('on');b.textContent='▶';cur=null;};};});
</script></body></html>
"""


def main():
    cards = []
    for rid, alt, label in ITEMS:
        p = alt or os.path.join(OUTD, "%s.wav" % rid)
        pn, li = _loud.to_uniform(p, "G:/_setup/_pool_norm/neighbor")
        y, sr = sf.read(pn, dtype="float64")
        cls = "card new" if "新" in label else "card"
        cards.append('<div class="%s"><span class="l">%s<br><span class="m">%s · %.2fs · F0 %dHz · %+.1fdB 对齐</span></span>'
                     '<button class="btn" data-src="%s">▶</button></div>'
                     % (cls, label, rid, len(y) / sr, med_f0(pn), li["gain_db"], b64(pn)))
    open(OUT, "w", encoding="utf-8").write(HTML.replace("__CARDS__", "".join(cards)))
    print("->", OUT, "%.2f MB" % (os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    sys.exit(main())
