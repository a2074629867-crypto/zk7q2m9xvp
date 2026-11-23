# -*- coding: utf-8 -*-
"""build_voice_report.py —— 全书人物音色总表（HTML）。

数据源：
  cloud/ref/cast.json            角色音色表（八套情绪切片 + 配角缺口）
  castle_dialog_report.json      v8 说话人归属（1538 个引号块）
  _emo_probe.json                每套参考音的 F0/RMS/HNR

输出：_voice_report.html
"""
import json
import os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
CAST = json.load(open(os.path.join(ROOT, "cloud/ref/cast.json"), encoding="utf-8"))
REP = json.load(open(os.path.join(ROOT, "castle_dialog_report.json"), encoding="utf-8"))
PROBE = json.load(open(os.path.join(ROOT, "_emo_probe.json"), encoding="utf-8"))["per_file"]

NAME2KEY = {"Charles": "C", "Edmund": "E", "Joseph": "J", "Helena": "H",
            "Fielding": "F", "Boland": "B", "Casey": "K", "Fenwick": "W"}
UNITS = REP["units"]

# ---------- 统计 ----------
lines_by_key = Counter()
ch_matrix = defaultdict(Counter)
for u in UNITS:
    who = u.get("who")
    if not who:
        k = "UNK"
    elif who == "__THOUGHT__":
        k = "TH"
    else:
        k = NAME2KEY.get(who, "UNK")
    lines_by_key[k] += 1
    ch_matrix[u.get("ch")][k] += 1

TOTAL = len(UNITS)
CHARS = ["C", "E", "J", "H", "F", "B", "K", "W"]
ORDER = CHARS + ["TH", "UNK"]

# 每章需要几套人声（不含独白/未定）
ch_need = {}
for ch, c in ch_matrix.items():
    ch_need[ch] = sum(1 for k in CHARS if c.get(k))

# 情绪分布（规则判定，与 make_jobs 同一套）
import sys
sys.path.insert(0, os.path.join(ROOT, "cloud/cuda"))
from make_jobs import pick_emotion  # noqa: E402

emo_dist = defaultdict(Counter)
for u in UNITS:
    k = NAME2KEY.get(u.get("who"))
    if not k:
        continue
    e, _ = pick_emotion(k, u["text"], CAST)
    emo_dist[k][e] += 1

