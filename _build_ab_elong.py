# -*- coding: utf-8 -*-
"""_build_ab_elong.py —— 省略号/破折号「拖音」A/B 审听页。

左：现役（原样）  右：拖长版（只拉元音、辅音原速）
每条标注：倍率、元音原/新时长、是否句末，以及是否超过 1.55 的「偏重」线。
"""
import base64
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from _rate import rate  # noqa: E402

ELONG = "G:/_setup/_elong"
rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
log = json.load(open(os.path.join(ELONG, "_elong_log.json"), encoding="utf-8"))


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


def info(p, text):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    r = rate(p, text) if text else {}
    return "%.2fs · %s wpm · peak %.2f" % (
        len(y) / sr, r.get("wpm", "-"), float(np.abs(y).max()))


HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>省略号拖音 A/B</title>
<style>
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#14171a;color:#e6e8ea;margin:0;padding:22px;max-width:1000px}
h1{font-size:19px;margin:0 0 4px}
.sub{color:#9aa3ad;font-size:13px;line-height:1.7;margin-bottom:18px}
.card{background:#1b1f23;border:1px solid #2b3036;border-radius:10px;padding:14px 16px;margin-bottom:14px}
.hd{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:4px}
.id{font-family:ui-monospace,monospace;font-weight:600;font-size:14px;color:#79c0ff}
.who{color:#e3b341;background:#2d2413;border-radius:4px;padding:1px 7px;font-size:12px}
.ratio{font-size:12px;border-radius:4px;padding:1px 7px}
.ok{background:#132d1c;color:#56d364}
.hot{background:#3a1a1a;color:#ff7b72}
.txt{color:#b9c0c8;font-size:13px;line-height:1.6;margin:5px 0 12px;padding-left:10px;border-left:3px solid #2b3036}
.row{display:flex;align-items:center;gap:10px;margin:7px 0;flex-wrap:wrap}
.lbl{width:168px;font-size:13px;color:#d5d9dd}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:6px 14px;font-size:13px;cursor:pointer;min-width:62px}
.btn:hover{background:#388bfd}
.btn.on{background:#da3633}
.mono{font-family:ui-monospace,monospace;font-size:12px;color:#8b949e}
</style></head><body>
<h1>省略号 / 破折号「自然拖音」A/B</h1>
<div class="sub">做法：只拉元音段（rubberband 保音高），辅音原速，末尾渐弱；句中标记后过长的死寂收到 0.6s。<br>
倍率 &gt;1.55 标红 = 按 10-20 的教训属「偏重」，容易被听出；≤1.4 才有把握听不出。</div>
__CARDS__
__JS__
</body></html>"""

CARD = """<div class="card">
<div class="hd"><span class="id">__ID__</span><span class="who">__WHO__</span>
<span class="ratio __CLS__">__RATIO__</span><span class="mono">__NOTE__</span></div>
<div class="txt">__TEXT__</div>
__ROWS__
</div>"""

ROW = """<div class="row"><div class="lbl">__LBL__</div>
<button class="btn" data-src="__SRC__">▶ 播放</button>
<span class="mono">__INFO__</span></div>"""

JS = """<script>
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
</script>"""


def main():
    cards = []
    items = []
    for rid, v in log.items():
        e = os.path.join(ELONG, "%s_elong.wav" % rid)
        if not os.path.exists(e):
            continue
        items.append((v["new_ms"] / max(1.0, v["vowel_ms"]), rid, v, e))
    items.sort(key=lambda x: x[0])          # 轻轻的排前面

    for ratio, rid, v, e in items:
        text = rows[rid]["text"]
        cls = "hot" if ratio > 1.55 else "ok"
        note = ("句末渐弱" if v.get("at_end") else
                ("停顿 %.2fs" % v["gap_before"] if v.get("gap_before") else "不变停顿"))
        rs = []
        for lbl, p in [("现役（原样）", "G:/_setup/_audio_ch123/out/%s.wav" % rid),
                       ("拖长版", e)]:
            if not os.path.exists(p):
                continue
            rs.append(ROW.replace("__LBL__", lbl).replace("__SRC__", b64(p))
                      .replace("__INFO__", info(p, text)))
        cards.append(CARD.replace("__ID__", rid)
                     .replace("__WHO__", "%s · %s" % (v.get("who", ""), v.get("word", "")))
                     .replace("__CLS__", cls)
                     .replace("__RATIO__", "元音 %d→%dms · x%.2f"
                              % (v["vowel_ms"], v["new_ms"], ratio))
                     .replace("__NOTE__", note)
                     .replace("__TEXT__", text).replace("__ROWS__", "\n".join(rs)))

    out = "G:/_setup/_ab_elong.html"
    open(out, "w", encoding="utf-8").write(
        HTML.replace("__CARDS__", "\n".join(cards)).replace("__JS__", JS))
    print("%s  %d 条  %.2f MB" % (out, len(cards), os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
