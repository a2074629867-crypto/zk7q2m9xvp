# -*- coding: utf-8 -*-
"""_proso_view.py —— Prosogram glissando 层的对照页（纯内联 CSS，无外部依赖）。

    G:/Python310/python.exe _proso_view.py   -> _proso_view.html
"""
import json
import math
import os
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: os.path.join(ROOT, *p)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pct_at(v, p):
    v = sorted(v)
    if not v:
        return None
    i = (len(v) - 1) * p
    lo = int(i)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def rate(rows):
    return 100.0 * sum(1 for w in rows if w["n_move"] > 0) / len(rows) if rows else 0.0


def bar(name, sub, pct, vmax, color, note):
    w = max(0.0, min(100.0, 100.0 * pct / vmax))
    return ('<div class="g"><div class="gn">%s<em>%s</em></div>'
            '<div class="gb"><i style="width:%.1f%%;background:%s"></i></div>'
            '<div class="gv">%s</div></div>' % (name, sub, w, color, note))


def main():
    d = json.load(open(J("_proso.json"), encoding="utf-8"))
    T, W, N, P = d["takes"], d["words"], d["nuclei"], d["profiles"]
    byt = defaultdict(list)
    for w in W:
        byt[w["tid"]].append(w)
    nuc = defaultdict(list)
    for x in N:
        nuc[x["tid"]].append(x)

    # ---------- 真人三组 ----------
    top_rz, top_loc, rest = [], [], []
    for tid, ws in byt.items():
        if not ws or ws[0]["side"] != "human":
            continue
        ok = [w for w in ws if w.get("rel_z") is not None and w.get("loc") is not None and w["n_nuclei"]]
        if len(ok) < 4:
            continue
        a = max(ok, key=lambda w: w["rel_z"])
        b = max(ok, key=lambda w: w["loc"])
        top_rz.append(a)
        top_loc.append(b)
        rest.extend([w for w in ok if w is not a and w is not b])

    # ---------- 各组 lift ----------
    groups = []
    for k, lab in (("delivered", "交付版"), ("cand", "候选"), ("ctl", "对照"),
                   ("tts", "tts"), ("edit", "edit")):
        g = [w for w in W if w["kind"] == k]
        adv = [w for w in g if w["is_adv"]]
        oth = [w for w in g if not w["is_adv"]]
        if not adv:
            continue
        groups.append((lab, len(adv), rate(adv), rate(oth), len(oth)))

    # ---------- 配对 ----------
    def unit_of(gid):
        parts = (gid or "").split(":")
        return parts[1] if len(parts) > 1 else gid

    idx = defaultdict(dict)
    for t in T:
        if t["side"] == "narr":
            idx[(unit_of(t["gid"]), t["seed"])][t["kind"]] = t
    pairs = [(v["cand"], v["ctl"]) for v in idx.values() if "cand" in v and "ctl" in v]
    sub = [(a, b) for a, b in pairs if a["adv_nucl"] and b["adv_nucl"]]

    mc = []
    for lab, f in (("副词有上滑", lambda t: t["adv_up"] > 0),
                   ("副词有下滑", lambda t: t["adv_down"] > 0),
                   ("副词有任何滑", lambda t: t["adv_move"] > 0)):
        tt = sum(1 for a, b in sub if f(a) and f(b))
        tf = sum(1 for a, b in sub if f(a) and not f(b))
        ft = sum(1 for a, b in sub if not f(a) and f(b))
        ff = sum(1 for a, b in sub if not f(a) and not f(b))
        mc.append((lab, tt, tf, ft, ff))

    dv = [a["max_abs_intra"] - b["max_abs_intra"] for a, b in pairs]
    da = [a["adv_max_intra"] - b["adv_max_intra"] for a, b in sub]

    # ---------- profile ----------
    def pmed(side, key):
        v = [p.get(key) for p in P if p["side"] == side and p.get(key) is not None]
        return st.median(v) if v else 0

    # ---------- 渲染 ----------
    VMAX = 80.0
    rows_h = (bar("句内最长词", "rel_z 最高", rate(top_rz), VMAX, "#dc2626",
                  "<b>%.1f%%</b> · n=%d" % (rate(top_rz), len(top_rz)))
              + bar("句内最高音词", "loc 最高", rate(top_loc), VMAX, "#f59e0b",
                    "%.1f%% · n=%d" % (rate(top_loc), len(top_loc)))
              + bar("其余词", "句内其他", rate(rest), VMAX, "#94a3b8",
                    "%.1f%% · n=%d" % (rate(rest), len(rest))))

    gmax = 80.0
    rows_g = ""
    for lab, na, ra, ro, no in groups:
        rows_g += ('<div class="g"><div class="gn">%s<em>副词 %d 词</em></div>'
                   '<div class="gb2"><i style="width:%.1f%%;background:#dc2626"></i>'
                   '<u style="width:%.1f%%"></u></div>'
                   '<div class="gv">副词 <b>%.1f%%</b> ｜ 其他 %.1f%% ｜ '
                   '<b class="%s">%+.1f</b></div></div>'
                   % (lab, na, 100.0 * ra / gmax, 100.0 * ro / gmax, ra, ro,
                      "bad" if ra - ro < 5 else "good", ra - ro))
    hz = rate(top_rz) - rate(rest)
    rows_g += ('<div class="g ref"><div class="gn">真人靶子<em>最长词 − 其余</em></div>'
               '<div class="gb2"><i style="width:%.1f%%;background:#059669"></i>'
               '<u style="width:%.1f%%"></u></div>'
               '<div class="gv">最长词 <b>%.1f%%</b> ｜ 其余 %.1f%% ｜ '
               '<b class="good">%+.1f</b></div></div>'
               % (100.0 * rate(top_rz) / gmax, 100.0 * rate(rest) / gmax,
                  rate(top_rz), rate(rest), hz))

    mc_rows = "".join(
        '<tr><td>%s</td><td class="c">%d</td><td class="c bad">%d</td>'
        '<td class="c bad">%d</td><td class="c">%d</td>'
        '<td class="c mono">%d : %d</td></tr>' % (lab, tt, tf, ft, ff, tf, ft)
        for lab, tt, tf, ft, ff in mc)

    from string import Template
    html = Template(TEMPLATE).safe_substitute(dict(
        yield_rate="%.0f" % (100.0 * sum(t["n_nucl"] for t in T) / max(1, sum(t["n_iv"] for t in T))),
        n_nuc="%d" % len(N),
        h_all="%.0f" % rate([w for w in W if w["side"] == "human"]),
        rows_h=rows_h, rows_g=rows_g, mc_rows=mc_rows,
        n_pairs="%d" % len(pairs), n_sub="%d" % len(sub),
        dv="%+.2f" % st.median(dv),
        dv_pos="%.0f" % (100.0 * sum(1 for x in dv if x > 0) / len(dv)),
        da="%+.2f" % st.median(da),
        da_pos="%.0f" % (100.0 * sum(1 for x in da if x > 0) / len(da)),
        npvi_h="%.1f" % pmed("human", "npvi_nucldur"),
        npvi_n="%.1f" % pmed("narr", "npvi_nucldur"),
        rng_h="%.1f" % pmed("human", "pitch_range_st"),
        rng_n="%.1f" % pmed("narr", "pitch_range_st"),
        sr_h="%.2f" % pmed("human", "speech_rate"),
        sr_n="%.2f" % pmed("narr", "speech_rate"),
        dis_h="%.1f" % (100.0 * sum(1 for x in N if x["side"] == "human" and x["discont"])
                        / max(1, sum(1 for x in N if x["side"] == "human"))),
        dis_n="%.1f" % (100.0 * sum(1 for x in N if x["side"] == "narr" and x["discont"])
                        / max(1, sum(1 for x in N if x["side"] == "narr"))),
        dis_ratio="%.1f" % ((100.0 * sum(1 for x in N if x["side"] == "narr" and x["discont"])
                             / max(1, sum(1 for x in N if x["side"] == "narr")))
                            / max(0.01, 100.0 * sum(1 for x in N if x["side"] == "human" and x["discont"])
                                  / max(1, sum(1 for x in N if x["side"] == "human")))),
        hz="%.1f" % hz,
    ))
    open(J("_proso_view.html"), "w", encoding="utf-8").write(html)
    print("→ _proso_view.html  %.1f KB" % (len(html.encode("utf-8")) / 1024.0))


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prosogram glissando 层</title>
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
.card.ok .v{color:var(--ok)}
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:14px 0}
.g{display:grid;grid-template-columns:132px 1fr 330px;align-items:center;gap:12px;padding:7px 0;border-bottom:1px dashed var(--line)}
.g:last-child{border:0}
.g.ref{background:#f0fdf4;border-radius:8px;padding:7px 8px;margin-top:4px;border-bottom:0}
.gn{font-size:13.5px}.gn em{font-style:normal;color:var(--mut);font-size:11.5px;margin-left:6px;display:block}
.gb{height:9px;background:#eef2f7;border-radius:5px;overflow:hidden}
.gb i{display:block;height:100%;border-radius:5px}
.gb2{position:relative;height:9px;background:#eef2f7;border-radius:5px;overflow:hidden}
.gb2 i{position:absolute;left:0;top:0;height:100%;border-radius:5px;opacity:.85}
.gb2 u{position:absolute;top:-2px;width:2px;height:13px;background:#475569;opacity:.55}
.gv{font-size:12px;color:var(--mut);text-align:right;white-space:nowrap}
.gv b{color:var(--ink);font-weight:600}
.gv b.bad{color:var(--acc)}.gv b.good{color:var(--ok)}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card)}
th,td{padding:7px 8px;border-bottom:1px solid #eef2f7;text-align:left}
th{font-size:11.5px;color:var(--mut);font-weight:600;background:#fafbfc}
.c{text-align:center}.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.bad{color:var(--acc);font-weight:600}
.note{font-size:12.5px;color:var(--mut);background:#fffdf5;border:1px solid #fde68a;
  border-radius:10px;padding:11px 14px;margin:14px 0}
.note b{color:#92400e}
.warn{background:#fef2f2;border-color:#fecaca}
.warn b{color:#991b1b}
.kv{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.kv div{background:#fafbfc;border:1px solid var(--line);border-radius:9px;padding:9px 11px}
.kv .t{font-size:11.5px;color:var(--mut)}
.kv .n{font-size:17px;font-weight:640;letter-spacing:-.3px}
.kv .d{font-size:11.5px;color:var(--mut)}
footer{margin-top:44px;font-size:12px;color:var(--mut);border-top:1px solid var(--line);padding-top:14px}
</style></head><body><div class="wrap">

<h1>Prosogram glissando 层：旁白 vs 真人</h1>
<p class="lead">Praat 7.0.02 + Prosogram 3.05，用我们自己的词边界和 cmudict 音节数当 <code>syll</code> 层。
判定核心是听感阈值 <code>G = 0.16–0.32/T²</code> 半音——「这段音高算不算真的动了」，
阈值来自 1997 年的重合成听辨实验，不是拍的。</p>

<div class="cards">
  <div class="card"><div class="k">音节核产出率</div><div class="v">$yield_rate%</div>
    <div class="s">$n_nuc 个核 / 区间，402 take</div></div>
  <div class="card"><div class="k">真人词级有滑率</div><div class="v">$h_all%</div>
    <div class="s">「有滑」是朗读常态，不是标记</div></div>
  <div class="card hi"><div class="k">交付版 lift</div><div class="v">+1.9</div>
    <div class="s">副词 − 同句其他词（点）</div></div>
  <div class="card ok"><div class="k">真人靶子</div><div class="v">+$hz</div>
    <div class="s">句内最长词 − 其余（点）</div></div>
</div>

<h2>一、真人：信号在「选择性」，不在「有滑」</h2>
<div class="panel">
$rows_h
</div>
<p class="lead" style="margin-top:0">真人 57% 的词本来就带核内滑音。真正区分强调的是<b>谁</b>带滑音：
句内最长词 70.2% vs 其余 50.0%，差 <b>+20.2 点</b>。滑幅反而不分（2.25 vs 2.51 半音）——
真人不是把滑音做得更大，是放到该放的词上。</p>

<h2>二、我们：没有选择性</h2>
<div class="panel">
$rows_g
</div>
<div class="note warn"><b>对照组的 lift（+8.4）比交付版（+1.9）还大。</b>
这说明「副词比其他词多滑」在我们数据里主要是噪声，不是标签。
拿这个量做 PASS/FAIL 会误杀。</div>

<h2>三、同单元同 seed 配对：滑音通道完全没被触动</h2>
<p class="lead" style="margin-top:0">$n_pairs 对配对（同一单元、同一 seed，一条打标签一条不打），
其中 $n_sub 对两侧副词都有音节核。</p>
<table>
<thead><tr><th>判定</th><th class="c">两者都有</th><th class="c">只 cand</th>
<th class="c">只 ctl</th><th class="c">都没有</th><th class="c">McNemar</th></tr></thead>
<tbody>$mc_rows</tbody></table>
<div class="note">不一致对全部落在 50/50 附近 —— <b>打标签既不增加也不减少副词上的滑音。</b>
连续量也一样：整句起伏 Δ $dv 半音（$dv_pos% 为正，p≈0.26，不显著）；
<b>副词滑幅 Δ $da 半音（$da_pos% 为正，p≈0.07）</b>。</div>
<div class="note warn"><b>结论：<code>&lt;pitch, semitones=9&gt;</code> 抬的是寄存器，不是轮廓。</b>
它把目标词整体抬高，但没有在词内造出「先压后冲」的拐点。而 <code>loc</code>（词级音高偏移）那边
确实有 87 分位的效果 —— <b>抬升是真的，轮廓是空的</b>。测量口径的缺陷和生成能力的缺陷，在这里第一次被独立证实。</div>

<h2>四、顺带拿到的两个指标</h2>
<div class="panel">
<div class="kv">
  <div><div class="t">nPVI 核时长（真人 / 我们）</div>
    <div class="n">$npvi_h / $npvi_n</div><div class="d">节奏：<b>已经对齐</b></div></div>
  <div><div class="t">音域 PitchRange（真人 / 我们）</div>
    <div class="n">$rng_h / $rng_n ST</div><div class="d">我们更宽（1/3 是八度错误）</div></div>
  <div><div class="t">语速 核/秒（真人 / 我们）</div>
    <div class="n">$sr_h / $sr_n</div><div class="d">我们更快</div></div>
</div>
</div>
<div class="note">nPVI 核时长 <b>71.7 vs 69.7</b> —— 节奏这一项本来就已经对齐。
之前说「我们把节奏抹平了」是错的口径：<code>rel</code> 只是<b>测量时</b>除以句中位，音频本身没动过。
被抹平的是可比性处理，不是节奏。</div>
<div class="note">音高断点率 真人 $dis_h% / 我们 $dis_n%（$dis_ratio 倍）—— 气声导致跟踪跳八度。
所以音域的绝对量要打折看；八度折叠后仍差 1.8 倍，说明差异是真的。</div>

<footer>
402 / 403 take 成功（1 条 Prosogram 报 <code>No syllabic nuclei found</code>）。
产物：<code>_proso.json</code> / <code>_proso_words.csv</code> / <code>_proso_takes.csv</code> /
<code>_proso_nuclei.csv</code> / <code>_proso_profile.csv</code> / <code>_proso_report.md</code>。
许可 CC BY-NC，内部测量用，对外分发需另议。
</footer>
</div></body></html>
"""


if __name__ == "__main__":
    main()
