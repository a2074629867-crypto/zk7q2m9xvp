# -*- coding: utf-8 -*-
"""_adv_ab8.py —— 本轮批量回环的 A/B 页（采纳前生成）。

必须**在 --adopt 之前**跑：adopt 会覆盖 `_mt_pick/<uid>.wav`，之后就拿不到「改之前」的那版了。

三列固定顺序：
    ① 现在交付的版本（改之前）
    ② 同一 seed 的无标签复刻（对照）
    ③ ★ 新候选（带单词级标签）

中间那列是必须的：tts 是重新生成，换 take 本身就有差异，
没有对照列就分不清「标签起了作用」还是「只是抽到了另一个 take」。
"""
import argparse
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
import mt_adv_fix as M

ROOT = "G:/_setup"
FF = "E:/tool/oopz/ffmpeg.exe"
OUT = os.path.join(ROOT, "_adv_ab8")
TMP = os.path.join(OUT, "mp3")
STATE = os.path.join(ROOT, "_mt_adv_state.json")


def mp3(src):
    """转 mp3。★ 缓存名必须带来源目录，否则 `_mt_pick/N0194.wav` 与
    `_mt_adv_ctl_2041/N0194.wav`、`_mt_adv_s2041/N0194.wav` 会同名，
    三列等于放同一段音频 —— 试听页直接失效（本轮踩过）。"""
    os.makedirs(TMP, exist_ok=True)
    tag = os.path.basename(os.path.dirname(src.replace("\\", "/"))) or "root"
    p = os.path.join(TMP, "%s-%s.mp3" % (tag, os.path.basename(src)[:-4]))
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
    loc = round(hit[-1]["loc"], 2) if hit and hit[-1]["loc"] is not None else None
    return dict(vdur=round(float(sel.sum()) * 0.005, 3),
                span=round(float(t1) - float(t0), 2),
                speech=round(float(keep.sum()) * 0.005, 2),
                dur=round(float(F.track(wav)[2]), 2),
                loc=loc,
                peak=round(float(fs[sel].max()), 0) if sel.sum() else None)


PREV_DIR = os.path.join(ROOT, "_mt_pick_prev")


def prev_pair(uid):
    """改之前那一版。优先用 _mt_pick_prev（采纳前备份），否则退回 _mt_pick。"""
    pw = os.path.join(PREV_DIR, uid + ".wav")
    pp = os.path.join(ROOT, "_wpt_out", "_mt_pick_prev__%s.prom" % uid)
    if os.path.exists(pw) and os.path.exists(pp):
        return pw, pp
    return (os.path.join(ROOT, "_mt_pick", uid + ".wav"),
            os.path.join(ROOT, "_wpt_out", "_mt_pick__%s.prom" % uid))


def best_attempt(x):
    """本轮回环产生的、闸门全过且判定 PASS 的 attempt。

    ★ 已采纳过的条目必须优先返回 `active` 绑定的那一版 ——
      否则会拿另一条 PASS 候选去和「已换成 active 的交付版」对比，
      页面就会出现「③ 和 ① 不同源、徽标还显示待判」的错位（N0239 踩过）。
    """
    ok = [a for a in (x.get("attempts") or [])
          if a.get("judge") in ("PASS", "WATCH")
          and (a.get("guards") or {}).get("verdict") == "OK"
          and a.get("cond")]
    if not ok:
        return None
    # PASS 优先，其次 F0 高的
    ok.sort(key=lambda z: (z.get("judge") == "PASS", z.get("loc") or -9.0))
    act = (x.get("active") or {}).get("seed")
    if act:
        same = [a for a in ok if str(a.get("seed")) == str(act)]
        if same:
            return same[-1]
    return ok[-1]


