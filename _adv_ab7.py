# -*- coding: utf-8 -*-
"""_adv_ab7.py —— 最终配方 A/B：单轴、不叠加。

用户裁决（2026-10-27 02:26）：
    「rate 0.70（慢）· r7 就不错了，如果叠加读的那个副词直接音色都变了，不要叠加」
    「要么就 pitch 要么就 rate0.7」

所以每个单元只给一个方案：
    句中词 → rate 0.70（时长轴；tts 下真变长，不从邻词借）
    句末词 → pitch +9（句末天然降调，rate 只会把它拖成气声）

三列固定顺序：交付版 / 同 seed 无标签（对照）/ 选定方案。
中间那列是必须的 —— 没有它就无法区分「标签起了作用」和「只是换了个 take」。
"""
import base64
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
import _adv_align as A
import _adv_prom as P
import _f0_accent as F

ROOT = "G:/_setup"
FF = "E:/tool/oopz/ffmpeg.exe"
OUT = os.path.join(ROOT, "_adv_ab7")
TMP = os.path.join(OUT, "mp3")
STATE = os.path.join(ROOT, "_mt_adv_state.json")

# uid -> (方案标签, 方案说明, tts 条件码)
PLAN = {
    "N0219": ("rate 0.70", "句中词 → 只拉慢", "r7"),
    "N0627": ("pitch +9", "句末词 → 只抬音高", "p9"),
}


def mp3(src):
    os.makedirs(TMP, exist_ok=True)
    p = os.path.join(TMP, os.path.basename(src)[:-4] + ".mp3")
    if not os.path.exists(p) or os.path.getmtime(p) < os.path.getmtime(src):
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", src,
                        "-ar", "44100", "-b:a", "96k", p], check=True)
    return p


def b64(p):
    return base64.b64encode(open(p, "rb").read()).decode()


def stat(wav, prom, text, adv):
    ts, fs, ss, dur = F.track_ex(wav)
    rows = F.read_prom(prom)
    sp = A.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    tw = A.text_words(text)
    idx = [i for i, t in enumerate(tw) if t["key"] == adv]
    if not idx:
        return None
    i = idx[-1]
    if sp[i]["t0"] is None:
        return None
    t0, t1 = sp[i]["t0"], sp[i]["t1"]
    sel = (ts >= t0) & (ts < t1)
    keep = np.r_[True, np.diff(ts) < 0.04]
    cws = P.measure_one(wav, prom, text) or []
    hit = [c for c in cws if c["key"] == adv]
    loc = round(hit[-1]["loc"], 2) if hit else None
    peak = round(float(fs[sel].max()), 0) if sel.sum() else None
    return dict(vdur=round(float(sel.sum()) * 0.005, 3),
                speech=round(float(keep.sum()) * 0.005, 2),
                dur=round(float(F.track(wav)[2]), 2),
                loc=loc, peak=peak)


def main():
    st = json.load(open(STATE, encoding="utf-8"))["units"]
    os.makedirs(OUT, exist_ok=True)
    blocks, table = [], []
    for uid, (lab, why, cond) in PLAN.items():
        x = st[uid]
        text, adv = x["text"], x["adv"].lower()
        rows = [("交付版（现在播的）", "_mt_pick/%s.wav" % uid,
                 "_wpt_out/_mt_pick__%s.prom" % uid, "base"),
                ("同 seed 无标签（对照）", "_adv_tts/%s_base_s2051.wav" % uid,
                 "_wpt_out/_adv_tts__%s_base_s2051.prom" % uid, "ctl"),
                ("★ %s" % lab, "_adv_tts/%s_%s_s2051.wav" % (uid, cond),
                 "_wpt_out/_adv_tts__%s_%s_s2051.prom" % (uid, cond), "new")]
        items = []
        for label, w, p, kind in rows:
            w = os.path.join(ROOT, w)
            p = os.path.join(ROOT, p)
            if not (os.path.exists(w) and os.path.exists(p)):
                items.append((label, None, None, kind))
                continue
            s = stat(w, p, text, adv)
            items.append((label, mp3(w), s, kind))
            if s:
                table.append(dict(uid=uid, adv=x["adv"], label=label,
                                  cond=cond, **s))
        cards = []
        for label, mp, s, kind in items:
            if mp is None:
                cards.append('<div class="row"><div class="lb">%s</div>'
                             '<div class="mut">缺文件</div></div>' % label)
                continue
            badges = ""
            if s:
                badges = ('<div class="badges">'
                          '<span class="k">副词有声 <b>%.3fs</b></span>'
                          '<span class="k">全句有声 <b>%.2fs</b></span>'
                          '<span class="k">文件 <b>%.2fs</b></span>'
                          '<span class="k">F0(p75) <b>%s</b></span>'
                          '<span class="k">峰值 <b>%sHz</b></span>'
                          '</div>'
                          % (s["vdur"], s["speech"], s["dur"],
                             "—" if s["loc"] is None else "%+.2f" % s["loc"],
                             "—" if s["peak"] is None else "%.0f" % s["peak"]))
            cards.append(
                '<div class="row%s"><div class="lb">%s</div>'
                '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>'
                '%s</div>' % (" hl" if kind == "new" else "", label, b64(mp), badges))
        blocks.append(
            '<section><h2>%s&nbsp; <code>%s</code> &nbsp;<span class="tag">%s</span></h2>'
            '<p class="txt">%s</p>%s</section>'
            % (uid, x["adv"], why, text, "".join(cards)))

    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>最终配方 A/B：rate 0.70 与 pitch +9（不叠加）</title>
