"""_build_ab_gap.py —— 「断开」修复审听页（带语调曲线）

用户口径：
  「为什么所有语句都没有分割好，都是从中间断开的？」
  「我说的语调，就是你的这些曲线是更符合的」

所以这页不只放音频，还把**F0 语调曲线**画出来，让「断开」变成看得见的东西：
  灰色块 = 句内停顿（越宽越长）
  红色块 = 超限停顿（就是「断成两截」的那一刀）
  蓝线   = F0 语调轮廓（只有发声帧才连线，静音处断开）

每条四个轨：seed 原版 / 裁后，各配一条曲线。
"""
import base64
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _pause_gap as PG       # noqa: E402
import _loud                 # noqa: E402

OUT = "G:/_setup/_ab_gap.html"


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


def curve(path):
    """返回 (f0[], 停顿段[(a,b)], 是否超限[]) —— 时间单位秒。"""
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    dur = len(y) / sr
    f = parselmouth.Sound(path).to_pitch(0.01, 75, 600).selected_array["frequency"]
    # 能量找停顿（10ms 帧，低于峰值 −35dB）
    n = int(0.01 * sr)
    c = len(y) // n
    db = 20 * np.log10(np.sqrt((y[:c * n].reshape(c, n) ** 2).mean(1)) + 1e-12)
    top = np.percentile(db, 95)
    q = db < top - 32
    gaps, cur = [], None
    for i, v in enumerate(q):
        if v and cur is None:
            cur = i
        if (not v or i == len(q) - 1) and cur is not None:
            if (i - cur) >= 12 and cur > 8 and i < len(q) - 8:     # ≥120ms 且不含首尾
                gaps.append((cur * 0.01, i * 0.01))
            cur = None
    return [float(x) for x in f], gaps, dur, (top, db)


def svg(f0, gaps, dur, red=None, w=680, h=104):
    v = [x for x in f0 if x > 0]
    if not v:
        return ""
    lo, hi = np.percentile(v, 3), np.percentile(v, 97)
    lo, hi = max(50, lo - 18), min(600, hi + 18)
    if hi - lo < 40:
        mid = (hi + lo) / 2
        lo, hi = mid - 20, mid + 20

    def X(t):
        return 6 + (t / max(dur, 0.01)) * (w - 12)

    def Y(f):
        return h - 10 - ((f - lo) / (hi - lo)) * (h - 24)

    parts = ['<rect x="0" y="0" width="%d" height="%d" fill="#101317"/>' % (w, h)]
    # 裁掉的部分（红）—— 只画在原版图上，让「断在哪」可见
    for a, b in (red or []):
        parts.append('<rect x="%.1f" y="0" width="%.1f" height="%d" fill="#da3633" opacity="0.55"/>'
                     % (X(max(0, a)), max(1.5, X(b) - X(a)), h))
    # 停顿灰块
    for a, b in gaps:
        parts.append('<rect x="%.1f" y="0" width="%.1f" height="%d" fill="#2b3036" opacity="0.85"/>'
                     % (X(a), max(1.0, X(b) - X(a)), h))
    # F0 折线（仅发声帧）
    seg, segs = [], []
    for i, f in enumerate(f0):
        if f > 0:
            seg.append((i * 0.01, f))
        elif seg:
            segs.append(seg)
            seg = []
    if seg:
        segs.append(seg)
    for s in segs:
        if len(s) < 2:
            continue
        pts = " ".join("%.1f,%.1f" % (X(t), Y(f)) for t, f in s)
        parts.append('<polyline points="%s" fill="none" stroke="#58a6ff" stroke-width="1.6" '
                     'stroke-linejoin="round"/>' % pts)
    # 基线
    parts.append('<line x1="0" y1="%d" x2="%d" y2="%d" stroke="#1f2429" stroke-width="1"/>'
                 % (h - 1, w, h - 1))
    return '<svg viewBox="0 0 %d %d" preserveAspectRatio="none">%s</svg>' % (w, h, "".join(parts))


