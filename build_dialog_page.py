# -*- coding: utf-8 -*-
"""生成《我是城堡之王》对话归属分析页"""
import json
import re
from collections import Counter, defaultdict

D = json.load(open("G:/_setup/castle_lines.json", encoding="utf-8"))
DL = D["dialog"]
ST = D["stats"]


def wc(s):
    return len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", s))


TOT_W = sum(wc(r["text"]) for r in DL)
agg = defaultdict(lambda: [0, 0])
for r in DL:
    a = agg[r["conf"]]
    a[0] += 1
    a[1] += wc(r["text"])

SURE = sum(w for k, (c, w) in agg.items() if k in ("VOCATIVE", "ADULT-ADDR"))
ALT = sum(w for k, (c, w) in agg.items() if k.startswith("ALTERNATE"))
UNK = sum(w for k, (c, w) in agg.items() if k in ("UNKNOWN", "CROWD"))

CONF_LABEL = {
    "VOCATIVE": ("呼语直接定人", "引号里叫了对方名字，说话人必然是另一个"),
    "ADULT-ADDR": ("成人称呼", "darling / dear / his mother → 只能是 Joseph 或 Helena"),
    "ALTERNATE": ("双人交替（连续）", "两段对话之间没有叙述打断，A-B-A-B 可靠"),
    "ALTERNATE-RISK": ("双人交替（跨叙述）", "中间夹了叙述段，同一人可能连说两句"),
    "CROWD": ("群像", "一群同学七嘴八舌，本来就没有单一说话人"),
    "UNKNOWN": ("无解", "三人以上在场，或附近没有任何人名锚点"),
}

# 人工核对样本（我逐句读过上下文）
VERIFY = [
    ("看鹿（[840]–[850]）", "Charles / Edmund", [
        (841, "It's a deer.", "Charles", "—", "首个，无锚点"),
        (842, "What sort of a deer?", "Edmund", "Edmund", "✓"),
        (843, "I don't know – like any sort. It's got sort of branchy horns.", "Charles", "Charles", "✓"),
        (844, "Antlers, stupid.", "Edmund", "Edmund", "✓"),
        (845, "Yes.", "Charles", "Charles", "✓"),
        (846, "I've never seen one.", "Edmund", "Edmund", "✓"),
        (847, "You must have, in the zoo.", "Charles", "Charles", "✓"),
        (848, "I've never been to a zoo.", "Edmund", "Edmund", "✓"),
        (850, "What are we going to do, then?", "Edmund", "Edmund", "✓ 跨了叙述段仍对"),
    ]),
    ("问学校（[171]–[182]）", "Charles / Edmund", [
        (171, "When did he die, then?", "Edmund", "Edmund", "✓"),
        (172, "Here's the picture, look – that's my father.", "Charles", "Charles", "✓"),
        (174, "A few years ago. I was about five. Or six.", "Charles", "Charles", "✓"),
        (175, "He would have been pretty old by then. How old was he?", "Edmund", "Edmund", "✓"),
        (176, "I don't know. Quite old, I suppose. Look, then, there's the photograph.", "Charles", "Charles", "✓"),
        (179, "I told you. When he was in the Battle of Britain, he was twenty.", "Charles", "Charles", "✓"),
        (181, "Where do you go to school?", "Edmund", "Charles", "✗ 反了"),
        (182, "In Wales.", "Charles", "Edmund", "✗ 反了"),
    ]),
    ("车里（[2100]–[2104]）", "Charles / Helena（母子）", [
        (2100, "I didn't push him, I was trying to help him down...", "Charles", "—", "v2 曾误判成 Edmund"),
        (2102, "All right, darling, it's quite all right.", "Helena", "Helena", "✓ v4 靠 darling 救回"),
        (2103, "He's just stupid, Hooper is, he's a show-off.", "Charles", "—", "v4 仍无解"),
        (2104, "Charles, dear, I don't think this is really the right time...", "Helena", "Helena", "✓ 呼语 Charles"),
    ]),
]


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def rows_conf():
    out = []
    order = ["VOCATIVE", "ADULT-ADDR", "ALTERNATE", "ALTERNATE-RISK", "CROWD", "UNKNOWN"]
    for k in order:
        c, w = agg.get(k, [0, 0])
        if not c:
            continue
        name, desc = CONF_LABEL[k]
        cls = {"VOCATIVE": "g", "ADULT-ADDR": "g", "ALTERNATE": "b",
               "ALTERNATE-RISK": "y", "CROWD": "m", "UNKNOWN": "r"}[k]
        out.append(
            "<tr><td class='cf %s'>%s</td><td class='nm'>%s</td><td class='ds'>%s</td>"
            "<td class='nu'>%d</td><td class='nu'>%d</td><td class='nu'>%.1f%%</td></tr>"
            % (cls, k, name, desc, c, w, 100.0 * w / TOT_W))
    return "\n".join(out)