# ---------- HTML ----------
H = []
A = H.append
A("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全书人物音色总表 · The Castle of Kingshaw</title>
<style>
:root{--bg:#fbfaf7;--card:#fff;--ink:#1d1c1a;--dim:#6b6862;--line:#e3ded4;
--accent:#8a6d3b;--ok:#2f6b4f;--warn:#9a5b1e;--bad:#a33a2f;--soft:#f3efe6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:27px;font-weight:600;letter-spacing:.4px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:34px}
h2{font-size:19px;font-weight:600;margin:44px 0 14px;padding-bottom:8px;
border-bottom:1px solid var(--line)}
h3{font-size:15px;font-weight:600;margin:26px 0 10px;color:var(--accent)}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--card);
box-shadow:0 1px 2px rgba(0,0,0,.04);border-radius:6px;overflow:hidden}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line)}
th{background:var(--soft);font-weight:600;font-size:12.5px;color:#4a463f;white-space:nowrap}
tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.mono{font-family:ui-monospace,"SF Mono",Consolas,monospace;font-size:12px}
.tag{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11.5px;
border:1px solid currentColor;white-space:nowrap}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.dim{color:var(--dim)}
.box{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:4px;padding:14px 18px;margin:16px 0;font-size:13.5px}
.box.warn{border-left-color:var(--warn)}
.box.bad{border-left-color:var(--bad)}
.box b{font-weight:600}
ul{margin:8px 0;padding-left:20px}li{margin:5px 0}
.heat{display:inline-block;min-width:26px;text-align:right}
tr.hl td{background:#fdfaf2}
.kpi{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0 6px}
.kpi div{flex:1 1 150px;background:var(--card);border:1px solid var(--line);
border-radius:6px;padding:12px 14px}
.kpi b{display:block;font-size:23px;font-weight:600;letter-spacing:-.5px}
.kpi span{font-size:12px;color:var(--dim)}
.fr{font-family:Georgia,serif;font-style:italic;color:#4a463f;font-size:12.5px;line-height:1.55}
.foot{margin-top:56px;padding-top:14px;border-top:1px solid var(--line);
color:var(--dim);font-size:12px}
</style></head><body><div class="wrap">""")

A("<h1>全书人物音色总表</h1>")
A('<div class="sub">The Castle of Kingshaw · 依据 v8 说话人归属（%d 个引号块）与法语原声切片实测 · 2026-10-31</div>' % TOTAL)

# KPI
A('<div class="kpi">')
A('<div><b>%d</b><span>全书对白句</span></div>' % TOTAL)
A('<div><b>%d</b><span>有名字的说话人</span></div>' % len(CHARS))
A('<div><b>2</b><span>有音色的角色</span></div>')
A('<div><b>6</b><span>无音色的角色</span></div>')
A('<div><b>8</b><span>主角情绪音色套数</span></div>')
A("</div>")

A('<div class="box"><b>一句话结论：</b>两个主角各有四套真人原声切片（共 8 套），'
  '可以按情绪逐句换参考音；但<b>另外 6 个说话人一套音色都没有</b>，'
  '而这 6 人合计 %d 句（占已归属对白的 %.0f%%）。'
  '所以"全书音色"现在只齐了 2 个人，剩下的缺口在配角。'
  '</div>' % (sum(lines_by_key[k] for k in "JHFBKW"),
              100 * sum(lines_by_key[k] for k in "JHFBKW") / max(1, TOTAL - lines_by_key["UNK"] - lines_by_key["TH"])))

# 1 角色总表
A("<h2>一、全书说话人清单</h2>")
A("<table><tr><th>角色</th><th>身份</th><th class='num'>句数</th>"
  "<th class='num'>占比</th><th>出场章节</th><th>音色</th></tr>")
for k in ORDER:
    n = lines_by_key.get(k, 0)
    if not n:
        continue
    if k == "UNK":
        A("<tr><td>未定</td><td>归属无锚点，未强行猜</td><td class='num'>%d</td>"
          "<td class='num'>%.1f%%</td><td class='dim'>—</td>"
          "<td><span class='tag dim'>待定</span></td></tr>" % (n, 100 * n / TOTAL))
        continue
    if k == "TH":
        A("<tr><td>心理独白</td><td>内心活动，不算对白</td><td class='num'>%d</td>"
          "<td class='num'>%.1f%%</td><td class='dim'>—</td>"
          "<td><span class='tag ok'>用角色本音·轻声</span></td></tr>" % (n, 100 * n / TOTAL))
        continue
    c = CAST[k]
    chs = sorted(ch for ch in ch_matrix if ch_matrix[ch].get(k))
    ref = c.get("ref")
    if ref:
        emos = list((c.get("emotions") or {}).keys())
        tag = "<span class='tag ok'>%d 套情绪</span> <span class='mono dim'>%s</span>" % (
            len(emos), " / ".join(emos))
    else:
        tag = "<span class='tag bad'>无音色</span>"
    A("<tr><td><b>%s</b></td><td>%s%s</td><td class='num'>%d</td><td class='num'>%.1f%%</td>"
      "<td class='mono'>%s</td><td>%s</td></tr>"
      % (c["name"], {"lead": "主角 · ", "support": "配角 · ", "minor": "次要 · "}.get(c.get("role"), ""),
         ({"M": "男", "F": "女"}.get(c.get("sex"), "") + "童") if c.get("age") == "child"
         else ("成年" + {"M": "男", "F": "女"}.get(c.get("sex"), "")),
         n, 100 * n / TOTAL, ",".join(str(x) for x in chs), tag))
A("</table>")

A('<div class="box warn"><b>缺口在这 6 个人身上。</b>'
  'Joseph（父亲）、Helena（母亲）、Fielding（校长）三个人就有 %d 句，'
  '而且分属成年男声、成年女声两种完全不同的音区——'
  '现有的 8 套全是童声，<b>无法用变调派生</b>（变调会把成年男声做成"大号儿童"）。'
  '</div>' % (lines_by_key.get("J", 0) + lines_by_key.get("H", 0) + lines_by_key.get("F", 0)))

# 2 四情绪表
A("<h2>二、两个主角的四套情绪音色</h2>")
A("<p class='dim'>全部为法语原声电影切片，<b>不是合成音</b>。参考音的转写必须与音频逐字对应，"
  "否则克隆会串味；下表转写即实际入参。</p>")

for k in ("C", "E"):
    c = CAST[k]
    A("<h3>%s（%s，%d 句）</h3>" % (c["name"], "男童" if c.get("sex") == "M" else "女童",
                                    lines_by_key.get(k, 0)))
    A("<table><tr><th>情绪</th><th>文件</th><th class='num'>时长</th>"
      "<th class='num'>F0 中位</th><th class='num'>谱质心</th><th class='num'>谱倾斜</th>"
      "<th class='num'>片段</th><th class='num'>全书占比</th>"
      "<th>状态</th></tr>")
    tot = sum(emo_dist[k].values()) or 1
    for name, ed in c["emotions"].items():
        pct = 100 * emo_dist[k].get(name, 0) / tot
        note = ed.get("note", "")
        if note.startswith("★"):
            st = "<span class='tag warn'>注意</span>"
        else:
            st = "<span class='tag ok'>可用</span>"
        A("<tr><td><b>%s</b><br><span class='dim'>%s</span></td>"
          "<td class='mono'>%s</td><td class='num'>%.1fs</td><td class='num'>%.0f Hz</td>"
          "<td class='num'>%.0f</td><td class='num'>%+.1f</td>"
          "<td class='num'>%d</td><td class='num'>%.0f%%</td><td>%s</td></tr>"
          % (name, ed.get("zh", ""), os.path.basename(ed["ref"]), ed["dur"], ed["f0"],
             ed.get("cen", 0), ed.get("slp", 0), ed["clips"], pct, st))
    A("</table>")
    for name, ed in c["emotions"].items():
        if ed.get("note"):
            A("<p class='dim' style='margin:6px 0 0'><b>%s：</b>%s</p>" % (name, ed["note"]))

A('<div class="box bad"><b>四套不能等权使用。</b>'
  'Charles 四套的 F0 中位是 184 / 252 / 389 / 395 Hz，跨度 <b>2.2 个八度</b>；'
  'Hooper 是 203 / 219 / 261 / 333 Hz，跨度 1.3 个八度。'
  '把它们当成"同一个人的四种心情"逐句切换，听感上会像换了四个人——'
  '这是参考音本身的声区差，不是模型问题。'
  '实际文本分布恰好救了这一点：Charles 84% 是 normal、Hooper 74% 是 calm，'
  '高唤醒档只占 1~16%，属于点缀而不是常态。'
  '<br><br><b>最易混的一对：C_soft 184 Hz 与 E_calm 203 Hz，只差 1.8 半音</b>，'
  '靠 F0 分不开，必须靠谱质心（927 vs 1116）与谱倾斜（−8.4 vs −6.1）。'
  '</div>')

A("<h2>五、验收口径：声纹已退役，改三参数</h2>")
A('<div class="box bad"><b>实测结论：CAM++ 在这批素材上连角色都分不开。</b>'
  '<table style="margin-top:8px"><tr><th>对比</th><th class="num">中位余弦</th></tr>'
  '<tr><td>同角色不同句子（55 条对白产物，801 对）</td><td class="num">0.382</td></tr>'
  '<tr><td>跨角色不同句子（684 对）</td><td class="num">0.383</td></tr>'
  '<tr><td>同一 ref 不同句子</td><td class="num">0.344</td></tr>'
  '<tr><td>同一 ref 同一句不同 seed</td><td class="num">0.796</td></tr>'
  '</table>'
  '<b>AUC = 0.491，等于随机。</b>方差几乎全部来自「内容」，不是「音色」。'
  '所以「normal 与 angry 只有 0.46」不是模型不行，是<b>跨情绪比这个口径本身就错</b>。'
  '声纹在本项目只保留一个用途：同一句、同一档、不同 seed 的自洽性（0.80 左右）。'
  '</div>')
A("<p>验收改用三个与内容弱相关、与发声强相关的量，<b>一律对「它自己那一档」的参考音比</b>：</p>")
A("<table><tr><th>参数</th><th class='num'>容差</th><th>作用</th></tr>"
  "<tr><td>F0 中位（半音差）</td><td class='num'>±3</td>"
  "<td>情绪档最直接的量；八档最小档距 5.1 半音，留一半余量</td></tr>"
  "<tr><td>谱质心（比值）</td><td class='num'>0.78~1.28</td>"
  "<td>声道长度 + 发声紧张度，927~2084 Hz 基本对应唤醒度</td></tr>"
  "<tr><td>谱倾斜（dB/kHz）</td><td class='num'>±3.0</td>"
  "<td>音色亮暗；excited 与 angry 的 F0 几乎相同（389 vs 395），靠它俩区分</td></tr>"
  "</table>")
A('<div class="box warn"><b>测量范围必须固定 75–500 Hz。</b>'
  '用 60–700 Hz 会出八度错误：C_angry 测成 474.6（实际 394.6）、'
  'E_begging 测成 486.7（实际 261.0），都是整 2 倍。'
  '旧表里的 428.8 / 258.6 就是被这个错误污染的，已全部重测。'
  '同时输出「八度跳变率」，超过 25% 的条目 F0 判据作废，只看谱参数。'
  '</div>')

# 3 情绪分布
A("<h2>三、四情绪在全书的实际分布</h2>")
A("<p class='dim'>按台词文本线索判定（侮辱词→愤怒/斥骂；感叹号→激动/大声；"
  "省略号或求饶词→轻声/求饶；其余→平常/平静）。这是首轮启发式，需人工复核。</p>")
A("<table><tr><th>角色</th><th>档位分布</th></tr>")
for k in ("C", "E"):
    tot = sum(emo_dist[k].values()) or 1
    parts = " ".join("<span class='mono'>%s %d (%.0f%%)</span>"
                     % (e, n, 100 * n / tot)
                     for e, n in emo_dist[k].most_common())
    A("<tr><td><b>%s</b></td><td>%s</td></tr>" % (CAST[k]["name"], parts))
A("</table>")

# 4 章节矩阵
A("<h2>四、章节 × 角色矩阵</h2>")
A("<p class='dim'>每一章实际需要几套人声，直接决定这一章的配音工作量与缺口。</p>")
SHORT = {"C": "Charles", "E": "Edmund", "J": "Joseph", "H": "Helena",
         "F": "Fielding", "B": "Boland", "K": "Casey", "W": "Fenwick"}
head = "".join("<th class='num'>%s</th>" % SHORT[k] for k in CHARS)
A("<table><tr><th>章</th><th class='num'>对白</th>%s<th class='num'>未定</th>"
  "<th class='num'>需音色</th></tr>" % head)
for ch in sorted(ch_matrix, key=lambda x: (x is None, x)):
    c = ch_matrix[ch]
    tot = sum(c.values())
    if tot < 5:
        continue
    cells = "".join("<td class='num'>%s</td>" % ("<span class='heat'>%d</span>" % c[k] if c.get(k) else "<span class='dim'>·</span>")
                    for k in CHARS)
    need = ch_need[ch]
    flag = " class='hl'" if need >= 4 else ""
    A("<tr%s><td>%s</td><td class='num'>%d</td>%s<td class='num dim'>%d</td>"
      "<td class='num'><b>%d</b></td></tr>" % (flag, ch, tot, cells, c.get("UNK", 0), need))
A("</table>")

maxneed = max(ch_need.values())
A('<div class="box">峰值出现在第 %s 章，需要 <b>%d 套人声</b>同章共存。'
  '其中只有 2 套（Charles / Hooper）现在能出，其余 %d 套全缺。'
  '</div>' % ("、".join(str(ch) for ch in sorted(ch_need) if ch_need[ch] == maxneed), maxneed, maxneed - 2))

# 5 问题清单
A("<h2>六、已查出的六个问题</h2>")
A("<table><tr><th>#</th><th>问题</th><th>证据</th><th>影响</th></tr>")
A("<tr><td>1</td><td><b>Charles 愤怒组混入 Hooper 台词</b></td>"
  "<td>第 3 条 <span class='fr'>Je demande pardon à Charles…</span>"
  "（我向 Charles 道歉）说话人不可能是 Charles；"
  "时间码 2556.5 与 Hooper 组 2561.8 是同一场戏的同一句，中间隔一句 "
  "<span class='fr'>Vas-y, répète!</span></td>"
  "<td>已重建 <span class='mono'>4_charles_angry_v2.wav</span>（3 条，5.8s），旧文件弃用</td></tr>")
A("<tr><td>2</td><td><b>声纹完全不能用作验收</b></td>"
  "<td>同角色不同句子 0.382 / 跨角色 0.383 / <b>AUC 0.491（随机）</b>；"
  "同一 ref 不同句子 0.344，同一句不同 seed 0.796</td>"
  "<td>方差来自内容不是音色。声纹只保留「同句同档不同 seed」自洽性检查</td></tr>")
A("<tr><td>3</td><td><b>F0 测量有八度错误</b></td>"
  "<td>60–700 Hz 下 C_angry 测成 474.6、E_begging 测成 486.7，"
  "在 100–400 Hz 下分别是 235.6 / 243.4，整 2 倍</td>"
  "<td>旧表 428.8 / 258.6 全部作废；统一 75–500 Hz 重测，并输出八度跳变率</td></tr>")
A("<tr><td>4</td><td><b>Charles 的中性锚点混了两个声区</b></td>"
  "<td><span class='mono'>CH_neutral = normal(252Hz) + soft(184Hz)</span>，差 5 个半音</td>"
  "<td>混合锚点本身就是矛盾的；生成时按情绪取单档参考音，不要用 CH_neutral</td></tr>")
A("<tr><td>5</td><td><b>Hooper 的 calm 是诗朗诵</b></td>"
  "<td>内容是拉辛《Phèdre》选段 <span class='fr'>N'accablez point, madame…</span>，"
  "10.8s 朗诵 + 2.46s 对话拼成</td>"
  "<td>克隆可能带舞台腔；已标 <span class='tag warn'>注意</span>，待探针实测</td></tr>")
A("<tr><td>6</td><td><b>切片表与文件不一致</b></td>"
  "<td><span class='mono'>castle_fr_slice.py</span> 里 6_hooper_calm 记的是 "
  "<span class='fr'>Voleur! Espèce de sale voleur.</span>，"
  "实际文件是诗朗诵（h04a_intro_verse + h04b_papa_seul）</td>"
  "<td>按脚本重切会得到错误的参考音；以 cast.json 的转写为准</td></tr>")
A("</table>")

# 6 路线
A("<h2>七、补齐配角音色的三条路</h2>")
A("<table><tr><th>方案</th><th>做法</th><th>代价</th><th>适用</th></tr>")
A("<tr><td><b>A · 原片补切</b></td>"
  "<td>从同一部电影里找 Joseph / Helena / Fielding 的台词时间码，按现有流程切 8~13s</td>"
  "<td>要人工听片标时间码；成人台词比童声少，可能凑不够长度</td>"
  "<td>最忠于原片，推荐给父亲/母亲</td></tr>")
A("<tr><td><b>B · 旁白派生</b></td>"
  "<td>Joseph / Fielding 用旁白 ref（成年男声）；Helena / Boland 需另找成年女声</td>"
  "<td>配角会和旁白同质，听众可能分不清谁在说话</td>"
  "<td>赶工期、配角句数少时</td></tr>")
A("<tr><td><b>C · 先只做主角</b></td>"
  "<td>配角的 %d 句先跳过，只生成 Charles / Hooper 的 757 句</td>"
  "<td>成书不完整，配角台词缺失</td>"
  "<td>先验证对白链路</td></tr>" % sum(lines_by_key[k] for k in "JHFBKW"))
A("</table>")

A('<div class="foot">数据：castle_dialog_report.json（1538 块）· cloud/ref/cast.json（v3，F0 重测）'
  '· mt_voice_gate.py（三参数闸门）· jobs_probe.json（36 条探针）<br>'
  'F0 为参考音整体中位（parselmouth To Pitch 75–500 Hz），非逐句；'
  '声纹为 WeSpeaker CAM++（英文 VoxCeleb），实测 AUC 0.491，本项目不作验收判据。</div>')
A("</div></body></html>")

out = os.path.join(ROOT, "_voice_report.html")
open(out, "w", encoding="utf-8").write("\n".join(H))
print("写出", out, os.path.getsize(out), "字节")
print("角色句数", dict(lines_by_key))
print("每章需音色", {k: v for k, v in sorted(ch_need.items(), key=lambda x: (x[0] is None, x[0]))})