<style>
*{box-sizing:border-box}
:root{--ink:#111827;--mut:#6b7280;--line:#e5e7eb;--bg:#f8fafc;--card:#fff;
      --acc:#0f766e;--hi:#ecfdf5}
body{margin:0;background:var(--bg);color:var(--ink);
     font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:28px 18px 64px}
h1{font-size:21px;margin:0 0 6px}
h2{font-size:16px;margin:0 0 4px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
code{font:13px ui-monospace,Consolas,monospace;background:#eef2f7;padding:1px 6px;border-radius:5px}
.tag{font-size:11.5px;font-weight:400;color:var(--acc);background:var(--hi);
     border:1px solid #a7f3d0;padding:1px 8px;border-radius:20px}
.lead{color:var(--mut);margin:0 0 18px}
.hint{background:#fff;border:1px solid var(--line);border-left:3px solid var(--acc);
      border-radius:8px;padding:12px 14px;font-size:13.5px;color:#374151;margin-bottom:22px}
.hint b{color:var(--ink)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;
        padding:16px 18px;margin-bottom:16px}
.txt{color:var(--mut);font-size:13.5px;margin:2px 0 12px;font-style:italic}
.row{padding:10px 0;border-top:1px solid #f1f5f9}
.row:first-of-type{border-top:none}
.row.hl{background:var(--hi);border-radius:8px;padding:10px 12px;margin-top:4px;
        border-top:none;box-shadow:inset 0 0 0 1px #a7f3d0}
.lb{font-size:13.5px;font-weight:600;margin-bottom:6px}
.row.hl .lb{color:var(--acc)}
audio{width:100%;height:32px}
.badges{margin-top:6px;display:flex;flex-wrap:wrap;gap:6px}
.k{font-size:11.5px;color:var(--mut);background:#f4f6f8;border:1px solid var(--line);
   padding:1px 7px;border-radius:20px}
.k b{color:var(--ink);font-variant-numeric:tabular-nums}
.mut{color:var(--mut);font-size:13px}
</style></head><body><div class="wrap">
<h1>最终配方 A/B：单轴，不叠加</h1>
<p class="lead">按你的裁决 —— 要么 pitch、要么 rate 0.70，不组合。两条各用一个方案。</p>
<div class="hint">
<b>三列固定顺序：</b>① 现在交付的版本 ② 同一 seed 的无标签复刻（<b>对照</b>）③ 选定方案。<br>
<b>为什么要第二列：</b>tts 是重新生成，换了 take 本身就会有差异。没有这一列，就分不清
「标签起了作用」还是「只是碰巧抽到另一个 take」。<br>
<b>副词有声</b> = 那个词实际发声多久；<b>全句有声</b> = 整条所有发声帧加起来。
全句也变长 ⇒ 真变慢；全句不变而副词变长 ⇒ 从邻词借的。<br>
<b>F0(p75)</b> = 词内基频 75 分位相对上下文的抬升（半音，≥2 可听），不用最大值，避免假峰。
</div>
%BODY%
</div></body></html>""".replace("%BODY%", "".join(blocks))
    p = os.path.join(OUT, "最终配方-rate07与pitch9.html")
    open(p, "w", encoding="utf-8").write(html)
    print("写出 %s (%.1f MB, %d 条音频)"
          % (p, os.path.getsize(p) / 1e6, html.count("data:audio/mpeg")))
    for r in table:
        print("%-7s %-22s vdur=%-6s 全句=%-5s loc=%-6s 峰=%sHz"
              % (r["uid"], r["label"][:22], r["vdur"], r["speech"],
                 r["loc"], r["peak"]))


if __name__ == "__main__":
    main()