def rows_verify():
    out = []
    for title, pair, items in VERIFY:
        ok = sum(1 for x in items if x[4].startswith("✓"))
        out.append("<div class='vgrp'><div class='vhead'>%s<span>%s · %d/%d 对</span></div>"
                   "<table class='vt'>" % (esc(title), esc(pair), ok, len(items)))
        for i, txt, truth, pred, mark in items:
            cls = "ok" if mark.startswith("✓") else ("bad" if mark.startswith("✗") else "na")
            out.append("<tr class='%s'><td class='idx'>%d</td><td class='q'>%s</td>"
                       "<td class='who'>%s</td><td class='pred'>%s</td><td class='mk'>%s</td></tr>"
                       % (cls, i, esc(txt), truth, pred, esc(mark)))
        out.append("</table></div>")
    return "\n".join(out)


# 长台词 UNKNOWN（>18 词），这些才是真正需要人工的
long_unk = [r for r in DL if r["conf"] == "UNKNOWN" and wc(r["text"]) > 18]
long_unk.sort(key=lambda r: -wc(r["text"]))
rows_long = "\n".join(
    "<tr><td class='idx'>%d</td><td class='q'>%s</td><td class='nu'>%d</td></tr>"
    % (r["i"], esc(r["text"][:150]), wc(r["text"])) for r in long_unk[:25])

# 角色分布
by = defaultdict(Counter)
for r in DL:
    if r["who"]:
        by[r["who"]][r["conf"]] += 1
rows_role = "\n".join(
    "<tr><td class='nm'>%s</td><td class='nu'>%d</td><td class='nu'>%d</td>"
    "<td class='nu'>%d</td><td class='nu'>%d</td></tr>"
    % (who, sum(c.values()), c.get("VOCATIVE", 0) + c.get("ADULT-ADDR", 0),
       c.get("ALTERNATE", 0) + c.get("ALTERNATE-RISK", 0), c.get("CROWD", 0))
    for who, c in sorted(by.items(), key=lambda x: -sum(x[1].values())))

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>只有引号时，谁在说话？</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0e1014;color:#c8cfda;font:15px/1.75 -apple-system,"Segoe UI","PingFang SC",sans-serif;
     padding:52px 22px 90px;max-width:1000px;margin:0 auto}
