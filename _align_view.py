# -*- coding: utf-8 -*-
"""_align_view.py —— 把对齐数据集渲染成一页 HTML（纯内联 SVG/CSS，无外部依赖）。

    G:/Python310/python.exe _align_view.py   → _align_view.html
"""
import json
import os
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _align_lib as L

ROOT = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: os.path.join(ROOT, *p)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    d = json.load(open(L.find_data("_align_dataset.json"), encoding="utf-8"))
    bl = json.load(open(L.BASE_JSON, encoding="utf-8"))
    recs = d["records"]
    human = [r for r in recs if r["side"] == "human"]
    narr = [r for r in recs if r["side"] == "narr"]
    ref = bl["ref"]
    hz = ref["all"]["relz_sorted"]
    hl = ref["all"]["loc_sorted"]
    h50z, h90z, h95z = ref["all"]["rel_z"]["p50"], ref["all"]["rel_z"]["p90"], ref["all"]["rel_z"]["p95"]
    h50l, h90l, h95l = ref["all"]["loc"]["p50"], ref["all"]["loc"]["p90"], ref["all"]["loc"]["p95"]

    # ---------- 数据 ----------
    hpts = [(w["rel_z"], w["loc"]) for r in human for w in r["words"]
            if w.get("rel_z") is not None and w.get("loc") is not None]
    pairs = []
    for r in narr:
        hits = [w for w in r["words"] if w.get("is_adv")]
        if hits:
            pairs.append((r, hits[-1]))
    opts = [(r, w) for r, w in pairs if r["take"]["kind"] == "delivered"
            and w.get("rel_z") is not None and w.get("loc") is not None]

    # ---------- 散点 ----------
    X0, X1 = -3.0, 4.2
    Y0, Y1 = -6.0, 12.0
    W, H = 900, 430
    PL, PR, PT, PB = 62, 18, 22, 46
    iw, ih = W - PL - PR, H - PT - PB
    sx = lambda v: PL + (min(max(v, X0), X1) - X0) / (X1 - X0) * iw
    sy = lambda v: PT + ih - (min(max(v, Y0), Y1) - Y0) / (Y1 - Y0) * ih
    dots_h = "".join('<circle cx="%.1f" cy="%.1f" r="1.9" fill="#94a3b8" opacity=".34"/>'
                     % (sx(x), sy(y)) for x, y in hpts)
    dots_o = "".join('<circle cx="%.1f" cy="%.1f" r="4.4" fill="#dc2626" opacity=".78"'
                     ' stroke="#fff" stroke-width=".8"/>' % (sx(w["rel_z"]), sy(w["loc"]))
                     for _, w in opts)
    grid = []
    for xv in (-3, -2, -1, 0, 1, 2, 3, 4):
        grid.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#eef2f7"/>'
                    % (sx(xv), PT, sx(xv), PT + ih))
        grid.append('<text x="%.1f" y="%d" font-size="11" fill="#94a3b8" text-anchor="middle">%d</text>'
                    % (sx(xv), PT + ih + 16, xv))
    for yv in (-5, 0, 5, 10):
        grid.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f7"/>'
                    % (PL, sy(yv), PL + iw, sy(yv)))
        grid.append('<text x="%d" y="%.1f" font-size="11" fill="#94a3b8" text-anchor="end">%d</text>'
                    % (PL - 8, sy(yv) + 4, yv))
    scatter = """<svg viewBox="0 0 %d %d" class="chart" role="img" aria-label="真人词与我们副词的 rel_z 与 loc 分布">
<rect x="%d" y="%d" width="%d" height="%d" fill="#fcfdff" stroke="#e5e7eb"/>
%s
<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#f59e0b" stroke-dasharray="5 4"/>
<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#f59e0b" stroke-dasharray="5 4" opacity=".7"/>
%s%s
<text x="%d" y="%d" font-size="12" fill="#475569" text-anchor="middle">相对时长 rel_z（音节校正，越大越像「拖长重读」）</text>
<text x="14" y="%d" font-size="12" fill="#475569" transform="rotate(-90 14 %d)" text-anchor="middle">音高 loc（半音）</text>
<g font-size="11.5">
<circle cx="%d" cy="%d" r="4" fill="#94a3b8" opacity=".5"/><text x="%d" y="%d" fill="#475569">真人词（%d）</text>
<circle cx="%d" cy="%d" r="4.4" fill="#dc2626" opacity=".8"/><text x="%d" y="%d" fill="#475569">我们交付版副词（%d）</text>
</g>
</svg>""" % (W, H, PL, PT, iw, ih, "".join(grid),
             sx(h50z), PT, sx(h50z), PT + ih,
             PL, sy(h50l), PL + iw, sy(h50l),
             dots_h, dots_o,
             PL + iw // 2, H - 10,
             PT + ih // 2, PT + ih // 2,
             PL + iw - 250, PT - 6, PL + iw - 236, PT - 2, len(hpts),
             PL + iw - 250, PT + 12, PL + iw - 236, PT + 16, len(opts))

    # ---------- 分组 ----------
    by_kind = defaultdict(list)
    for r, w in pairs:
        by_kind[r["take"]["kind"]].append(w)
    gnames = [("delivered", "交付版"), ("cand", "标签版候选"), ("ctl", "无标签对照"),
              ("tts", "tts 实验"), ("edit", "edit 实验"), ("prev", "历史交付")]
    grow = []
    for k, label in gnames:
        v = by_kind.get(k) or []
        if not v:
            continue
        z = [w["rel_z"] for w in v if w.get("rel_z") is not None]
        lo = [w["loc"] for w in v if w.get("loc") is not None]
        gbar = min(100, max(0, 100 * (st.median(z) - X0) / (X1 - X0))) if z else 0
        grow.append('<div class="g"><div class="gn">%s<em>n=%d</em></div>'
                    '<div class="gb"><i style="width:%.1f%%"></i></div>'
                    '<div class="gv">rel_z <b>%+.2f</b> · 分位 <b>%.0f</b>'
                    ' ｜ loc <b>%+.2f</b> · 分位 <b>%.0f</b></div></div>'
                    % (label, len(z), gbar, st.median(z) if z else 0,
                       st.median([L.pct_of(x, hz) for x in z]) if z else 0,
                       st.median(lo) if lo else 0,
                       st.median([L.pct_of(x, hl) for x in lo]) if lo else 0))

    # ---------- 表 ----------
    trows = []
    for r, w in pairs:
        if r["take"]["kind"] != "delivered":
            continue
        trows.append(dict(
            uid=r["uid"], adv=r["adv"], nsyl=w["nsyl"],
            pos="句末" if w.get("last") else "句中",
            rel=w["rel"], relz=w["rel_z"] or 0,
            pz=L.pct_of(w["rel_z"], hz) or 0,
            loc=w["loc"] or 0, pl=L.pct_of(w["loc"], hl) or 0,
            rank=w["rank"], n=r["n_content"],
            flag="低上下文" if r["low_context"] else "",
            judge=""))
    st_ = {}
    try:
        st_ = json.load(open(L.find_data("_mt_adv_state.json"), encoding="utf-8"))["units"]
    except Exception:
        pass
    for t in trows:
        x = st_.get(t["uid"]) or {}
        t["judge"] = x.get("judge") or ""
        t["m2loc"] = ((x.get("m2") or {}).get("loc"))
    trows.sort(key=lambda t: t["relz"])
    trs = "".join(
        '<tr data-z="%.2f" data-l="%.2f"><td class="mono">%s</td><td>%s</td><td class="c">%d</td>'
        '<td class="c">%s</td><td class="c">%.2f</td><td class="c %s">%+.2f</td><td class="c">%.0f</td>'
        '<td class="c %s">%+.2f</td><td class="c">%.0f</td><td class="c">%d/%d</td><td class="c">%s</td></tr>'
        % (t["relz"], t["loc"], t["uid"], esc(t["adv"]), t["nsyl"], t["pos"],
           t["rel"], "bad" if t["relz"] < -0.5 else "", t["relz"], t["pz"],
           "bad" if t["loc"] < 1.0 else "", t["loc"], t["pl"],
           t["rank"], t["n"], t["flag"] or "&nbsp;")
        for t in trows)

    n_deliv = len(opts)
    med_z = st.median([w["rel_z"] for _, w in opts])
    med_pz = st.median([L.pct_of(w["rel_z"], hz) for _, w in opts])
    med_l = st.median([w["loc"] for _, w in opts])
    med_pl = st.median([L.pct_of(w["loc"], hl) for _, w in opts])

    html = TEMPLATE
    reps = {
        "__NH__": "%d" % len(human), "__NHS__": "%d" % sum(r["n_content"] for r in human),
        "__NN__": "%d" % len(narr), "__NNS__": "%d" % sum(r["n_content"] for r in narr),
        "__ND__": "%d" % n_deliv,
        "__MZ__": "%+.2f" % med_z, "__MPZ__": "%.0f" % med_pz,
        "__ML__": "%+.2f" % med_l, "__MPL__": "%.0f" % med_pl,
        "__H50Z__": "%+.2f" % h50z, "__H90Z__": "%+.2f" % h90z,
        "__H50L__": "%+.2f" % h50l, "__H90L__": "%+.2f" % h90l,
        "__TOPRZ__": "%+.2f" % ref["top_rel"]["rel_z"]["p50"],
        "__TOPRL__": "%+.2f" % ref["top_rel"]["loc"]["p50"],
        "__TOPLZ__": "%+.2f" % ref["top_loc"]["rel_z"]["p50"],
        "__TOPLL__": "%+.2f" % ref["top_loc"]["loc"]["p50"],
        "__BUILT__": esc(d["built"]),
        "__SCATTER__": scatter, "__GROUPS__": "".join(grow), "__ROWS__": trs,
    }
    for k, v in reps.items():
        html = html.replace(k, v)
    open(J("_align_view.html"), "w", encoding="utf-8").write(html)
    print("→ _align_view.html (%.0f KB)" % (len(html) / 1024))


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>旁白 ↔ 真人 对齐</title>
<style>
:root{--ink:#14181f;--mut:#64748b;--line:#e2e8f0;--bg:#f7f8fa;--card:#fff;--acc:#dc2626;--ok:#059669;--warn:#f59e0b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.65 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1060px;margin:0 auto;padding:34px 22px 70px}
h1{font-size:25px;margin:0 0 6px;letter-spacing:-.3px}
h2{font-size:17px;margin:42px 0 12px;padding-bottom:7px;border-bottom:1px solid var(--line)}
.lead{color:var(--mut);font-size:13.5px;margin:0 0 22px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0 6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 15px}
.card .k{font-size:12px;color:var(--mut);letter-spacing:.2px}
.card .v{font-size:23px;font-weight:650;margin-top:3px;letter-spacing:-.5px}
.card .s{font-size:11.5px;color:var(--mut);margin-top:2px}
.card.hi .v{color:var(--acc)}
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:14px 0}
.chart{width:100%;height:auto;display:block}
.g{display:grid;grid-template-columns:104px 1fr 360px;align-items:center;gap:12px;padding:7px 0;border-bottom:1px dashed var(--line)}
.g:last-child{border:0}
.gn{font-size:13.5px}.gn em{font-style:normal;color:var(--mut);font-size:11.5px;margin-left:6px}
.gb{height:8px;background:#eef2f7;border-radius:5px;overflow:hidden}
.gb i{display:block;height:100%;background:linear-gradient(90deg,#fca5a5,#dc2626)}
.gv{font-size:12px;color:var(--mut);text-align:right;white-space:nowrap}
.gv b{color:var(--ink);font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card)}
th,td{padding:6px 7px;border-bottom:1px solid #eef2f7;text-align:left}
th{font-size:11.5px;color:var(--mut);font-weight:600;cursor:pointer;user-select:none;white-space:nowrap;
  background:#fafbfc;position:sticky;top:0}
th:hover{color:var(--ink)}
tbody tr:hover{background:#fff8f8}
.c{text-align:center}.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--mut)}
.bad{color:var(--acc);font-weight:600}
.note{font-size:12.5px;color:var(--mut);background:#fffdf5;border:1px solid #fde68a;
  border-radius:10px;padding:11px 14px;margin:14px 0}
.note b{color:#92400e}
ul{margin:8px 0 0 0;padding-left:20px}li{margin:4px 0;font-size:13.5px}
.small{font-size:12px;color:var(--mut)}
</style></head><body><div class="wrap">

<h1>旁白 ↔ 真人（马修《Wonder》母带）对齐</h1>
<p class="lead">同一测量核、同一字段、同一 <code>rel</code> 定义。构建于 __BUILT__。
点击表头可排序。</p>

<div class="cards">
  <div class="card"><div class="k">真人基准</div><div class="v">__NH__ 句</div><div class="s">__NHS__ 个内容词</div></div>
  <div class="card"><div class="k">我们的 take</div><div class="v">__NN__ 条</div><div class="s">__NNS__ 个内容词</div></div>
  <div class="card hi"><div class="k">交付版 rel_z 中位</div><div class="v">__MZ__</div><div class="s">真人分位 __MPZ__</div></div>
  <div class="card"><div class="k">交付版 loc 中位</div><div class="v">__ML__</div><div class="s">真人分位 __MPL__</div></div>
</div>

<h2>一、一张图看清我们站在哪</h2>
<p class="lead">每点是一个词：横轴 = 相对时长（音节校正后），纵轴 = 音高相对本地上下文。
橙虚线是真人中位（rel_z __H50Z__ ／ loc __H50L__）。真人被强调的词分两簇 ——
「拖长」往右走，「抬高」往上走，两者几乎不重叠。</p>
<div class="panel">__SCATTER__</div>
<div class="note"><b>读法：</b>我们的红点整体贴在<b>上半部</b>（音高够），横轴却压在橙线附近（时长不够）。
真人「句内最长词」的 rel_z 中位是 <b>__TOPRZ__</b>、「句内最高音词」的 loc 中位是 <b>__TOPLL__</b> ——
我们只做到了后者的形态。</div>

<h2>二、分组对比</h2>
<p class="lead">条形 = rel_z 中位在 −3.0~4.2 区间内的位置。右列同时给 rel_z 与 loc 的真人分位。</p>
<div class="panel">__GROUPS__</div>

<h2>三、逐单元（交付版 __ND__ 条）</h2>
<p class="lead">默认按 rel_z 升序，最"没时长"的排在最前。红色 = rel_z &lt; −0.5 或 loc &lt; 1.0。</p>
<div class="panel" style="padding:0;overflow:hidden">
<table id="t"><thead><tr>
<th data-i="0">单元</th><th data-i="1">副词</th><th data-i="2">音节</th><th data-i="3">位置</th>
<th data-i="4">rel</th><th data-i="5">rel_z</th><th data-i="6">真人分位</th>
<th data-i="7">loc</th><th data-i="8">真人分位</th><th data-i="9">名次</th><th data-i="10">备注</th>
</tr></thead><tbody>__ROWS__</tbody></table></div>

<h2>四、口径</h2>
<ul>
<li><code>rel</code> = 词 sps ÷ <b>句内全部内容词 sps 中位（含自身）</b>。sps = 词时长 ÷ 音节数（CMU 词典）。</li>
<li><code>rel_z</code> = <code>(log(rel) − 0.2041 + 0.4339·log(nsyl)) / 0.3575</code>，系数只用真人 931 词拟合。</li>
<li><code>loc</code> = 词内 F0 p75 − 前后 ±1.2s（排除自身）F0 中位，单位半音。两侧同一函数，可直接比。</li>
<li>真人侧过滤：漏词（|原文−ASR| &gt; 1）、内容词 &lt; 4、任一词 sps &gt; 3×句中位。旁白侧不套这三条，
      质量用 <code>synthetic_share</code> 与「低上下文」标记暴露。</li>
</ul>
<p class="small">数据：<code>_align_dataset.json</code> / <code>_align_words.csv</code>（一行一个词）/
<code>_align_takes.csv</code> / <code>_align_report.md</code></p>
</div>
<script>
document.querySelectorAll('#t th').forEach(function(th){
  th.addEventListener('click',function(){
    var tb=document.querySelector('#t tbody'), rows=[].slice.call(tb.rows), i=+th.dataset.i;
    var num=i>=2&&i<=9, dir=th.dataset.d==='asc'?-1:1;
    document.querySelectorAll('#t th').forEach(function(o){o.dataset.d=''});
    th.dataset.d=dir===1?'asc':'desc';
    rows.sort(function(a,b){
      var x=a.cells[i].textContent.trim(), y=b.cells[i].textContent.trim();
      if(num){x=parseFloat(x)||0;y=parseFloat(y)||0;return (x-y)*dir}
      return x.localeCompare(y)*dir;
    });
    rows.forEach(function(r){tb.appendChild(r)});
  });
});
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
