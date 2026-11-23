# -*- coding: utf-8 -*-
"""build_pause_rules_page.py —— 生成「马修停顿规则」报告页（离线单文件）。"""
import json

R = json.load(open("G:/_setup/mc_pause_rules.json", encoding="utf-8"))
BT = json.load(open("G:/_setup/mc_pause_backtest.json", encoding="utf-8"))
PLAN = json.load(open("G:/_setup/castle_pause_plan.json", encoding="utf-8"))

meta = R["meta"]
tiers = R["tiers"]
punct = R["punct"]
conj = R["conj"]

TOTAL = R["all"]["n"]


def pct(x):
    return "%.1f" % (100 * x)


# ---- 分层条 ----
TIER_LABEL = {"micro": ("词间微隙", "0.06–0.15s", "不算停顿，正常连读"),
              "breath": ("轻换气", "0.15–0.30s", "句中最常见的真停顿"),
              "pause": ("明显换气", "0.30–0.60s", "长从句后"),
              "punct": ("标点级", "≥0.60s", "逗号/句号/段落")}
TIER_COLOR = {"micro": "#4a5261", "breath": "#5f8fa8", "pause": "#c98b3a", "punct": "#e8a33d"}

tier_rows = ""
for k in ["micro", "breath", "pause", "punct"]:
    t = tiers.get(k)
    if not t:
        continue
    lab, rng, note = TIER_LABEL[k]
    w = 100 * t["n"] / TOTAL
    tier_rows += (
        '<div class="trow">'
        '<div class="tname">%s<em>%s</em></div>'
        '<div class="tbar"><i style="width:%.1f%%;background:%s"></i></div>'
        '<div class="tval">%d<span>%s%%</span></div>'
        '<div class="tnote">%s · 中位 %.2fs</div>'
        '</div>\n' % (lab, rng, w, TIER_COLOR[k], t["n"], pct(t["share"]), note,
                      t["stats"]["median"]))

# ---- 标点表 ----
PUNCT_NAME = {"period": "句号 .", "comma": "逗号 ,"}
punct_rows = ""
for k, v in punct.items():
    s = v["stats"]
    punct_rows += (
        "<tr><td>%s</td><td class='num'>%d</td><td class='num big'>%.2fs</td>"
        "<td class='num'>%.2f</td><td class='num'>%.2f</td><td class='num'>%.2f</td>"
        "<td class='num'>%.2f</td></tr>\n"
        % (PUNCT_NAME.get(k, k), v["n"], s["median"], s["p25"], s["p75"], s["p90"], s["max"]))

# ---- 连词表 ----
CONJ_ORDER = ["and", "as", "that", "so", "then", "if", "or", "but", "for", "because", "while"]
conj_rows = ""
for w in CONJ_ORDER:
    p = conj.get(w)
    if not p:
        continue
    a, b, c = p["after_period"], p["after_comma"], p["no_punct"]
    conj_rows += (
        "<tr><td class='w'>%s</td><td class='num'>%d</td><td class='num'>%d</td>"
        "<td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num hl'>%s</td><td class='num hl'>%s</td></tr>\n"
        % (w, p["occ"], p["n_before"],
           ("%d / %.2f" % (a["n"], a["med"])) if a["n"] else "–",
           ("%d / %.2f" % (b["n"], b["med"])) if b["n"] else "–",
           c["n"],
           ("%.2fs" % c["med"]) if c["med"] else "–"))

# ---- 城堡示例 ----
castle_rows = ""
for x in PLAN["items"]:
    castle_rows += (
        "<tr><td class='ctx'>%s</td><td class='mk'>%s</td><td class='num'>%.2fs</td></tr>\n"
        % (x["after"], x["punct"] or "—", x["pause_s"]))