h1{font-size:29px;font-weight:600;color:#eef2f8;letter-spacing:-.3px;line-height:1.35}
.sub{color:#6b7484;font-size:14px;margin-top:10px}
.hero{display:flex;gap:14px;margin:34px 0 8px;flex-wrap:wrap}
.kpi{flex:1;min-width:150px;background:#15181f;border:1px solid #212630;border-radius:12px;padding:18px 20px}
.kpi b{display:block;font-size:32px;font-weight:600;color:#eef2f8;line-height:1.2}
.kpi b.g{color:#6fbf8c}.kpi b.y{color:#d9a441}.kpi b.r{color:#d8697a}
.kpi span{font-size:12.5px;color:#6b7484}
h2{font-size:19px;color:#e6ebf3;margin:52px 0 6px;font-weight:600}
h2 em{font-style:normal;font-size:13px;color:#5d6675;font-weight:400;margin-left:12px}
p{color:#98a1b0;margin:12px 0;font-size:14.5px}
p b{color:#dbe2ec;font-weight:600}
table{width:100%;border-collapse:collapse;background:#14171d;border-radius:11px;
      overflow:hidden;font-size:13.5px;margin-top:14px}
th{background:#1a1e26;color:#8b94a3;font-weight:500;font-size:12px;text-align:left;padding:9px 12px}
td{padding:9px 12px;border-top:1px solid #1f242d;vertical-align:top}
tr:hover td{background:#171b22}
.cf{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;white-space:nowrap}
.cf.g{color:#6fbf8c}.cf.b{color:#6a9fd8}.cf.y{color:#d9a441}.cf.m{color:#a98bc9}.cf.r{color:#d8697a}
.nm{color:#dbe2ec;font-weight:600;white-space:nowrap}
.ds{color:#8b94a3;font-size:12.5px}
.nu{text-align:right;color:#9aa3b2;font-variant-numeric:tabular-nums;white-space:nowrap}
.idx{color:#5d6675;font-family:ui-monospace,monospace;font-size:11.5px;width:52px}
.q{color:#b8c2d0;font-family:Georgia,serif;font-size:13.5px;line-height:1.6}
.who{white-space:nowrap;color:#8b94a3;font-size:12.5px}
.pred{white-space:nowrap;font-size:12.5px}
.mk{font-size:12px;white-space:nowrap}
tr.ok .mk{color:#6fbf8c} tr.bad .mk{color:#d8697a} tr.bad td{background:#1e1518}
tr.na .mk{color:#6b7484}
.vgrp{margin-top:26px}
.vhead{display:flex;justify-content:space-between;align-items:baseline;
       color:#dbe2ec;font-size:14.5px;font-weight:600;padding:0 2px}
.vhead span{font-size:12.5px;color:#6b7484;font-weight:400}
.vt td{padding:8px 12px}
.note{background:#15181f;border-left:3px solid #d9a441;border-radius:0 8px 8px 0;
      padding:14px 18px;margin:20px 0;font-size:13.8px;color:#a8b1c0}
.note b{color:#e3c07a}
.warn{border-left-color:#d8697a}
.warn b{color:#e58c99}
.foot{margin-top:56px;padding-top:20px;border-top:1px solid #1f242d;
      color:#5d6675;font-size:12.5px;line-height:1.9}
code{background:#1a1e26;padding:1.5px 6px;border-radius:4px;
     font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#a8b1c0}
</style></head><body>

<h1>只有引号、没有人物称谓时，<br>能分清是谁在说话吗</h1>
<div class="sub">Susan Hill《我是城堡之王》· 全书 2,921 段 · 逐段解析</div>

<div class="hero">
  <div class="kpi"><b>1,168</b><span>纯引号对话段<br>（占全书段落 40%）</span></div>
  <div class="kpi"><b class="g">46%</b><span>能给出说话人<br>（按字数计）</span></div>
  <div class="kpi"><b class="r">54%</b><span>规则无法判定<br>（按字数计）</span></div>
  <div class="kpi"><b>43</b><span>群像段<br>本来就没有「谁」</span></div>
</div>

<p>答案是：<b>能分出一半，但另一半必须读上下文</b>。这本书 40% 的段落是光秃秃的引号，
作者从不写「某某说」。我试了四条路径，按可靠性排下来是这样。</p>

<h2>四条归属路径<em>按词数占比</em></h2>
<table>
<tr><th>置信度</th><th>名称</th><th>依据</th><th>段数</th><th>词数</th><th>占比</th></tr>
__ROWS_CONF__
</table>

<p>最硬的信号不是语法，是<b>呼语</b>：<code>'I'm not afraid of you, Hooper.'</code>
——说话人叫对方 Hooper，那他自己必然不是 Hooper。这类句子只有 41 段，但零误差。
第二硬的是<b>成人称呼</b>：<code>'All right, darling'</code>、<code>'Charles, dear'</code>，
说明说话人是家长，只可能是 Joseph 或 Helena。</p>

<div class="note">
<b>为什么「双人交替」只算第二档</b>：如果两段对话之间没有任何叙述，A-B-A-B 极可靠。
但只要中间插了一句「Hooper said nothing.」或「Kingshaw took his watch out」，
下一个人可能接着自己说，也可能换人——这一步机械规则无法判断。
</div>

<h2>我逐句核对过的样本<em>含错误案例</em></h2>
<p>下面三场戏我人工读了上下文，把真实说话人和规则判断逐句对照。对错都留着。</p>
__ROWS_VERIFY__

<div class="note warn">
<b>看第二组的最后两句</b>：<code>'Where do you go to school?'</code> 被判给 Charles，
实际是 Edmund 问的；<code>'In Wales.'</code> 被判给 Edmund，实际是 Charles 答。
两句全反。原因是中间隔了一句叙述，交替的「步数」被错位了。
<br><br>
<b>第一组跨了叙述段却全对</b>，说明这类错误不是必然，只是无法预判。
</div>

<h2>分不清的三类<em>各有各的原因</em></h2>
<p><b>一、群像（43 段）。</b>学校里一群同学围着 Charles 七嘴八舌：
<code>'What did he do?'</code> <code>'Is it a spell?'</code> <code>'You'll probably die, now.'</code>
这些话不是「某个人说的」，是人群的噪音。配音时应该当环境音处理，不该分配给任何角色。</p>

<p><b>二、三人以上在场（521 段里的主体）。</b>Warings 里同时有 Edmund、Charles、Helena、
Mrs Boland 时，交替推断失效。尤其是母亲全程用 <code>she</code> 指代、名字不出现，
早期版本会把母子对话误判成两个男孩的对话——这是我修得最久的一处。</p>

<p><b>三、附近没有任何人名锚点。</b>连续的短对话（<code>'Yes.'</code> <code>'No.'</code> <code>'Why?'</code>）
离最近的「某某说」可能隔了十几段，中间还夹着大段心理描写。</p>

<h2>按角色看<em>已归属的台词</em></h2>
<table>
<tr><th>角色</th><th>总句数</th><th>呼语/成人称呼</th><th>交替推断</th><th>群像</th></tr>
__ROWS_ROLE__
</table>

<p>Edmund 和 Charles 各占约 280 句，量级对称，符合全书双主角结构。
Joseph 只有 25 句、Helena 17 句——这不是他们话少，是<b>他们的对话大多落在「多人场景」里</b>，
被归进了 UNKNOWN。</p>

<h2>还剩下的长台词<em>最需要人工过一遍</em></h2>
<p>UNKNOWN 里有 521 段，但多数是 <code>'Yes.'</code> 这种短应答。真正影响配音的是下面这些
超过 18 词、却没定到人的台词（按长度排前 25 条）。</p>
<table>
<tr><th>段号</th><th>台词</th><th>词数</th></tr>
__ROWS_LONG__
</table>

<h2>对配音方案的影响</h2>
<p><b>可以直接用的：</b>呼语和成人称呼定下的 1,096 词，加上连续双人交替的 1,863 词，
共约 <b>2,959 词（26%）</b>，这些句子给谁配音是确定的。</p>

<p><b>需要读一遍的：</b>跨叙述段的 2,193 词（19.6%）——多数正确，但会像第二组那样整段反掉，
建议按场景整块核对，不要逐句核。</p>

<p><b>建议的做法：</b>先把每个<b>场景</b>（连续 20–40 段）的在场人物定下来，再在这个场景内
逐句分配。整块处理比逐句猜准得多——因为一旦确定了「这场是母亲开车送儿子」，
后面每一句就只在两个人之间选，错误率会掉一个数量级。</p>

<div class="foot">
数据：<code>castle_lines.json</code>（1,168 段逐段记录：说话人 / 置信度 / 依据 / 前后文）<br>
脚本：<code>castle_dialog_attr4.py</code>（呼语 + 成人称呼 + 代词落地 + 双人交替 + 群像检测）<br>
全书 73,637 词 / 2,921 段 / 492 个「叙述+对话」混合段（混合段自带归属，共 325 处锚点）
</div>
</body></html>"""

HTML = (HTML.replace("__ROWS_CONF__", rows_conf())
            .replace("__ROWS_VERIFY__", rows_verify())
            .replace("__ROWS_ROLE__", rows_role)
            .replace("__ROWS_LONG__", rows_long))

open("G:/_setup/castle_dialog.html", "w", encoding="utf-8").write(HTML)
print("ok  %d bytes" % len(HTML))
print("unreplaced:", re.findall(r"__[A-Z_]+__", HTML))
