# -*- coding: utf-8 -*-
"""_build_ab_s46.py —— s46 参照页：语调像 s46 + can't 的 /t/ 真的爆出来

用户口径（2026-11-25 08:43 / 08:44 / 08:45 连提三次，全部照此执行）：
  1) 「s46 的问题根本不是语调，它这个就也很好了……我是觉得 s46 是最合适罢了」
     ⇒ s46 是**参照/首选**，不是淘汰项；rng 越大越好的排序作废。
  2) 「他的问题是他把 can't 读成了 cam I」
     ⇒ 唯一要修的指标：can't 词尾有没有释放爆破。
  3) 「I 与 I 之间间隔不用太大，说 I 差 0 点，最多 0.2 秒」
     ⇒ 口吃重复间隔 ≤200ms（已用 `_gapfix3` 剪好，实测听得见的间隔 110~200ms）。

页面结构：s46 打头当参照（标红它的 /t/ 缺失），后面按「与 s46 的语调距离」排序，
/t/ 有释放的排前面并加绿框。全部等响 -24dBFS。
"""
import base64
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _loud  # noqa: E402

OUT = "G:/_setup/_ab_s46.html"
FIXDIR = "G:/_setup/_gapfix3/c3_0853"
REL_MIN = 0.06           # can't 词尾 3.5k+ 占比 ≥6% 才算 /t/ 有释放


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


def f0_svg(p, spans, w=660, h=88):
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    f = np.where(f > 0, f, np.nan)
    med = np.nanmedian(f)
    st = 12.0 * np.log2(np.maximum(f, 1e-9) / med)
    dur = len(st) * 0.01
    lo, hi = -8.0, 8.0
    v = st[~np.isnan(st)]
    if len(v):
        lo = min(lo, float(np.nanpercentile(v, 2)) - 0.5)
        hi = max(hi, float(np.nanpercentile(v, 98)) + 0.5)
    X = lambda t: 30 + (t / max(dur, 1e-6)) * (w - 38)
    Y = lambda x: h - 8 - (x - lo) / max(hi - lo, 1e-6) * (h - 16)
    out = ['<svg viewBox="0 0 %d %d" style="display:block;width:100%%;height:%dpx;'
           'background:#0f1216;border-radius:6px">' % (w, h, h)]
    out.append('<line x1="30" y1="%.1f" x2="%d" y2="%.1f" stroke="#30363d" stroke-dasharray="3 3"/>'
               % (Y(0), w - 8, Y(0)))
    for (wd, a, b) in spans:
        out.append('<line x1="%.1f" y1="3" x2="%.1f" y2="%d" stroke="#21262d"/>' % (X(a), X(a), h - 3))
    pts = ["%.1f,%.1f" % (X(i * 0.01), Y(x)) for i, x in enumerate(st) if not np.isnan(x)]
    if pts:
        out.append('<polyline fill="none" stroke="#58a6ff" stroke-width="1.4" points="%s"/>' % " ".join(pts))
    for (wd, a, b) in spans:
        i0, i1 = int(a / 0.01), max(int(b / 0.01), int(a / 0.01) + 1)
        seg = st[i0:i1]
        seg = seg[~np.isnan(seg)]
        if not len(seg):
            continue
        out.append('<text x="%.1f" y="10" font-size="9" fill="#8b949e" text-anchor="middle">%s%+.0f</text>'
                   % ((X(a) + X(b)) / 2, wd[:5], float(np.median(seg))))
    out.append('</svg>')
    return "".join(out)


def tail_svg(p, a, b, w=660, h=64):
    """can't 词尾 10ms 能量条：先塌下去再竖起来一根 = 爆破；一路平 = 收成 /m/。"""
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    n = max(16, int(0.01 * sr))
    seg = y[int(a * sr):int(b * sr)]
    c = len(seg) // n
    db = np.array([20 * np.log10(np.sqrt((seg[i * n:(i + 1) * n] ** 2).mean()) + 1e-12) for i in range(c)])
    v = np.clip((db - (db.max() - 45)) / 45.0, 0, 1)
    bw = (w - 36) / max(len(v), 1)
    out = ['<svg viewBox="0 0 %d %d" style="display:block;width:100%%;height:%dpx;'
           'background:#0f1216;border-radius:6px">' % (w, h, h)]
    for i, x in enumerate(v):
        col = "#f85149" if i >= len(v) - 4 else "#3fb950" if x > 0.5 else "#484f58"
        bh = max(1.0, x * (h - 8))
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                   % (30 + i * bw, h - 4 - bh, max(0.6, bw - 1), bh, col))
    out.append('<text x="2" y="12" font-size="8" fill="#8b949e">词尾</text>')
    out.append('</svg>')
    return "".join(out)


HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>c3_0853 · 以 s46 为参照</title>
<style>
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#14171a;color:#e6e8ea;margin:0;padding:24px;max-width:940px}
h1{font-size:19px;margin:0 0 8px}
.sub{color:#9aa3ad;font-size:13px;line-height:1.85;margin-bottom:16px;border-left:3px solid #2b3036;padding-left:12px}
.sub b{color:#e6e8ea}
.card{background:#1b1f23;border:1px solid #2b3036;border-radius:10px;padding:13px 15px;margin:13px 0}
.card.ref{border-color:#da3633}
.card.best{border-color:#238636;box-shadow:0 0 0 1px #23863633}
.hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:7px}
.id{font-family:ui-monospace,monospace;font-size:13px;color:#58a6ff}
.m{font-family:ui-monospace,monospace;font-size:11.5px;color:#9aa3ad}
.row{display:flex;align-items:center;gap:10px;margin:6px 0 2px}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:5px 13px;font-size:12.5px;cursor:pointer;min-width:58px}
.btn:hover{background:#388bfd}
.btn.on{background:#da3633}
.tag{font-size:11px;padding:1px 7px;border-radius:10px;background:#21262d;color:#8b949e;margin-left:6px}
.tag.g{background:#23863633;color:#3fb950}
.tag.r{background:#da363333;color:#f85149}
.lbl{font-size:11px;color:#6e7681;margin:6px 0 2px}
</style></head><body>
<h1>c3_0853 · 以 <span style="color:#da3633">s46</span> 为参照找「能听见 can't 的 t」</h1>
<div class="sub">
文本：<b>I – I can see them all right, can't I?</b><br>
判据按你的口径改了：<b>语调不评优劣，s46 的语调就是目标</b>；唯一硬指标是 <b>can't 词尾有没有爆破</b>
（读成 “cam” 时词尾没有那根竖条）。<br>
「I – I」已按口吃处理，剪到 <b>≤200ms</b>（实测听得见的间隔列在每张卡上），不再当破折号停顿。<br>
全部 <b>等响 −24dBFS</b>。<span style="color:#3fb950">绿框</span>= /t/ 有释放且语调接近 s46；
<span style="color:#f85149">红框</span>= 你的首选 s46，语调对、但 /t/ 没出来。
</div>
__CARDS__
<script>
let cur=null;
document.querySelectorAll('.btn').forEach(b=>{b.onclick=()=>{
  if(cur){cur.pause();cur=null;}
  document.querySelectorAll('.btn').forEach(x=>{x.classList.remove('on');x.textContent='▶ 播放';});
  if(b.classList.contains('on')){return;}
  const a=new Audio(b.dataset.src);a.play();cur=a;b.classList.add('on');b.textContent='■ 停止';
  a.onended=()=>{b.classList.remove('on');b.textContent='▶ 播放';cur=null;};
};});
</script></body></html>
"""


def main():
    rank = json.load(open("G:/_setup/_pool_rank3.json", encoding="utf-8"))
    match = json.load(open("G:/_setup/_s46_match3.json", encoding="utf-8"))
    ranks = {r["tag"]: r for r in rank["rows"]}
    items = []
    for tag, m in match.items():
        p = os.path.join(FIXDIR, "%s.wav" % tag)
        if not os.path.exists(p):
            continue
        b = m.get("burst") or {}
        items.append(dict(tag=tag, p=p, dist=m["contour_dist"], hf=b.get("hf_tail", 0),
                          jump=b.get("hf_jump", 0), igap=m.get("i_gap_aud_ms"),
                          spans=ranks[tag]["spans"], dur=ranks[tag]["dur"],
                          rel=(b.get("hf_tail", 0) >= REL_MIN)))
    ref = [i for i in items if i["tag"] == "s46"][0]
    others = [i for i in items if i["tag"] != "s46"]
    good = sorted([i for i in others if i["rel"]], key=lambda i: i["dist"])
    weak = sorted([i for i in others if not i["rel"]], key=lambda i: i["dist"])
    ordered = [ref] + good + weak
    best = {i["tag"] for i in good[:3]}

    cards = []
    for i in ordered:
        pn, li = _loud.to_uniform(i["p"], "G:/_setup/_pool_norm/s46")
        spans = [(s[0], s[1], s[2]) for s in i["spans"]]
        cant = [s for s in spans if s[0].startswith("cant")][0]
        _f = parselmouth.Sound(pn).to_pitch(0.01, 75, 600).selected_array["frequency"]
        _f = _f[_f > 0]
        med = int(np.median(_f)) if len(_f) else 0
        flags = []
        if i["tag"] == "s46":
            flags.append('<span class="tag r">你的首选 · 语调对</span>')
        if not i["rel"]:
            flags.append('<span class="tag r">/t/ 没释放（cam）</span>')
        else:
            flags.append('<span class="tag g">/t/ 有爆破</span>')
        if i["tag"] in best:
            flags.append('<span class="tag g">推荐听</span>')
        cls = "card ref" if i["tag"] == "s46" else ("card best" if i["tag"] in best else "card")
        cards.append("""
<div class="%s">
 <div class="hd"><div><span class="id">%s</span>%s</div>
  <div class="m">%.2fs · 语调距离 %.2f · /t/ 释放 %.3f · 口吃间隔 %sms（听得见）</div></div>
 <div class="lbl">F0 语调（灰竖线=词界）</div>
 %s
 <div class="lbl">can't 词尾能量（10ms/条；先塌再竖一根=爆破）</div>
 %s
 <div class="row"><button class="btn" data-src="%s">▶ 播放</button>
  <span class="m">F0 中位 %dHz · 响度 %+.1fdB 对齐</span></div>
</div>""" % (cls, i["tag"], "".join(flags), i["dur"], i["dist"], i["hf"], i["igap"],
             f0_svg(pn, spans), tail_svg(pn, cant[1], cant[2]), b64(pn), med,
             li["gain_db"]))

    # F0 中位单独取（上面 li 里没存，补一行）
    html = HTML.replace("__CARDS__", "".join(cards))
    open(OUT, "w", encoding="utf-8").write(html)
    print("->", OUT, "%.2f MB" % (os.path.getsize(OUT) / 1e6), "cards", len(cards))
    print("推荐：", " → ".join("%s(语调距%.2f, /t/ %.3f)" % (i["tag"], i["dist"], i["hf"]) for i in good[:3]))


if __name__ == "__main__":
    sys.exit(main())