def info(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    f = f[f > 0]
    return dict(dur=len(y) / sr, f0=int(np.median(f)) if len(f) else 0,
                peak=float(np.abs(y).max()))


HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>句中断裂修复 · 语调曲线对照</title>
<style>
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#14171a;color:#e6e8ea;margin:0;padding:24px;max-width:1000px}
h1{font-size:19px;margin:0 0 6px}
.sub{color:#9aa3ad;font-size:13px;line-height:1.85;margin-bottom:16px;border-left:3px solid #2b3036;padding-left:12px}
.legend{font-size:12px;color:#9aa3ad;margin:10px 0 18px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 12px;vertical-align:-1px}
.card{background:#1b1f23;border:1px solid #2b3036;border-radius:10px;padding:14px 16px;margin:16px 0}
.hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:8px}
.id{font-family:ui-monospace,monospace;font-size:13px;color:#58a6ff}
.tag{font-size:12px;color:#9aa3ad}
.txt{color:#d5d9dd;font-size:15px;line-height:1.65;padding:8px 12px;background:#16191d;border-radius:6px;margin-bottom:10px}
.block{margin:10px 0 4px}
.blbl{font-size:12.5px;color:#8b949e;display:flex;justify-content:space-between;margin-bottom:4px}
.blbl b{color:#c9d1d9;font-weight:600}
.row{display:flex;align-items:center;gap:10px;margin:6px 0}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:5px 13px;font-size:12.5px;cursor:pointer;min-width:58px}
.btn:hover{background:#388bfd}
.btn.on{background:#da3633}
.mono{font-family:ui-monospace,monospace;font-size:11.5px;color:#8b949e}
svg{display:block;width:100%;height:104px;border-radius:6px;margin-top:2px}
</style></head><body>
<h1>「从中间断开」修复 · 语调曲线对照</h1>
<div class="sub">模型在<b>所有标点处都停太久</b>：逗号 640~840ms、句号 780~1640ms、破折号 1240ms。
真实对白是逗号 200~350、句号 400~600。<br>
修复只删<b>真静音</b>（不碰任何有声采样），所以音色、语调、字一个不动 —— 已用 ASR 验证 6/6 覆盖率不掉。<br>
本页所有轨<b>已等响</b>（voiced RMS −24 dBFS），只比语调与停顿，不被音量差带偏。</div>
<div class="legend">曲线：<i style="background:#58a6ff"></i>F0 语调轮廓
<i style="background:#2b3036"></i>句内停顿
<i style="background:#da3633"></i>裁掉的部分
</div>
__CARDS__
<script>
document.querySelectorAll('.btn').forEach(b=>{b.onclick=()=>{
  const a=document.getElementById(b.dataset.t);
  if(a.paused){document.querySelectorAll('audio').forEach(x=>x.pause());
    a.currentTime=0;a.play();b.classList.add('on');
    a.onended=()=>b.classList.remove('on');}
  else{a.pause();b.classList.remove('on');}}});
</script></body></html>
"""


def main():
    pick = json.load(open("G:/_setup/_seedpick_pick.json", encoding="utf-8"))
    rep = {}
    if os.path.exists("G:/_setup/_gapfix_report.json"):
        rep = json.load(open("G:/_setup/_gapfix_report.json", encoding="utf-8"))
    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
    cards = []
    for rid, sd in pick.items():
        before = "G:/_setup/_seedpick/%s/s%s.wav" % (rid, sd)
        after = "G:/_setup/_gapfix/%s.wav" % rid
        if not (os.path.exists(before) and os.path.exists(after)):
            continue
        text = PG.clean(rows[rid]["text"])
        blocks = []
        for tag, name, p, col in (("b", "seed 原版", before, "#8b949e"),
                                  ("a", "裁后", after, "#3fb950")):
            # 等响：同一个页面里所有轨统一到 voiced RMS -24 dBFS，避免音量盖过语调
            pn, li = _loud.to_uniform(p, "G:/_setup/_pool_norm/gap")
            f0, gaps, dur, _ = curve(pn)
            it = info(pn)
            red = None
            if tag == "b" and rid in rep:
                # 红块 = 静音核心中点附近被删掉的那段
                red = []
                for cc in rep[rid].get("cut_at", []):
                    mid = cc["at"] + cc["gap_ms"] / 2000.0
                    half = cc["cut_ms"] / 2000.0
                    red.append((mid - half, mid + half))
            gtxt = " · ".join("%.0fms" % ((b - a) * 1000) for a, b in gaps) or "无"
            blocks.append("""<div class="block">
<div class="blbl"><span><b>%s</b></span><span class="mono">%0.2fs · F0 %d · 停顿 %s</span></div>
<svg viewBox="0 0 680 104" preserveAspectRatio="none">%s</svg>
<div class="row"><button class="btn" data-t="au_%s_%s">播放</button>
<audio id="au_%s_%s" preload="none" src="%s"></audio>
<span class="mono">%s</span></div></div>""" % (
                name, it["dur"], it["f0"], gtxt,
                svg(f0, gaps, dur, red).split(">", 1)[1].rsplit("</svg>", 1)[0],
                rid, tag, rid, tag, b64(pn), p.split("/")[-1]))
        cards.append("""<div class="card"><div class="hd"><span class="id">%s</span>
<span class="tag">%s</span></div><div class="txt">%s</div>%s</div>""" % (
            rid, rows[rid].get("who", "") + " · " + rows[rid].get("emo", ""),
            text, "".join(blocks)))

    html = HTML.replace("__CARDS__", "\n".join(cards))
    open(OUT, "w", encoding="utf-8").write(html)
    print("-> %s  %.1f MB  %d 条" % (OUT, len(html.encode()) / 1e6, len(cards)))


if __name__ == "__main__":
    sys.exit(main())
