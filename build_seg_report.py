# -*- coding: utf-8 -*-
"""build_seg_report.py —— 句内漂移检测的可视化报告。

为什么必须可视化：
  窗级参数是 4 条时间序列（F0 / 谱质心 / HNR / RMS），只看表格看不出「哪一段掉了」。
  人耳复核需要知道「第几秒、哪个参数掉了多少」，否则 59 条要一条条听。

用法：
  G:/Python310/python.exe build_seg_report.py --dir ch123_final --name "edit+emo 对白"
  G:/Python310/python.exe build_seg_report.py --dir _mt_trim_ch1_s42 --limit 40 --name "正常旁白"
  G:/Python310/python.exe build_seg_report.py --json a.json,b.json --out _seg_report.html
"""
import argparse
import glob
import html
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
import mt_seg_drift as D

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f7f7f5;color:#1b1b1b;
 font:14px/1.6 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:22px;margin:0 0 4px;font-weight:600}
h2{font-size:16px;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid #e2e2dd}
.sub{color:#6b6b66;font-size:13px;margin-bottom:20px}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 8px}
.kpi div{background:#fff;border:1px solid #e2e2dd;border-radius:8px;padding:10px 14px;min-width:104px}
.kpi b{display:block;font-size:20px;font-weight:600;line-height:1.2}
.kpi span{color:#6b6b66;font-size:12px}
.box{border-radius:8px;padding:12px 14px;margin:14px 0;font-size:13px;line-height:1.65}
.box.warn{background:#fff8e6;border:1px solid #f0dca8}
.box.bad{background:#fdecea;border:1px solid #f3c2bd}
.box.ok{background:#eef7ee;border:1px solid #c6e2c6}
.box code{background:rgba(0,0,0,.06);padding:1px 5px;border-radius:3px;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px;background:#fff;
 border:1px solid #e2e2dd;border-radius:8px;overflow:hidden}
th{background:#f0f0ec;text-align:left;padding:8px 10px;font-weight:600;font-size:12px;color:#4a4a46}
td{padding:8px 10px;border-top:1px solid #ececE7;vertical-align:top}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.card{background:#fff;border:1px solid #e2e2dd;border-radius:10px;padding:14px 16px;margin:12px 0}
.card.fail{border-left:4px solid #c0392b}
.card.warn{border-left:4px solid #d39e00}
.card.pass{border-left:4px solid #2e7d32}
.hd{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.hd b{font-size:14px}
.tag{font-size:11px;padding:1px 7px;border-radius:10px;background:#eee;color:#555}
.tag.fail{background:#c0392b;color:#fff}.tag.warn{background:#d39e00;color:#fff}
.tag.pass{background:#2e7d32;color:#fff}
.txt{color:#555;font-size:12px;margin:4px 0 8px}
svg{display:block;width:100%;height:auto}
.lbl{font-size:10px;fill:#8a8a84}
audio{width:100%;height:30px;margin-top:8px}
.ev{font-size:12px;color:#8a3a30;margin-top:6px}
.foot{margin-top:40px;color:#8a8a84;font-size:12px;line-height:1.7}
"""


def mini(ws, key, color, unit, W=980, H=52, evt=None):
    """一个参数的窗级折线（含事件竖线）。"""
    vals = [(w["t0"] + D.WIN / 2, w.get(key)) for w in ws]
    vv = [v for _, v in vals if v is not None and np.isfinite(v)]
    if len(vv) < 2:
        return "<div class='lbl'>%s: 无数据</div>" % key
    lo, hi = min(vv), max(vv)
    if hi - lo < 1e-6:
        hi = lo + 1
    pad = (hi - lo) * 0.15
    lo, hi = lo - pad, hi + pad
    tmax = max(t for t, _ in vals) or 1
    t0 = min(t for t, _ in vals)

    def X(t):
        return 42 + (t - t0) / max(1e-6, tmax - t0) * (W - 52)

    def Y(v):
        return H - 8 - (v - lo) / (hi - lo) * (H - 16)

    pts, seg = [], []
    for t, v in vals:
        if v is None or not np.isfinite(v):
            if pts:
                seg.append(pts)
            pts = []
            continue
        pts.append("%.1f,%.1f" % (X(t), Y(v)))
    if pts:
        seg.append(pts)
    lines = "".join("<polyline fill='none' stroke='%s' stroke-width='1.6' points='%s'/>"
                    % (color, " ".join(s)) for s in seg if len(s) > 1)
    evl = ""
    if evt:
        for e in evt:
            x = X(e["t"])
            c = "#c0392b" if e["level"] == "FAIL" else "#d39e00"
            evl += ("<line x1='%.1f' y1='4' x2='%.1f' y2='%d' stroke='%s' "
                    "stroke-width='1' stroke-dasharray='2,2'/>" % (x, x, H - 4, c))
    return ("<div style='position:relative'>"
            "<svg viewBox='0 0 %d %d' preserveAspectRatio='none'>"
            "<text class='lbl' x='0' y='%d'>%s</text>"
            "<text class='lbl' x='0' y='12'>%.0f</text>"
            "<text class='lbl' x='0' y='%d'>%.0f</text>"
            "%s%s</svg></div>" % (W, H, H - 2, unit, hi, H - 12, lo, lines, evl))


def card(r, name_map):
    v = r["verdict"]
    cls = {"FAIL": "fail", "WARN": "warn", "PASS": "pass"}.get(v, "")
    nm = name_map.get(r["file"], {})
    who = nm.get("who", "")
    txt = nm.get("text", "")
    sp = r.get("span") or {}
    o = ["<div class='card %s'>" % cls]
    o.append("<div class='hd'><b>%s</b><span class='tag %s'>%s</span>"
             "<span class='tag'>%.2fs</span><span class='tag'>%d 窗</span>"
             "%s</div>"
             % (html.escape(os.path.basename(r["file"])), cls, v, r["dur"],
                r.get("n_win", 0),
                ("<span class='tag'>%s</span>" % html.escape(who)) if who else ""))
    if txt:
        o.append("<div class='txt'>%s</div>" % html.escape(txt[:150]))
    if sp:
        o.append("<div class='txt'>F0 中位 %.0f Hz · 句内跨度 %.1f 半音 (%.0f Hz)"
                 " · 双音区 %s</div>"
                 % (sp.get("f0_med", 0), sp.get("span_st") or 0, sp.get("span_hz") or 0,
                    ("%.1f 半音 [%.0f↔%.0f]" % (sp["gap_st"], sp["gap_lo"], sp["gap_hi"]))
                    if sp.get("gap_st") is not None else "未检出"))
    ev = r.get("events") or []
    o.append(mini(r["windows"], "f0", "#2b6cb0", "F0 Hz", evt=ev))
    o.append(mini(r["windows"], "cen", "#805ad5", "谱质心"))
    o.append(mini(r["windows"], "hnr", "#2f855a", "HNR dB"))
    o.append(mini(r["windows"], "rms", "#c05621", "RMS dB"))
    for e in ev[:4]:
        o.append("<div class='ev'>%s @%.2fs — %s</div>"
                 % (e["level"], e["t"], html.escape(" / ".join(e["why"]))))
    o.append("<audio controls preload='none' src='%s'></audio>"
             % html.escape(r["file"].replace("\\", "/")))
    o.append("</div>")
    return "".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--plan", default="", help="可选：{uid:{who,text}} 用来显示角色与台词")
    ap.add_argument("--name", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="_seg_report.html")
    a = ap.parse_args()

    name_map = {}
    if a.plan and os.path.exists(a.plan):
        d = json.load(open(a.plan, encoding="utf-8"))
        if isinstance(d, dict):
            name_map = {k: v for k, v in d.items() if isinstance(v, dict)}

    res = []
    if a.dir:
        files = sorted(glob.glob(os.path.join(a.dir, "*.wav")))
        if a.limit:
            files = files[:a.limit]
        for p in files:
            try:
                res.append(D.one(p))
            except Exception as e:  # noqa: BLE001
                print("ERR", p, e, file=sys.stderr)
    elif a.json:
        for p in a.json.split(","):
            res += json.load(open(p.strip(), encoding="utf-8"))
    if not res:
        print("没有数据", file=sys.stderr)
        return 2

    from collections import Counter
    cnt = Counter(r["verdict"] for r in res)
    order = {"FAIL": 0, "WARN": 1, "INSUFFICIENT": 2, "PASS": 3, "ERROR": 4}
    res.sort(key=lambda r: (order.get(r["verdict"], 9), r["file"]))

    o = ["<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
         "<title>句内音色漂移检测</title><style>%s</style></head><body><div class='wrap'>" % CSS,
         "<h1>句内音色漂移检测</h1>",
         "<div class='sub'>%s · %d 条 · 窗长 %.2fs / 步长 %.2fs</div>"
         % (html.escape(a.name or a.dir or a.json), len(res), D.WIN, D.HOP)]

    o.append("<div class='kpi'>")
    for k, lab in (("FAIL", "FAIL 疑似突变"), ("WARN", "WARN 待复核"),
                   ("PASS", "PASS"), ("INSUFFICIENT", "素材不足")):
        o.append("<div><b>%d</b><span>%s</span></div>" % (cnt.get(k, 0), lab))
    o.append("</div>")

    o.append("<div class='box warn'><b>判据与验证现状（必须说清）</b><br>"
             "阈值由 <code>_calib_seg.py</code> 在 180 条已交付旁白（已知干净）的"
             "<b>零分布</b>上定：<code>|ΔF0| p99 5.46 半音</code>、"
             "<code>HNR 降 p99 14.62 dB</code>、<code>|ΔRMS| p99 8.38 dB</code>。"
             "第一版阈值（3.0 / 8 / 10）全部落在正常噪声里，180 条误判 101 条。<br>"
             "<b>持续性规则</b>：孤立事件只记 WARN —— 正常句子的异常都是瞬时的"
             "（词尾气声），实测 180 条里 FAIL 的句子全部只有 1 个孤立事件。"
             "但<b>气声化例外</b>：HNR 塌 ≥15dB 单次即判，因为它就是「音色消失」。<br>"
             "<b>已验证</b>：正常批次误报 8%（15/180）；对白批次 FAIL 7%（4/59）。<br>"
             "<b>未验证</b>：<b>没有「句内音色剧变」的真实坏样本</b>，所以"
             "<b>检出率无法给出</b>。L088（记录在案的拆句四段 304/218/179/145Hz）"
             "合并成成品后 F0 序列与修复版几乎一致，不能当坏样本。"
             "要真正确认，需要一次带 emo 标签的生成，与无标签组对照。</div>")

    o.append("<h2>逐条明细（FAIL → WARN → PASS）</h2>")
    for r in res:
        o.append(card(r, name_map))

    o.append("<div class='foot'>F0 范围自适应：旁白（成人男低音 73Hz）用 60-300，"
             "对白（童声 173~395Hz）用 90-450。写死范围会让旁白测不到"
             "（100-400 只测到 1/569 帧）、童声锁 2 倍频（240→480）。<br>"
             "能量只取浊音帧：正常词间停顿 0.2~0.5s 会让全帧 RMS 掉 20dB+，"
             "全帧口径把正常停顿误报成「能量塌」。<br>"
             "谱质心对元音极敏感（/i/ 与 /u/ 差 2 倍），所以它<b>不能单独当音色判据</b>，"
             "只做联合条件。</div>")
    o.append("</div></body></html>")

    open(a.out, "w", encoding="utf-8").write("".join(o))
    print("->", a.out, "| 判定", dict(cnt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
