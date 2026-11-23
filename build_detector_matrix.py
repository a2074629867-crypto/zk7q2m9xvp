# -*- coding: utf-8 -*-
"""build_detector_matrix.py —— 出「检测器条件矩阵」：什么时候跑、什么结果可信、看不见什么。"""
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
from mt_detectors import DETECTORS  # noqa: E402

ROOT = "G:/_setup"
SCOPE = [("item", "单条（逐 take）"), ("pair", "成对（需同句对照）"),
         ("group", "组级（n≥20）"), ("batch", "批次（n≥10）")]
LV = {"veto": ("能拒收", "bad"), "warn": ("只报警", "warn"), "info": ("只记录", "dim")}

EV = {}
try:
    q = json.load(open(os.path.join(ROOT, "_qa_deg.json"), encoding="utf-8"))
    for r in q:
        for x in (r.get("det") or []):
            if x["verdict"] not in ("SKIP", "PASS"):
                EV.setdefault(x["id"], []).append(r["name"])
except Exception:  # noqa: BLE001
    pass

H = []
A = H.append
A("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>检测器条件矩阵</title>
<style>
:root{--bg:#fbfaf7;--card:#fff;--ink:#1d1c1a;--dim:#6b6862;--line:#e3ded4;
--accent:#8a6d3b;--ok:#2f6b4f;--warn:#9a5b1e;--bad:#a33a2f;--soft:#f3efe6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:40px 24px 90px}
h1{font-size:27px;font-weight:600;letter-spacing:.4px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:24px}
h2{font-size:19px;font-weight:600;margin:40px 0 12px;padding-bottom:8px;
border-bottom:1px solid var(--line)}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;
padding:13px 16px;margin:11px 0;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.card h3{margin:0 0 3px;font-size:15px;font-weight:600}
.card .id{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--dim)}
.tag{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;
border:1px solid currentColor;margin-left:6px;vertical-align:1px}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.dim{color:var(--dim)}
.row{display:grid;grid-template-columns:74px 1fr;gap:2px 10px;margin-top:7px;font-size:13px}
.row b{font-weight:600;color:var(--accent);font-size:12px;padding-top:2px}
.row span{color:var(--ink)}
.blind{color:var(--bad)}
.box{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:4px;padding:12px 16px;margin:14px 0;font-size:13.5px}
.flow{background:var(--card);border:1px solid var(--line);border-radius:6px;
padding:16px 20px;margin:14px 0;font-family:ui-monospace,Consolas,monospace;
font-size:12.5px;line-height:2.0;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;font-size:12.5px;background:var(--card);
border-radius:6px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}
th,td{padding:6px 9px;text-align:left;border-bottom:1px solid var(--line)}
th{background:var(--soft);font-size:11.5px;font-weight:600}
.foot{margin-top:46px;padding-top:13px;border-top:1px solid var(--line);
color:var(--dim);font-size:12px}
</style></head><body><div class="wrap">""")

A("<h1>检测器条件矩阵</h1>")
A('<div class="sub">%d 个检测器 · 每个都写明「什么时候才跑 / 怎么判 / 什么结果可信 / 看不见什么」'
  ' · 2026-10-31</div>' % len(DETECTORS))

A('<div class="box"><b>一句话：</b>检测器不是「开或关」，是<b>有条件才生效</b>。'
  '同一个 crest，在「末尾是数字零的 trim 文件」上会误报 151/865，'
  '在「未 trim 的原始生成」上 5/5 抓准削波。'
  '所以每条都带 <b>when</b>（前置）+ <b>valid</b>（什么时候能信）+ <b>blind</b>（它看不见什么）。</div>')

def _when(w):
    p = []
    if w.get("min_sec"):
        p.append("时长 ≥ %.1fs" % w["min_sec"])
    if w.get("min_frames"):
        p.append("≥ %d 帧" % w["min_frames"])
    if w.get("min_n"):
        p.append("n ≥ %d" % w["min_n"])
    if w.get("need"):
        p.append({"f0": "F0 可测", "ref": "有同档 ref", "text": "有参考文本",
                  "pair": "有同句对照", "nisqa": "NISQA 已跑",
                  "hf_abs": "高频绝对量 ≥ 0.02", "path": "有 wav 路径",
                  "prom": "有 .prom", "prosogram": "有 Prosogram",
                  "spk": "有声纹模型"}.get(w["need"], w["need"]))
    if w.get("order"):
        p.append("须在插停顿之前")
    if w.get("trimmed"):
        p.append("已剪插入停顿")
    return " 且 ".join(p) or "无条件"


A("<h2>决策顺序（单条 take 进回环后）</h2>")
A('<div class="flow">'
  '① 时长 &lt; 1.5s ?  → 只跑 硬切 / 吞字 / 削波，其余 SKIP\n'
  '② 有参考文本 ?     → 跑 ASR 覆盖率（cov &lt; 0.80 = 吞字，必须重生）\n'
  '③ F0 可测 ?        → 跑 压平（span_st &lt; 3.0 = 被压平）\n'
  '④ 有同档 ref ?      → 跑 音色三取二（F0 ±3st / 质心 ×0.78~1.28 / 倾斜 ±3）\n'
  '⑤ 时长 ≥ 2.0s ?    → 跑 NISQA 断流（&lt; 2.0 只记数值，不定级）\n'
  '⑥ 跳前 &gt; −50dBFS ? → 跑 硬切（否则 SKIP：那是淡出到零，听不见）\n'
  '⑦ 高频绝对量 ≥ 2%% ? → 跑 气声（否则比值型判据分母塌陷）\n'
  '─────────────────────────────────────────────\n'
  '全部条目跑完 → 组级（n≥20）出形状，批次（n≥10）出韵律分</div>')

for scope, label in SCOPE:
    items = [d for d in DETECTORS if d["scope"] == scope]
    if not items:
        continue
    A("<h2>%s</h2>" % label)
    for d in items:
        lv, cls = LV[d["level"]]
        A('<div class="card">')
        _st = d.get("status") or "?"
        _stc = "" if _st == "在跑" else ' style="opacity:.55"'
        A('<h3%s>%s<span class="tag %s">%s</span>'
          '<span class="tag dim">%s</span><span class="tag dim">%s</span></h3>'
          % (_stc, d["name"], cls, lv, d["id"], _st))
        A('<div class="id">%s</div>' % d["what"])
        A('<div class="row"><b>什么时候跑</b><span>%s</span>' % _when(d.get("when") or {}))
        A('<b>怎么判</b><span>%s</span>' % d["rule"])
        A('<b>什么可信</b><span>%s</span>' % d["valid"])
        A('<b>看不见</b><span class="blind">%s</span>' % d["blind"])
        A('<b>实测</b><span class="dim">%s</span></div>' % d["evidence"])
        if d.get("blocked"):
            A('<div class="row"><b>不可用</b><span class="blind">%s</span></div>'
              % d["blocked"])
        ev = EV.get(d["id"])
        if ev:
            A('<div class="row"><b>本次抓到</b><span class="ok">%s</span></div>'
              % "、".join(ev[:6]))
        A("</div>")


A("<h2>实测：新判据有没有溢出</h2>")
A("<table><tr><th>退化类型</th><th>报出</th><th>该由谁抓</th></tr>")
A("<tr><td>削波 clip</td><td class='ok'>FAIL 5/5</td>"
  "<td>crest_clip（阈值改到 16.0 之后；旧值 14.0 只拦 2/5）</td></tr>")
A("<tr><td>音高压平 mono</td><td class='ok'>4/5</td><td>span_flatten（新增）</td></tr>")
A("<tr><td>等响 flatamp</td><td class='dim'>1/5</td>"
  "<td>energy_span 抓不到（AUC 0.64）—— 已知失效，别指望它</td></tr>")
A("<tr><td>切碎 chop</td><td class='dim'>0/5</td><td>NISQA-DIS / 句内漂移（不在本层）</td></tr>")
A("<tr><td>挖洞 hole</td><td class='dim'>0/5</td><td>NISQA-DIS / ASR 覆盖率</td></tr>")
A("<tr><td>变速 jitter</td><td class='dim'>0/5</td><td>RDR / 句内漂移</td></tr>")
A("<tr><td>低通 lowpass</td><td class='dim'>0/5</td><td>NISQA-COL / 音色谱质心</td></tr>")
A("<tr><td>结巴 stutter</td><td class='dim'>0/5</td><td>ASR word_gate（所有 MOS 模型都失效）</td></tr>")
A("</table>")
A('<div class="box">新判据只在自己那两类上报，<b>没有把别的缺陷误报成削波/压平</b>。'
  '这就是「有条件才生效」的价值 —— 上一版没有条件时，865 条交付版被误判 151 条。</div>')

A('<div class="foot">登记表 <span style="font-family:monospace">mt_detectors.py</span>（单一来源）· '
  '接入点 <span style="font-family:monospace">mt_item_qa.py --no-det</span> 可关、'
  '<span style="font-family:monospace">mt_loop.py AUDIO_GATE</span> 控制回环内生效</div>')
A("</div></body></html>")

open(os.path.join(ROOT, "_detector_matrix.html"), "w", encoding="utf-8").write("\n".join(H))
print("wrote _detector_matrix.html  %d detectors" % len(DETECTORS))
