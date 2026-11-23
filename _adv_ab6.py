# -*- coding: utf-8 -*-
"""_adv_ab6.py —— tts **纯生成**（非 edit）各标注条件的 A/B 试听页。

与 _adv_ab5（edit 版）的区别：
    edit 的输出时长被源音频钉死 ⇒ 只能重新分配时间；
    tts  没有源音频 ⇒ 模型自己决定总长，可以真的变长。

每行标四个数：
    vdur   副词词内有声时长（真·发声时间）
    ×同句  该词 vdur ÷ 同句其它实词中位（相对突出度）
    F0     p75 版相对上下文抬升（半音）
    全句   整条文件里所有有声帧的总时长（判断「是真变长还是从邻词借的」）
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
OUT = os.path.join(ROOT, "_adv_ab6")
TMP = os.path.join(OUT, "mp3")
STATE = os.path.join(ROOT, "_mt_adv_state.json")
D = "_adv_tts"

# (label, 文件, prom)；prom 统一由 _prom_build.py --prefix _adv_tts 生成
CONDS = [("base", "无标签（纯复刻这一 seed）"),
         ("p6", "pitch +6 半音"),
         ("p9", "pitch +9 半音"),
         ("r7", "rate 0.70（慢）"),
         ("r6", "rate 0.60（更慢）"),
         ("rp", "rate 0.60 + pitch 6"),
         ("rp9", "rate 0.60 + pitch 9")]

GROUPS = [
    dict(uid="N0627", adv="carefully",
         note="副词在**句末**（后面是句号）。念到这里的能量天然衰减，旧测量就是在这里被假峰骗的。"),
    dict(uid="N0219", adv="nervously",
         note="副词在**句中**（后面是逗号），有自然的后续语调，是最好判断的位置。"),
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
    ts, fs, ss, dur = F.track_ex(wav)
    rows = F.read_prom(prom)
    spans = A.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    tw = A.text_words(text)
    per = {}
    for i, x in enumerate(tw):
        if not x["is_word"] or x["key"] in F.FUNC:
            continue
        sp = spans[i]
        if sp["t0"] is None:
            continue
        per[x["key"]] = float(((ts >= sp["t0"]) & (ts < sp["t1"])).sum()) * 0.005
    vt = per.get(adv)
    others = [v for k, v in per.items() if k != adv]
    med = float(np.median(others)) if others else None
    cws = P.measure_one(wav, prom, text, strict=True) or []
    hit = [c for c in cws if c["key"] == adv]
    loc = round(hit[-1]["loc"], 2) if hit else None

    # 副词词内绝对 F0（p75 与峰值），用来防「半音数漂亮但其实是假峰」
    ref = float(np.median(fs))
    sp = None
    for i, x in enumerate(tw):
        if x["is_word"] and x["key"] == adv and spans[i]["t0"] is not None:
            sp = spans[i]
            break
    f0p75 = f0peak = None
    if sp:
        sel = (ts >= sp["t0"]) & (ts < sp["t1"])
        if sel.sum() >= 3:
            f = fs[sel]
            f0p75 = int(round(float(np.percentile(f, 75))))
            f0peak = int(round(float(f.max())))
    return dict(vdur=round(vt, 3) if vt else None,
                vx=round(vt / med, 2) if (vt and med) else None,
                loc=loc, dur=round(dur, 2), speech=round(float(len(ts)) * 0.005, 2),
                f0p75=f0p75, f0peak=f0peak, ref=int(round(ref)))


def main():
    os.makedirs(OUT, exist_ok=True)
    st = json.load(open(STATE, encoding="utf-8"))["units"]
    blocks, table = [], []
    for g in GROUPS:
        uid, adv = g["uid"], g["adv"].lower()
        text = st[uid]["text"]
        rows = []
        takes = [("原交付（上一版）", "_mt_pick/%s.wav" % uid,
                  "_wpt_out/_mt_pick__%s.prom" % uid)]
        for cond, lab in CONDS:
            tag = "%s_%s_s2051" % (uid, cond)
            takes.append(("%s · %s" % (lab, cond),
                          "%s/%s.wav" % (D, tag), "_wpt_out/_adv_tts__%s.prom" % tag))
        base = None
        for label, wrel, prel in takes:
            wav, prom = os.path.join(ROOT, wrel), os.path.join(ROOT, prel)
            if not (os.path.exists(wav) and os.path.exists(prom)):
                continue
            m = metrics(wav, prom, text, adv)
            if label.endswith("base"):
                base = m
            if m["vdur"] is None:
                label += "   ⚠ 这个词在 ASR 里消失了（被吞）"
            m.update(label=label, wav=wrel, uid=uid)
            table.append(m)
            b64 = base64.b64encode(open(mp3(wrel), "rb").read()).decode()
            badges = []
            if m["vdur"]:
                badges.append("有声 <b>%.3fs</b>" % m["vdur"])
            if m["vx"]:
                badges.append("×同句 <b>%.2f</b>" % m["vx"])
            if m["loc"] is not None:
                badges.append("F0(p75) <b>%+.2f</b>" % m["loc"])
            if m["f0p75"]:
                badges.append("词内 F0 <b>%d</b>Hz（句 %d）" % (m["f0p75"], m["ref"]))
            badges.append("全句有声 <b>%.2fs</b>" % m["speech"])
            badges.append("文件 <b>%.2fs</b>" % m["dur"])
            rows.append(
                '<div class="row"><div class="lab">%s</div>'
                '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>'
                '<div class="badges">%s</div></div>'
                % (label, b64, "".join('<span class="k">%s</span>' % b for b in badges)))
        blocks.append('<section><h2>%s · <code>%s</code></h2>'
                      '<p class="note">%s</p><p class="text">%s</p>%s</section>'
                      % (uid, g["adv"], g["note"], text, "".join(rows)))

    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>tts 纯生成 + 单词级标注</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1b1f24;--mut:#5b6570;--line:#e3e7ec;--ac:#2563eb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.65 -apple-system,"Segoe UI","Noto Sans SC",sans-serif}
.wrap{max-width:920px;margin:0 auto;padding:32px 20px 80px}
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
<h1>tts 纯生成 + 单词级标注：音高 / 语速 / 两个一起</h1>
<p class="lead">这一批**不给源音频**，所以模型自己决定句子多长 —— 和上一批 edit（按源时长输出）不是一回事。</p>
<div class="hint">
<b>怎么听：</b>每组第一条是现在交付的版本，第二条是同一 seed 的无标签复刻（对照），往下依次是各种标注。<br>
<b>有声</b> = 那个词实际发声多久；<b>×同句</b> = 它 ÷ 同句其它实词的中位（相对突出度，最抗句子整体变慢的干扰）；<br>
<b>F0(p75)</b> = 词内基频 75 分位相对上下文的抬升（半音，≥2 可听）；<b>词内 F0</b> = 绝对音高，防「数字漂亮其实是假峰」；<br>
<b>全句有声</b> = 整条所有发声帧加起来 —— 它若不变而副词变长，说明是<b>从别的词借的</b>。
</div>
%BODY%
</div></body></html>""".replace("%BODY%", "".join(blocks))
    p = os.path.join(OUT, "试听-tts标注.html")
    open(p, "w", encoding="utf-8").write(html)
    json.dump(table, open(os.path.join(OUT, "_table.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("写出 %s (%.1f MB, %d 条音频)"
          % (p, os.path.getsize(p) / 1e6, html.count("data:audio/mpeg")))
    for r in table:
        print("%-7s %-30s vdur=%-6s vx=%-5s loc=%-6s F0=%sHz 全句=%.2f 文件=%.2f"
              % (r["uid"], r["label"][:30], r["vdur"], r["vx"], r["loc"],
                 r["f0p75"], r["speech"], r["dur"]))


if __name__ == "__main__":
    main()
