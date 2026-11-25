# -*- coding: utf-8 -*-
"""_build_ab_pool.py —— 候选池审听页（带词级音高曲线）

用户口径：
  「Free 更好，它是有点声调的，不是很平的那种 Free，更像普通人说话、有生气的说话、
    有表演性质的更好一点。」
  ⇒ 看的是**词内有没有音高走向**，不是整条平不平。

所以每个候选画一条 F0 曲线（半音刻度），竖线是词边界，词标半音偏移。
绿框 = 推荐（技术闸过 + 表达力好 + 目标词有释放爆破）。
"""
import argparse
import base64
import glob
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _pause_gap as PG   # noqa: E402
import _loud             # noqa: E402


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


def curve(p, spans):
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    f = np.where(f > 0, f, np.nan)
    med = np.nanmedian(f)
    st = 12.0 * np.log2(np.maximum(f, 1e-9) / med) if med else f
    return st, med, len(f) * 0.01


def svg(st, dur, spans, w=660, h=92):
    lo, hi = -8.0, 8.0
    vals = st[~np.isnan(st)]
    if len(vals):
        lo = min(lo, float(np.nanpercentile(vals, 2)) - 0.5)
        hi = max(hi, float(np.nanpercentile(vals, 98)) + 0.5)
    X = lambda t: 32 + (t / max(dur, 1e-6)) * (w - 40)
    Y = lambda v: h - 8 - (v - lo) / max(hi - lo, 1e-6) * (h - 16)
    out = ['<svg viewBox="0 0 %d %d" width="100%%" height="%d" '
           'style="display:block;background:#0f1216;border-radius:6px">' % (w, h, h)]
    # 0 线
    y0 = Y(0)
    out.append('<line x1="32" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#30363d" stroke-dasharray="3 3"/>'
               % (y0, w - 8, y0))
    # 词边界
    for (wd, a, b) in spans:
        out.append('<line x1="%.1f" y1="4" x2="%.1f" y2="%d" stroke="#21262d"/>' % (X(a), X(a), h - 4))
    # 曲线
    pts = []
    for i, v in enumerate(st):
        if np.isnan(v):
            continue
        pts.append("%.1f,%.1f" % (X(i * 0.01), Y(v)))
    if pts:
        out.append('<polyline fill="none" stroke="#58a6ff" stroke-width="1.4" points="%s"/>' % " ".join(pts))
    # 词标
    for i, (wd, a, b) in enumerate(spans):
        i0, i1 = int(a / 0.01), max(int(b / 0.01), int(a / 0.01) + 1)
        seg = st[i0:i1]
        seg = seg[~np.isnan(seg)]
        if not len(seg):
            continue
        m = float(np.median(seg))
        out.append('<text x="%.1f" y="11" font-size="9" fill="#8b949e" text-anchor="middle">%s%+.0f</text>'
                   % ((X(a) + X(b)) / 2, wd[:5], m))
    out.append('</svg>')
    return "".join(out)


HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>c3_0853 候选池 · 语调与咬字</title>
<style>
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#14171a;color:#e6e8ea;margin:0;padding:24px;max-width:940px}
h1{font-size:19px;margin:0 0 8px}
.sub{color:#9aa3ad;font-size:13px;line-height:1.85;margin-bottom:18px;border-left:3px solid #2b3036;padding-left:12px}
.sub b{color:#e6e8ea}
.card{background:#1b1f23;border:1px solid #2b3036;border-radius:10px;padding:14px 16px;margin:14px 0}
.card.best{border-color:#238636;box-shadow:0 0 0 1px #23863633}
.hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:6px}
.id{font-family:ui-monospace,monospace;font-size:13px;color:#58a6ff}
.m{font-family:ui-monospace,monospace;font-size:11.5px;color:#9aa3ad}
.row{display:flex;align-items:center;gap:10px;margin:8px 0 4px}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:6px 14px;font-size:12.5px;cursor:pointer;min-width:62px}
.btn:hover{background:#388bfd}
.btn.on{background:#da3633}
.tag{font-size:11px;padding:1px 7px;border-radius:10px;background:#21262d;color:#8b949e;margin-left:6px}
.tag.g{background:#23863633;color:#3fb950}
.tag.r{background:#da363333;color:#f85149}
</style></head><body>
<h1>c3_0853 · 同一句多生成几次，挑「有语调 + can't 咬得住」</h1>
<div class="sub">
文本：<b>I – I can see them all right, can't I?</b>（Charles 小声档）<br>
曲线 = 词级 F0（半音，0 线是全句中位）。<b>词内有起伏 = 有生气</b>；一条几乎贴着虚线的就是「平」。<br>
指标：<b>词内rng</b> 平均每个词的音高跨度（半音，≥2.5 才算有语气）；<b>平帧%</b> 落在 ±1 半音内的帧占比（越低越活）；
<b>尾音 burst</b> 是 can't 词尾的高频释放（读成 cam 时几乎没有）。<br>
所有 take <b>已等响对齐</b>（voiced RMS 统一到 −24 dBFS，页面内最大差 &lt;1dB），只比语调与咬字，
不会被音量大小带偏；原始文件没有改动，归一化副本在 <code>_pool_norm/</code>。<br>
<span style="color:#3fb950">绿框</span> = 我建议优先听；<span style="color:#f85149">红标</span> = 已知有问题的项。
</div>
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
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="c3_0853")
    ap.add_argument("--word", default="cant")
    ap.add_argument("--rank", default="G:/_setup/_pool_rank.json")
    ap.add_argument("--out", default="G:/_setup/_ab_pool.html")
    ap.add_argument("--pools", default="G:/_setup/_pool2")
    a = ap.parse_args()

    d = json.load(open(a.rank, encoding="utf-8"))
    text = d["text"]
    rows = d["rows"]
    paths = {}
    base = "G:/_setup/_audio_ch123/out/%s.wav" % a.id
    paths["now"] = base
    for pool in [x for x in a.pools.split(",") if x]:
        for p in glob.glob(os.path.join(pool, a.id, "s*.wav")):
            paths[os.path.basename(p)[:-4]] = p

    # 推荐 = 两道硬闸 + 表达力排序
    #   ★ 用户要求「语调好」和「字清楚」必须同时满足，不能互相折算成加权分。
    #     上一版把 hf_tail 当加分项，结果 s56（rng 3.72 很高但 hf_tail 只有 0.015，
    #     即尾音几乎没有释放）排到了第二 —— 那是「语调好但读成 cam」，正是他要修的问题。
    #   所以咬字改为硬闸：hf_tail ≥ 0.06 才算词尾有 /t/ 释放。
    def clear(r):
        b = r.get("burst") or {}
        return (b.get("hf_tail") or 0) >= 0.06

    def score(r):
        return round(r["mean_rng"] - r["bad_spike"] * 2.0
                     - max(0.0, r["flat_frac"] - 0.78) * 8.0, 2)

    for r in rows:
        if not r.get("ok"):
            continue
        r["score"] = score(r)
        r["clear"] = clear(r)
    pool = [r for r in rows if r.get("ok") and r.get("clear")]
    if not pool:
        pool = [r for r in rows if r.get("ok")]
    best = sorted(pool, key=lambda r: -r["score"])[:3]
    best_tags = {r["tag"] for r in best}

    order = sorted(rows, key=lambda r: (0 if r["tag"] in best_tags else 1,
                                        -(r.get("score") or -99)))

    cards = []
    for r in order:
        p = paths.get(r["tag"])
        if not p or not os.path.exists(p):
            continue
        spans = [(s[0], s[1], s[2]) for s in (r.get("spans") or [])]
        if not spans:
            continue
        # 用户要求：同一个页面里的 take 必须等响，否则「大小不一」会干扰听感判断。
        # 统一把 voiced 帧 RMS 拉到 -24 dBFS（口径 _dn_uniform.norm_rms），
        # 曲线也从归一化后的文件算 —— 原来 s43 峰值只有 0.04，F0 跟踪本身就不可靠。
        pn, li = _loud.to_uniform(p, "G:/_setup/_pool_norm/%s" % a.id)
        st, med, dur = curve(pn, spans)
        y, sr = sf.read(pn, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        b = r.get("burst") or {}
        flags = []
        if not r.get("ok"):
            flags.append('<span class="tag r">词数 %d/%d</span>' % (r["nword"], r.get("nword")))
        if r.get("bad_spike"):
            flags.append('<span class="tag r">功能词误重音×%d</span>' % r["bad_spike"])
        if r["flat_frac"] > 0.85:
            flags.append('<span class="tag r">偏平</span>')
        if (b.get("hf_tail") or 0) < 0.03:
            flags.append('<span class="tag r">尾音无释放</span>')
        cls = "card best" if r["tag"] in best_tags else "card"
        cards.append("""
<div class="%s">
 <div class="hd">
  <div><span class="id">%s</span>%s</div>
  <div class="m">%.2fs · ×%.2f 基线 · 词内rng %.2f · 平帧 %.0f%% · 尾burst %.3f</div>
 </div>
 %s
 <div class="row">
  <button class="btn" data-src="%s">▶ 播放</button>
  <span class="m">F0 中位 %dHz · peak %.2f · rough %.2f · 音域 %.1fst · 响度 %+.1fdB 对齐</span>
 </div>
</div>""" % (cls, r["tag"], "".join(flags), r["dur"], r["dr"] or 0, r["mean_rng"],
             100 * r["flat_frac"], b.get("hf_tail") or 0,
             svg(st, dur, spans), b64(pn),
             int(med), float(np.abs(y).max()), r["rough"], r["range_st"], li["gain_db"]))

    html = (HTML.replace("__CARDS__", "".join(cards))
            .replace("</body>", '<div style="color:#6e7681;font-size:12px;margin-top:18px">'
                     '推荐顺序：%s</div></body>' % " → ".join(r["tag"] for r in best)))
    open(a.out, "w", encoding="utf-8").write(html)
    print("->", a.out, "%.1f MB" % (len(html.encode()) / 1e6), "cards", len(cards))
    print("推荐：", " → ".join("%s(%.2f)" % (r["tag"], r["score"]) for r in best))


if __name__ == "__main__":
    sys.exit(main())