RULE_ROWS = [
    ("句号  .  ?  !", "1.76s", "1.38 – 1.98", "n=234"),
    ("逗号  ,", "1.17s", "1.00 – 1.45", "n=136"),
    ("分号 / 冒号  ; :", "1.28s", "≈ 逗号 ×1.09", "无样本，按比例估"),
    ("破折号  —", "1.17s", "同逗号", "无样本"),
    ("段落末", "2.50s", "2.30 – 2.80", "n=26（≥2.3s 超长停）"),
    ("句中换气", "0.20s", "0.15 – 0.27", "n=68，默认不主动加"),
    ("词间微隙", "0.10s", "0.08 – 0.13", "n=130，模型自带，别动"),
]
rule_rows = ""
for a, b, c, d in RULE_ROWS:
    cls = " class='keyrow'" if a.startswith("句号") or a.startswith("逗号") else ""
    rule_rows += "<tr%s><td>%s</td><td class='num big'>%s</td><td class='num'>%s</td><td class='note'>%s</td></tr>\n" % (cls, a, b, c, d)

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>马修的停顿规则 · 实测</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0e1014;color:#e8eaee;font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:44px 24px 80px}
h1{font-size:27px;font-weight:650;letter-spacing:.3px;margin:0 0 8px}
.sub{color:#8b93a1;font-size:14px;margin-bottom:34px}
.sub b{color:#e8a33d;font-weight:600}
h2{font-size:17px;font-weight:600;margin:44px 0 14px;padding-left:11px;border-left:3px solid #e8a33d}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:10px}
.card{background:#161a21;border:1px solid #232833;border-radius:12px;padding:16px 16px 14px}
.card .k{font-size:12px;color:#7d8593;letter-spacing:.4px}
.card .v{font-size:26px;font-weight:650;margin-top:4px;color:#f0b455}
.card .u{font-size:12px;color:#7d8593;margin-left:3px}
table{width:100%;border-collapse:collapse;background:#14171d;border-radius:11px;overflow:hidden;font-size:14px}
th{background:#1b1f27;color:#98a0ae;font-weight:500;font-size:12.5px;text-align:left;padding:10px 13px;letter-spacing:.3px}
td{padding:10px 13px;border-top:1px solid #20252e}
tr:hover td{background:#181d25}
.num{text-align:right;font-variant-numeric:tabular-nums;color:#cfd5df}
.big{font-size:16px;font-weight:650;color:#f0b455}
.note{color:#7d8593;font-size:12.5px}
.keyrow td{background:#1a1710}
.keyrow:hover td{background:#1f1b12}
.w{font-family:ui-monospace,Consolas,monospace;color:#8fc7e8}
.hl{color:#f0b455;font-weight:600}
.ctx{font-family:ui-monospace,Consolas,monospace;font-size:13px;color:#b8c0cc}
.mk{color:#e8a33d;font-family:ui-monospace,monospace;text-align:center}
.trow{display:grid;grid-template-columns:118px 1fr 78px 200px;align-items:center;gap:12px;margin-bottom:9px}
.tname{font-size:13.5px;color:#dfe3ea}
.tname em{display:block;font-style:normal;font-size:11px;color:#6f7787}
.tbar{height:16px;background:#1a1e26;border-radius:4px;overflow:hidden}
.tbar i{display:block;height:100%;border-radius:4px}
.tval{text-align:right;font-variant-numeric:tabular-nums;font-size:14px}
.tval span{color:#6f7787;font-size:11.5px;margin-left:4px}
.tnote{font-size:11.5px;color:#6f7787}
.callout{background:#1a1710;border:1px solid #3a2e18;border-left:3px solid #e8a33d;border-radius:9px;padding:14px 17px;margin:16px 0;font-size:14px}
.callout b{color:#f0b455}
.callout.warn{background:#1a1416;border-color:#3a2026;border-left-color:#c0565f}
.callout.warn b{color:#e07a83}
code{background:#1c212a;padding:1.5px 6px;border-radius:4px;font-family:ui-monospace,Consolas,monospace;font-size:13px;color:#a8c8e8}
pre{background:#14171d;border:1px solid #232833;border-radius:10px;padding:15px 17px;overflow-x:auto;font-size:13px;line-height:1.65}
pre code{background:none;padding:0;color:#b8c8d8}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.foot{margin-top:52px;padding-top:18px;border-top:1px solid #20252e;color:#5f6775;font-size:12px}
@media(max-width:760px){.cards{grid-template-columns:1fr 1fr}.grid2{grid-template-columns:1fr}.trow{grid-template-columns:90px 1fr 62px}.tnote{display:none}}
</style></head><body><div class="wrap">

<h1>马修的停顿规则 · 实测</h1>
<div class="sub">来源：Mathew McConaughey 朗读《Wonder》有声书母带 <b>26.63 分钟</b> ·
2,587 词 · <b>641 个间隙</b>逐个对齐到词边界（能量 VAD −35dB / 10ms + 词级时间戳）</div>

<div class="cards">
<div class="card"><div class="k">整体语速</div><div class="v">97.1<span class="u">wpm</span></div></div>
<div class="card"><div class="k">每几词一个间隙</div><div class="v">4.0<span class="u">词</span></div></div>
<div class="card"><div class="k">标点级占全部间隙</div><div class="v">69.1<span class="u">%</span></div></div>
<div class="card"><div class="k">规则回测误差</div><div class="v">0.32<span class="u">s</span></div></div>
</div>

<h2>一句话结论</h2>
<div class="callout">马修的停顿<b>几乎完全由标点驱动</b>，语法位置（连词、从句、介词短语）几乎没有额外作用。
句号稳定在 <b>1.76s</b>、逗号稳定在 <b>1.17s</b>，两者都不随后接词或前子句长度明显变化
（逗号 1.09–1.37s、句号 1.59–1.81s）。所以「他的习惯不变」这句话是对的 ——
但变的不是连词，而是<b>标点密度</b>。</div>

<h2>可直接用的规则表</h2>
<table>
<tr><th>位置</th><th style="text-align:right">目标停顿</th><th style="text-align:right">实测区间 p25–p75</th><th>样本</th></tr>
{{RULE_ROWS}}
</table>
<div class="callout">这些是<b>间隙总时长</b>（前一语音结束 → 下一语音开始）。生成音频自带的 0.09s 级词间隔已经在里面，
所以后期替换时直接用这个绝对值，不要再叠加。</div>

<h2>连词：反直觉的真相</h2>
<div class="callout warn"><b>连词前面没有习惯性长停。</b>
<code>and</code> 在母带出现 119 次，其中 35 次前面有 ≥0.6s 停顿 —— 但拆开看，
10 次是<b>前一句句号</b>（<code>…soundly. And Zoe…</code>）、10 次是<b>原文逗号</b>（枚举 <code>A, B, and C</code>），
真正<b>没有标点</b>的只有 15 次，中位 <b>0.15s</b>。<br><br>
换句话说：看到 <code>and</code> 不要加 1.2s，那是标点的功劳。要加也只加 0.15s，听感上接近不停。</div>
<table>
<tr><th>连词</th><th style="text-align:right">出现次数</th><th style="text-align:right">前有停顿</th>
<th style="text-align:right">句号后 n / 中位</th><th style="text-align:right">逗号后 n / 中位</th>
<th style="text-align:right">无标点 n</th><th style="text-align:right">无标点中位</th></tr>
{{CONJ_ROWS}}
</table>

<h2>间隙分层：句中真的很少停</h2>
{{TIER_ROWS}}
<div class="callout">68 个真换气（0.15–0.60s）分摊到 26 分钟里，等于<b>平均每 23 秒才有一次</b>。
0.10s 的「词间微隙」虽然占 20%，但那是正常连读的产物，不是停顿 —— 不要刻意加。</div>

<h2>标点停顿的完整分布</h2>
<table>
<tr><th>标点</th><th style="text-align:right">n</th><th style="text-align:right">中位</th>
<th style="text-align:right">p25</th><th style="text-align:right">p75</th><th style="text-align:right">p90</th><th style="text-align:right">max</th></tr>
{{PUNCT_ROWS}}
</table>
<div class="callout">逗号与句号的分布<b>重叠很少</b>（逗号 p90 1.70 &lt; 句号中位 1.76），
说明这是两套稳定的档位，不是连续变化。超过 2.3s 的 26 个超长停全部落在场景/段落切换处。</div>

<h2>规则回测（诚实数字）</h2>
<div class="grid2">
<div class="card" style="padding:18px">
<div class="k">全量 641 个间隙</div>
<div style="font-size:15px;margin-top:8px;line-height:2">
MAE <b style="color:#f0b455">0.321s</b><br>
中位绝对误差 <b style="color:#f0b455">0.190s</b><br>
相关系数 <b style="color:#f0b455">0.781</b><br>
总静音量偏差 <b style="color:#f0b455">+7.9%</b>
</div></div>
<div class="card" style="padding:18px">
<div class="k">分项 MAE</div>
<div style="font-size:14px;margin-top:8px;line-height:2">
逗号 <b style="color:#f0b455">0.298s</b>（n=136）<br>
句号 <b style="color:#f0b455">0.428s</b>（n=234）<br>
句中短停 <b style="color:#f0b455">0.105s</b>（n=170）<br>
无标点长停 <b style="color:#f0b455">0.472s</b>（n=101）
</div></div>
</div>
<div class="callout">句号误差比逗号大，是因为句号本身跨度更宽（1.0–2.3s），不是规则错了。
换句话说：<b>按这套规则配出来的停顿，和真人逐处对照平均差 0.32 秒</b>。</div>

<h2>套到《我是城堡之王》</h2>
<div class="sub" style="margin-bottom:14px">开头 8 句实测输出（<code>castle40b.txt</code> → <code>castle_pause_plan.json</code>，抖动 ±0.10s）</div>
<table>
<tr><th>停顿落在</th><th style="text-align:center">标点</th><th style="text-align:right">停顿</th></tr>
{{CASTLE_ROWS}}
</table>

<h2>怎么用</h2>
<pre><code># 1) 给任意文本生成停顿计划
G:/Python310/python.exe G:/_setup/mc_pause_plan.py \\
    --text-file your.txt --jitter 0.10 --json plan.json --tsv

# 2) 生成的音频按计划改停顿（双向：可拉长也可缩短）
G:/Python310/python.exe G:/_setup/pause_by_punct.py \\
    --gen gen.wav --text your.txt --out fixed.wav --report fix.json

# 3) 只想调快慢
--scale 0.9   # 全部停顿 ×0.9</code></pre>
<div class="callout">规则文件是 <code>G:/_setup/mc_pause_rules.json</code>，
<code>pause_by_punct.py</code> 会直接读它，所以以后重新统计一次，全链路自动跟着变。</div>

<div class="foot">数据：G:/GPT-SoVITS/_dataset/wonder_train.wav（26.63min / 32kHz）·
词级时间戳 wonder_final.json（2,587 词 / 80ms 粒度）·
脚本 mc_pause_rules.py / mc_pause_plan.py / _pause_backtest.py</div>
</div></body></html>"""

HTML = (HTML.replace("{{RULE_ROWS}}", rule_rows)
            .replace("{{CONJ_ROWS}}", conj_rows)
            .replace("{{TIER_ROWS}}", tier_rows)
            .replace("{{PUNCT_ROWS}}", punct_rows)
            .replace("{{CASTLE_ROWS}}", castle_rows))

out = "G:/_setup/mc_pause_rules.html"
open(out, "w", encoding="utf-8").write(HTML)
print("写出 %s  (%.1f KB)" % (out, len(HTML) / 1024))
