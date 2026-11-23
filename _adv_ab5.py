# -*- coding: utf-8 -*-
"""_adv_ab5.py —— edit 模板 + 单词级标注 的 A/B 试听页。

想验证的三件事，每件都给了对照：
  1. edit 纯复刻（base）跟原交付是不是同一个人、整句韵律保不保
  2. `<rate>` 能不能让那个词"真的慢下来"（用**有声帧时长**看，不看 ASR 边界）
  3. `<pitch>` 到底有没有动 F0（预期：一点没动，用来证明这条路走不通）

每个 take 都标三个数：
  vdur  词内有声帧总时长（"真的慢了"的直接证据）
  loc   p75 版 F0 抬升（半音）—— 旧的 max 版会被词尾假峰污染，不采用
  总时长
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
OUT = os.path.join(ROOT, "_adv_ab5")
TMP = os.path.join(OUT, "mp3")
STATE = os.path.join(ROOT, "_mt_adv_state.json")

GROUPS = [
    dict(uid="N0219", adv="nervously",
         text="They all stood about nervously, Kingshaw had red hair.",
         note="副词在句中（后面是逗号）。rate 0.70 在这里生效：有声时长 +37%，三个 seed 完全一致。",
         takes=[("原交付", "_mt_pick/N0219.wav", "_wpt_out/_mt_pick__N0219.prom"),
                ("edit 纯复刻（无标签）", "_adv_edit/N0219_base_s2041.wav",
                 "_wpt_out/_adv_edit__N0219_base_s2041.prom"),
                ("rate 0.80", "_adv_edit/N0219_r8_s2041.wav",
                 "_wpt_out/_adv_edit__N0219_r8_s2041.prom"),
                ("rate 0.70  s2041", "_adv_edit/N0219_r7_s2041.wav",
                 "_wpt_out/_adv_edit__N0219_r7_s2041.prom"),
                ("rate 0.70  s2043", "_adv_edit/N0219_r7_s2043.wav",
                 "_wpt_out/_adv_edit__N0219_r7_s2043.prom"),
                ("rate 0.70  s2045", "_adv_edit/N0219_r7_s2045.wav",
                 "_wpt_out/_adv_edit__N0219_r7_s2045.prom"),
                ("pitch +6 半音", "_adv_edit/N0219_p6_s2041.wav",
                 "_wpt_out/_adv_edit__N0219_p6_s2041.prom")]),
    dict(uid="N0627", adv="carefully",
         text="Then, he bent down and lifted the thing up carefully.",
         note="副词在句末（后面是句号）。句末本来就降调，rate 只会「拖长+下沉」，不会抬 F0。",
         takes=[("原交付", "_mt_pick/N0627.wav", "_wpt_out/_mt_pick__N0627.prom"),
                ("edit 纯复刻（无标签）", "_adv_edit/N0627_base_s2041.wav",
                 "_wpt_out/_adv_edit__N0627_base_s2041.prom"),
                ("rate 0.80", "_adv_edit/N0627_r8_s2041.wav",
                 "_wpt_out/_adv_edit__N0627_r8_s2041.prom"),
                ("rate 0.70", "_adv_edit/N0627_r7_s2041.wav",
                 "_wpt_out/_adv_edit__N0627_r7_s2041.prom"),
                ("rate 0.60", "_adv_edit/N0627_r6_s2041.wav",
                 "_wpt_out/_adv_edit__N0627_r6_s2041.prom"),
                ("pause + rate 0.70", "_adv_edit/N0627_pr7_s2041.wav",
                 "_wpt_out/_adv_edit__N0627_pr7_s2041.prom"),
                ("短语级 rate 0.75（up carefully）", "_adv_edit/N0627_ph7_s2041.wav",
                 "_wpt_out/_adv_edit__N0627_ph7_s2041.prom"),
                ("pitch +6 半音", "_adv_edit/N0627_p6_s2041.wav",
                 "_wpt_out/_adv_edit__N0627_p6_s2041.prom")]),
]


def mp3(rel):
    os.makedirs(TMP, exist_ok=True)
    p = os.path.join(TMP, rel.replace("/", "_")[:-4] + ".mp3")
    if not (os.path.exists(p) and os.path.getsize(p) > 1000):
        subprocess.run([FF, "-y", "-v", "error", "-i", os.path.join(ROOT, rel),
                        "-ac", "1", "-ar", "44100", "-b:a", "64k", p],
                       capture_output=True)
    return p


def metrics(wav, prom, text, adv):
    """vdur / vx / loc(p75) / 总时长。"""
    ts, fs, ss, dur = F.track_ex(wav)
    rows = F.read_prom(prom)
    spans = A.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    tw = A.text_words(text)

    def vd(t0, t1):
        sel = (ts >= t0) & (ts < t1)
        return float(sel.sum()) * 0.005

    med = None
    vt = None
    for i, x in enumerate(tw):
        if not x["is_word"] or x["key"] in F.FUNC:
            continue
        sp = spans[i]
        if sp["t0"] is None:
            continue
        v = vd(sp["t0"], sp["t1"])
        if x["key"] == adv:
            vt = v
    others = []
    for i, x in enumerate(tw):
        if not x["is_word"] or x["key"] in F.FUNC or x["key"] == adv:
            continue
        sp = spans[i]
        if sp["t0"]:
            others.append(vd(sp["t0"], sp["t1"]))
    if others:
        med = float(np.median(others))
    cws = P.measure_one(wav, prom, text, strict=True) or []
    hit = [c for c in cws if c["key"] == adv]
    loc = round(hit[-1]["loc"], 2) if hit else None
    return dict(vdur=round(vt, 3) if vt is not None else None,
                vx=(round(vt / med, 2) if (vt and med) else None),
                loc=loc, dur=round(dur, 2))


def main():
    os.makedirs(OUT, exist_ok=True)
    blocks = []
    table = []
    for g in GROUPS:
        rows = []
        for label, wrel, prel in g["takes"]:
            wav = os.path.join(ROOT, wrel)
            prom = os.path.join(ROOT, prel)
            if not (os.path.exists(wav) and os.path.exists(prom)):
                print("skip", wrel)
                continue
            m = metrics(wav, prom, g["text"], g["adv"].lower())
            m.update(label=label, wav=wrel)
            table.append(dict(uid=g["uid"], **m))
            b64 = base64.b64encode(open(mp3(wrel), "rb").read()).decode()
            badge = ""
            if m["vdur"]:
                badge += '<span class="k">有声 <b>%.3fs</b></span>' % m["vdur"]
            if m["vx"]:
                badge += '<span class="k">×同句 <b>%.2f</b></span>' % m["vx"]
            if m["loc"] is not None:
                badge += '<span class="k">F0(p75) <b>%+.2f</b></span>' % m["loc"]
            badge += '<span class="k">总长 <b>%.2fs</b></span>' % m["dur"]
            rows.append(
                '<div class="row"><div class="lab">%s</div>'
                '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>'
                '<div class="badges">%s</div></div>' % (label, b64, badge))
        blocks.append(
            '<section><h2>%s · <code>%s</code></h2><p class="note">%s</p>'
            '<p class="text">%s</p>%s</section>'
            % (g["uid"], g["adv"], g["note"], g["text"], "".join(rows)))

    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>edit + 单词级标注 A/B</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1b1f24;--mut:#5b6570;--line:#e3e7ec;--ac:#2563eb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.65 -apple-system,"Segoe UI","Noto Sans SC",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:24px;margin:0 0 6px}
.lead{color:var(--mut);margin:0 0 10px}
.hint{background:#eef4ff;border:1px solid #cdddff;border-radius:10px;
 padding:12px 14px;margin:18px 0 26px;font-size:14px;color:#1e3a8a}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;
 padding:18px 18px 8px;margin:0 0 22px}
h2{font-size:17px;margin:0 0 4px}
h2 code{background:#f1f3f5;padding:1px 6px;border-radius:5px;font-size:14px}
.note{color:var(--mut);font-size:13px;margin:2px 0 6px}
.text{font-family:ui-monospace,Consolas,monospace;font-size:13px;color:#334155;
 background:#f8fafc;border-left:3px solid var(--ac);padding:7px 10px;border-radius:0 6px 6px 0;
 margin:0 0 12px}
.row{padding:9px 0;border-top:1px solid var(--line)}
.lab{font-size:13.5px;font-weight:600;margin:0 0 6px}
audio{width:100%;height:32px}
.badges{margin-top:6px;display:flex;flex-wrap:wrap;gap:6px}
.k{font-size:11.5px;color:var(--mut);background:#f4f6f8;border:1px solid var(--line);
 padding:1px 7px;border-radius:20px}
.k b{color:var(--ink);font-variant-numeric:tabular-nums}
</style></head><body><div class="wrap">
<h1>edit 模板 + 单词级标注：实测</h1>
<p class="lead">同一句话、同一个源音频，只改标注。每一行都能直接对比。</p>
<div class="hint">
<b>先看这三个数，再听。</b><br>
<b>有声</b> = 这个词实际发声的时长（帧累加）。这是「真的慢下来」的直接证据 ——
之前用 ASR 词边界算，边界里含尾随静音，改前改后都是 0.64，看不出任何变化。<br>
<b>×同句</b> = 该词有声时长 ÷ 同句其它实词的中位。<br>
<b>F0(p75)</b> = 词内基频 75 分位相对上下文的抬升（半音）。旧版用最大值，
会被词尾 0.04 秒的假峰拉到 +5 以上 —— N0627 的 rate 0.60 就是这么「命中」的。<br>
<b>总长</b> = 整条音频时长（edit 基本按源时长输出，插 pause 才会变长）。
</div>
%BODY%
</div></body></html>""".replace("%BODY%", "".join(blocks))

    p = os.path.join(OUT, "试听-edit标注.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    json.dump(table, open(os.path.join(OUT, "_table.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("写出 %s  (%.1f MB, %d 条音频)"
          % (p, os.path.getsize(p) / 1e6,
             sum(1 for _ in range(html.count("data:audio/mpeg")))))
    for r in table:
        print("%-7s %-34s vdur=%-6s vx=%-5s loc=%-7s dur=%s"
              % (r["uid"], r["label"][:34], r["vdur"], r["vx"], r["loc"], r["dur"]))


if __name__ == "__main__":
    main()
