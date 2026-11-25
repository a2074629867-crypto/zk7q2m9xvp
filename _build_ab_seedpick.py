# -*- coding: utf-8 -*-
"""_build_ab_seedpick.py —— seed 择优批量审听页（每条：现役 + 选中 + 备选）。

读 `_seedpick_summary.json`，为每条 pick 非空（或 --all）的条目渲染一张卡片：
  现役成品（灰）／★ 选中 take（绿）／其余合格候选（蓝）
每行标注目标词时长、相对现役的倍数、总长、F0。
"""
import argparse
import base64
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _loud  # noqa: E402

OUT = "G:/_setup/_ab_seedpick.html"


def nb(p):
    """等响副本（voiced RMS -24 dBFS）—— 同一句的多个 seed 音量本来差很多，
    不拉平的话「哪个更好听」其实是在比音量。"""
    return _loud.to_uniform(p, "G:/_setup/_pool_norm/seedpick")[0]


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


def info(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    f = f[f > 0]
    return "总 %.2fs · F0 %d · peak %.2f" % (
        len(y) / sr, int(np.median(f)) if len(f) else 0, float(np.abs(y).max()))


HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>省略号延长 · seed 择优审听</title>
<style>
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#14171a;color:#e6e8ea;margin:0;padding:24px;max-width:960px}
h1{font-size:19px;margin:0 0 6px}
.sub{color:#9aa3ad;font-size:13px;line-height:1.8;margin-bottom:18px;border-left:3px solid #2b3036;padding-left:12px}
.card{background:#1b1f23;border:1px solid #2b3036;border-radius:10px;padding:14px 16px;margin:16px 0}
.hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:8px}
.id{font-family:ui-monospace,monospace;font-size:13px;color:#58a6ff}
.tag{font-size:12px;color:#9aa3ad}
.txt{color:#d5d9dd;font-size:15px;line-height:1.65;padding:8px 12px;background:#16191d;border-radius:6px;margin-bottom:10px}
.row{display:flex;align-items:center;gap:10px;margin:7px 0}
.lbl{flex:1;font-size:13.5px}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:6px 14px;font-size:12.5px;cursor:pointer;min-width:62px}
.btn:hover{background:#388bfd}
.btn.on{background:#da3633}
.mono{font-family:ui-monospace,monospace;font-size:11.5px;color:#8b949e;min-width:196px;text-align:right}
</style></head><body>
<h1>省略号 / 破折号延长 · 原生 seed 择优</h1>
<div class="sub">同一文本、同一参考、同一参数，唯一变量是 seed；音频<b>零后处理</b>（模型自己把该词说长）。<br>
每格左侧标注该词发声时长与相对现役的倍数。<b>1.5x 以下听不出延长，3.5x 以上会拖过头</b>，所以只报 1.5–3.5x。</div>
__CARDS__
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

CARD = """<div class="card">
<div class="hd"><span class="id">__ID__</span><span class="tag">__TAG__</span></div>
<div class="txt">__TXT__</div>
__ROWS__
</div>"""

ROW = """<div class="row"><div class="lbl" style="color:__C__">__LBL__</div>
<button class="btn" data-src="__SRC__">▶ 播放</button>
<span class="mono">__INFO__</span></div>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="包含 pick 为空的条目（只放现役+候选）")
    a = ap.parse_args()

    summ = json.load(open("G:/_setup/_seedpick_summary.json", encoding="utf-8"))
    cards = []
    for e in summ:
        if e.get("err"):
            continue
        rid = e["id"]
        base = "G:/_setup/_audio_ch123/out/%s.wav" % rid
        if not os.path.exists(base):
            continue
        rows = []
        word = e.get("word", "?")
        bt = e.get("base")
        rows.append(ROW.replace("__LBL__", "现役成品（%s %s）" % (
            word, ("%.0fms" % bt) if bt else "n/a")).replace("__C__", "#8b949e")
            .replace("__SRC__", b64(nb(base))).replace("__INFO__", info(nb(base))))
        ranked = sorted([r for r in (e.get("seeds") or []) if r.get("ok")],
                        key=lambda r: -r["target"])
        for r in ranked[:3]:
            src = "G:/_setup/_seedpick/%s/s%s.wav" % (rid, r["seed"])
            if not os.path.exists(src):
                continue
            star = "★ " if r["seed"] == e.get("pick") else ""
            lbl = "%sseed%s（%s %.0fms）" % (star, r["seed"], word, r["target"])
            rows.append(ROW.replace("__LBL__", lbl)
                        .replace("__C__", "#56d364" if star else "#79c0ff")
                        .replace("__SRC__", b64(nb(src))).replace("__INFO__",
                            "%s · %.2fx" % (info(nb(src)), r.get("ratio") or 0)))
        if len(rows) == 1:
            continue
        txt = e.get("text", "")
        tag = ("选中 seed%s · %s %.1fx" % (e["pick"], word, e.get("pick_ratio") or 0)
               if e.get("pick") else (e.get("reason") or "无合适候选"))
        cards.append(CARD.replace("__ID__", rid).replace("__TAG__", tag)
                     .replace("__TXT__", txt).replace("__ROWS__", "\n".join(rows)))

    open(OUT, "w", encoding="utf-8").write(HTML.replace("__CARDS__", "\n".join(cards)))
    print("%s  %d 条  %.2f MB" % (OUT, len(cards), os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