def _parse_units(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", default="", help="逗号分隔，默认全部")
    a = ap.parse_args()
    only = set(_parse_units(a.units)) or None
    st = json.load(open(STATE, encoding="utf-8"))["units"]
    os.makedirs(OUT, exist_ok=True)
    blocks, n_ok = [], 0
    for uid in sorted(st):
        if only and uid not in only:
            continue
        x = st[uid]
        at = best_attempt(x)
        if not at:
            continue
        text, adv = x["text"], x["adv"].lower()
        seed = at.get("seed")
        prom = os.path.join(ROOT, "_mt_adv_prom_%s" % seed, uid + ".prom")
        cprom = os.path.join(ROOT, "_mt_adv_prom_ctl_%s" % seed, uid + ".prom")
        rows = [
            ("① 改之前（原交付）", *prev_pair(uid), "old"),
            ("② 同 seed 无标签（对照）", at["ctl_wav"], cprom, "ctl"),
            ("★ ③ 新候选 · %s" % at.get("cond"), at["wav"], prom, "new"),
        ]
        cards, stats = [], []
        for label, w, p, kind in rows:
            if not (os.path.exists(w) and os.path.exists(p)):
                cards.append('<div class="row"><div class="lb">%s</div>'
                             '<div class="mut">缺文件</div></div>' % label)
                continue
            s = stat(w, p, text, adv)
            stats.append((kind, s))
            badges = ""
            if s:
                badges = ('<div class="badges">'
                          '<span class="k">副词有声 <b>%.3fs</b></span>'
                          '<span class="k">全句有声 <b>%.2fs</b></span>'
                          '<span class="k">F0(p75) <b>%s</b></span>'
                          '<span class="k">峰值 <b>%sHz</b></span>'
                          '</div>' % (s["vdur"], s["speech"],
                                      "—" if s["loc"] is None else "%+.2f" % s["loc"],
                                      "—" if s["peak"] is None else "%.0f" % s["peak"]))
            cards.append(
                '<div class="row%s"><div class="lb">%s</div>'
                '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>'
                '%s</div>' % (" hl" if kind == "new" else "", label, b64(mp3(w)), badges))

        g = at.get("guards") or {}
        delta = ""
        if len(stats) >= 3:
            o, c, n = (s for _, s in stats)
            if o and c and n:
                dv = n["vdur"] / max(o["vdur"], 1e-6)
                ds = n["speech"] / max(o["speech"], 1e-6)
                spn = n["span"] / max(o["span"], 1e-6)
                dc = n["vdur"] / max(c["vdur"], 1e-6)
                dcsp = n["span"] / max(c["span"], 1e-6)
                dl = (n["loc"] or 0) - (c["loc"] or 0)
                verdict = "F0 轴：比对照 %+.1f 半音" % dl
                if abs(dl) >= 2.0:
                    verdict += "（落差显著）"
                else:
                    verdict += "（在 2.0 噪声带内，判不出）"
                if dl < 0:
                    verdict += " → ③ 反而更平"
                delta = ("副词跨度 ×%.2f／有声 ×%.2f · 全句 ×%.2f ｜ ③ vs ②：跨度 ×%.2f 有声 ×%.2f"
                         " ｜ %s ｜ %s"
                         % (spn, dv, ds, dcsp, dc, verdict, at.get("by") or ""))
        adopted = (x.get("active") or {}).get("seed")
        adopted = bool(adopted) and str(adopted) == str(seed)
        blocks.append((adopted, uid,
            '<section><h2>%s&nbsp;<code>%s</code>&nbsp;'
            '<span class="tag">%s</span><span class="tag">seed %s</span>'
            '<span class="%s">%s</span></h2>'
            '<p class="txt">%s</p>%s%s</section>'
            % (uid, x["adv"], M.adv_position(text, adv), seed,
               "ok" if adopted else "hold", "已采纳" if adopted else "待判",
               text,
               "".join(cards),
               ('<div class="dlt">%s</div>' % delta) if delta else "")))
        n_ok += 1

    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>本轮回环采纳清单</title>
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
.ok,.hold{font-size:11.5px;font-weight:700;padding:1px 9px;border-radius:20px;margin-left:auto}
.ok{color:#065f46;background:#d1fae5;border:1px solid #6ee7b7}
.hold{color:#92400e;background:#fef3c7;border:1px solid #fcd34d}
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
.dlt{margin-top:10px;font-size:12.5px;color:var(--acc);background:#f0fdfa;
     border:1px dashed #99f6e4;border-radius:6px;padding:5px 9px}
.mut{color:var(--mut);font-size:13px}
</style></head><body><div class="wrap">
<h1>本轮回环采纳清单</h1>
<p class="lead">共 __N__ 条通过闸门。绿灯 <b>已采纳</b> 写进了交付目录；黄灯 <b>待判</b>
只通过「跨度」轴，证据不足，没动交付文件，等你听完决定。</p>
<div class="hint">
<b>① 改之前</b>（现在在播的）→ <b>② 同 seed 无标签复刻</b>（对照）→ <b>★ ③ 新候选</b>。<br>
<b>为什么要有第二列：</b>tts 是重新生成，换 take 本身就有差异；没有对照就分不清
「标签起作用」还是「抽到了另一个 take」。<br>
<b>听的时候重点听：</b>那个副词是不是真的更重、<b>被压的邻词有没有变急促</b>、还是不是同一个人在念。<br>
<b>黄灯那几条为什么没自动收：</b>它们只在「跨度」轴上过线（×1.44~×1.80），
而 span 比的换-take 噪声 p95 = 1.44、最大 1.80（n=46 对纯无标签 take）——
过线值正好压在噪声上沿，分不清是标签起作用还是抽到了另一个 take；
<b>F0 轴那几条才是有把握的</b>（比对照高 2.0~5.4 半音，噪声底 1.8）。
</div>
%BODY%
</div></body></html>""".replace("%BODY%", "".join(b for _, _, b in
                 sorted(blocks, key=lambda t: (not t[0], t[1])))).replace("__N__", str(n_ok))

    p = os.path.join(OUT, "本轮采纳清单.html")
    open(p, "w", encoding="utf-8").write(html)
    print("写出 %s（%d 条单元，%d 段音频）"
          % (p, n_ok, html.count("data:audio/mpeg;base64")))


if __name__ == "__main__":
    main()
