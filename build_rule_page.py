# -*- coding: utf-8 -*-
"""build_rule_page.py —— 生成「韵律指令编译器」报告页（内嵌 1 条对照音频）"""
import base64, json, os, subprocess, tempfile
from pathlib import Path

OUT = Path("G:/_setup/dots_prosody_report.html")
AUDIO = Path("G:/_setup/dots_prog/A_rate080.wav")
FFMPEG = "ffmpeg"


def mp3_b64(p, br="96k"):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as t:
        tmp = t.name
    try:
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(p),
                        "-codec:a", "libmp3lame", "-b:a", br, tmp], check=True)
        return base64.b64encode(Path(tmp).read_bytes()).decode()
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


plan = json.load(open("G:/_setup/plan_calm.json", encoding="utf-8"))
safe_tag = Path("G:/_setup/tag_safe.txt").read_text(encoding="utf-8").strip()

RATE_ROWS = [
    ("1.00", "14.24", "20.80", "—", ""),
    ("0.85", "15.20", "21.76", "+4.6%", "bad"),
    ("0.80", "16.10", "22.72（实测）", "+9.2%", "ok"),
    ("0.71", "16.96", "23.52", "+13.1%", "ok"),
    ("0.60", "18.70", "25.28", "+21.5%", "ok"),
    ("0.55", "19.36", "26.08", "+25.4%", "ok"),
]
GAP_ROWS = [
    ("真人 real_trim", "29.41", "17.45", "11.96", "1.28", "9", "ref"),
    ("dots 基线（无标签）", "20.80", "14.24", "6.56", "0.60", "9", ""),
    ("A · rate 0.80", "22.72", "15.09", "7.63", "0.71", "9", ""),
    ("P · 仅 8×pause L3", "23.20", "14.37", "8.83", "0.83", "9", ""),
    ("D · rate + 9×pause", "24.16", "14.67", "9.49", "0.76", "10", "warn"),
    ("E · 多 rate span + pause", "24.00", "13.79", "10.21", "1.12", "9", "warn"),
    ("F · 多 rate span 无 pause", "24.32", "15.53", "8.79", "0.88", "7", "warn"),
]
SIDE_ROWS = [
    ("A", "整段一个 <code>&lt;rate&gt;</code>", "22.72s", "✅ 完整（仅丢 1 个 and）", "ok"),
    ("P", "8 个 <code>&lt;pause act=&quot;ins&quot; level=&quot;3&quot;/&gt;</code>，无 rate", "23.20s", "✅ 100% 完整", "ok"),
    ("F", "9 个 <code>&lt;rate&gt;</code> span，无 pause", "24.32s", "❌ 丢「swelling in oceans」", "bad"),
    ("D", "9 个 rate span + 9 个 pause", "24.16s", "❌ 丢「trickling into streams」", "bad"),
    ("E", "11 个 rate span + 9 个 pause", "24.00s", "❌ 丢 2 处（and evaporating in / trickling）", "bad"),
    ("B", "每处叠 3 个 pause", "12.80s", "❌ 38 词只剩 10 词", "bad"),
]
OSS = [
    ("hi-paris/Prosody-Control-French-TTS", "端到端 SSML 标注流水线（最直接对标）",
     "级联两个 QLoRA Qwen2.5-7B：一个预测短语断点（F1 99.2%），一个回归 pitch/rate/volume 目标值。MOS 3.20→3.87。"),
    ("AI-S2-Lab/EmoPP", "情感感知的韵律切分",
     "BiLSTM 基线，用 <code>#</code> 标断点；证明「情绪 → 断点位置」可预测。"),
    ("b08x/prosodic-text-converter", "音频 → SSML（Ruby）",
     "预置风格 deliberate（1.0s 段 / 350ms 停）、contemplative（1.4s / 500ms），与我们的 pause_bank 同构。"),
    ("Zyphra/Zonos", "Apache-2.0 表达性 TTS",
     "显式 prosody 旋钮（rate / pitch / 频率响应）+ 4 个情绪滑条 + 10–30s 参考。"),
    ("EmotiVoice", "情绪 + reference_audio 风格提取",
     "有独立 Duration Predictor / Pitch Predictor，中文强。"),
]

b64 = mp3_b64(AUDIO)

rate_html = "".join(
    "<tr class='%s'><td>%s</td><td>%s s</td><td>%s s</td><td>%s</td></tr>" % (c, r, s, t, d)
    for r, s, t, d, c in RATE_ROWS)

gap_html = "".join(
    "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
    % (c, n, t, sp, si, g, k) for n, t, sp, si, g, k, c in GAP_ROWS)

side_html = "".join(
    "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (c, i, w, d, v)
    for i, w, d, v, c in SIDE_ROWS)

plan_html = "".join(
    "<tr><td>%s</td><td>%s</td><td>%.2f s</td><td>%.2f s</td></tr>"
    % (p["after_text"], p["punct"], p["target_s"], p["residual_s"]) for p in plan["pause_plan"])
plan_sum = sum(p["residual_s"] for p in plan["pause_plan"])

oss_html = "".join(
    "<div class='oss'><h3><a href='https://github.com/%s' target='_blank'>%s</a></h3>"
    "<p class='tag'>%s</p><p>%s</p></div>" % (n, n, k, d) for n, k, d in OSS)

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dots 韵律指令编译器 · 实测报告</title>
<style>
:root{--bg:#0f1115;--fg:#e8eaf0;--dim:#9aa3b2;--line:#252a34;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--acc:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.75 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:40px 22px 80px}
h1{font-size:27px;margin:0 0 6px;letter-spacing:-.3px}
.sub{color:var(--dim);margin:0 0 34px;font-size:14px}
h2{font-size:19px;margin:44px 0 14px;padding-bottom:9px;border-bottom:1px solid var(--line)}
h3{font-size:15px;margin:0 0 4px}
p{margin:10px 0}
code{background:#1b202a;padding:1px 5px;border-radius:4px;font-size:13px;color:#a5d6ff;font-family:ui-monospace,Consolas,monospace}
pre{background:#141922;border:1px solid var(--line);border-radius:9px;padding:14px 16px;overflow-x:auto;font-size:12.5px;line-height:1.65;font-family:ui-monospace,Consolas,monospace;color:#c9d1d9;white-space:pre-wrap;word-break:break-all}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:14px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:500;font-size:13px}
tr.ok td:nth-child(2){color:var(--ok)}
tr.bad td{background:rgba(248,81,73,.07)}
tr.ref td{background:rgba(88,166,255,.09);font-weight:600}
tr.warn td{background:rgba(210,153,34,.07)}
.note{border-left:3px solid var(--acc);background:#141b26;padding:12px 16px;border-radius:0 8px 8px 0;margin:16px 0}
.note.warn{border-color:var(--warn);background:#1e1a10}
.note.bad{border-color:var(--bad);background:#1e1213}
.k{color:var(--ok);font-weight:600}.w{color:var(--warn);font-weight:600}.b{color:var(--bad);font-weight:600}
audio{width:100%;margin:10px 0 4px}
.oss{border:1px solid var(--line);border-radius:9px;padding:13px 16px;margin:11px 0;background:#131821}
.oss .tag{color:var(--dim);font-size:13px;margin:2px 0 6px}
.oss a{color:var(--acc);text-decoration:none}
.oss p{margin:4px 0;font-size:13.5px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
.card{border:1px solid var(--line);border-radius:9px;padding:14px 16px;background:#131821}
.card p{font-size:13.5px;color:#c3cbd8;margin:4px 0 0}
</style></head><body><div class="wrap">

<h1>dots 韵律指令编译器</h1>
<p class="sub">按文字内容生成 <code>&lt;rate&gt;</code> / <code>&lt;pause&gt;</code> / <code>&lt;pitch&gt;</code> · 2026-10-17 实测</p>

<h2>一、先纠正：rate 0.80 确实够 10%</h2>
<p>重新拟合 rate 兑现曲线（5 个实测点），<b>语音时长 = base / (1 − 0.58×(1−r))</b>，k=0.58 在三档上稳定（0.587 / 0.595 / 0.553）。</p>
<table><tr><th>rate</th><th>语音</th><th>总长</th><th>相对 20.80s</th></tr>__RATE__</table>
<div class="note">0.85 只有 <span class="b">+4.6%</span>，但 <span class="k">0.80 是 +9.2%（实测 22.72s）</span>，基本踩在官方 10% 线上。上一轮把「0.85 不够」推广成「0.8 也不行」，是我说错了。</div>

<h2>二、缺口不在语速，在静音</h2>
<table><tr><th>文件</th><th>总长</th><th>语音</th><th>静音</th><th>间隙中位</th><th>间隙数</th></tr>__GAP__</table>
<div class="note warn">真人 29.41s = 语音 17.45 + <b>静音 11.96</b>；基线只有 6.56s 静音。<br>
rate 0.55 的语音已到 19.36s（<b>比真人还慢</b>），总长仍只 26.08s —— 差的 3.3s 全在静音。<br>
真人每个标点后停 <b>1.0–1.7s</b>，模型只停 0.1–1.0s。<span class="k">这就是「不像」的最大来源。</span></div>

<h2>三、标签有副作用（本次最重要的发现）</h2>
<table><tr><th>组</th><th>写法</th><th>时长</th><th>ASR 内容</th></tr>__SIDE__</table>
<div class="note bad">
<b>铁律：文本里只能有一个 <code>&lt;rate&gt;</code>，而且不能和 <code>&lt;pause&gt;</code> 混用。</b><br>
· 叠 2 个以上 pause → 整段跳词（12.80s / 38 词只剩 10 词）<br>
· 拆成多个 rate span → 丢子句（F 丢 1、E 丢 2、D 丢 1，随 span 数递增）<br>
· 单独用都安全（A 一个 rate / P 只有 pause）<br>
⇒ 生产配方改成：<b>生成端只下 rate，停顿交给后期 insert_pauses.py + room_tone.py</b>。
</div>

<h2>四、编译器怎么用</h2>
<p>先 <code>analyze()</code> 再 <code>decide()</code>，八个维度全部来自文本本身：</p>
<div class="grid">
<div class="card"><h3>① 句法位置</h3><p>段首铺垫放慢 6%，段末收尾放慢 12%</p></div>
<div class="card"><h3>② 子句长度</h3><p>≤3 词放慢 8%（真人短句反而拖长），≥12 词加快 6%</p></div>
<div class="card"><h3>③ 标点层级</h3><p>句号 1.56s / 分号 1.35s / 逗号 1.16s / 破折号 0.95s</p></div>
<div class="card"><h3>④ 枚举结构</h3><p>连续逗号 ≥2：各项等距 −0.12s，末项蓄势 +0.25s</p></div>
<div class="card"><h3>⑤ 句首连接词</h3><p>and / but / so / because… → 换气 +0.12s 且放慢 3%</p></div>
<div class="card"><h3>⑥ 句子类型</h3><p>疑问句尾 +3 半音，感叹句 +2 半音并加快 8%，引语放慢 4%</p></div>
<div class="card"><h3>⑦ 强调词</h3><p>全大写 / <code>*斜体*</code> / 数字 → 单独 span 放慢 6%</p></div>
<div class="card"><h3>⑧ 长句呼吸</h3><p>≥12 词的子句后 +0.20s 换气</p></div>
</div>

<p style="margin-top:22px"><b>命令行</b></p>
<pre>python dots_prosody.py --in text.txt --mode mc --safe --explain \\
       --target-wpm 145 --pause-scale 1.30 --json plan.json</pre>
<p><code>--safe</code> 输出唯一不丢词的组合（整段一个 rate），同时给出 <code>pause_plan</code> 供后期插停顿；<code>--explain</code> 逐句打印决策依据。</p>

<p style="margin-top:18px"><b>同一段文本的决策输出（节选）</b></p>
<pre>#3 swelling in oceans
   短句(3词)放慢 · 标点 , → 1.16s · 枚举末项蓄势 +0.25
   ⚠ 需 1.23s，标签只给 0.30s → 后期补 0.93s
#9 flowing down rivers
   短句(3词)放慢 · 段末收尾放慢 · 标点 . → 1.56s · 段末长停 +0.60
   ⚠ 需 2.81s，标签只给 0.30s → 后期补 2.21s</pre>

<p><b>safe 模式的最终指令</b>（38 词整段，一条 rate）</p>
<pre>__SAFE__</pre>

<p><b>停顿计划</b>（9 个边界，共需后期补 <b>__PLANSUM__s</b> 静音）</p>
<table><tr><th>边界（该句之后）</th><th>标点</th><th>目标间隙</th><th>后期补</th></tr>__PLAN__</table>

<h2>五、rate 0.80 的实际听感对照</h2>
<p>38 词 / 同参考 / seed 42 / 内容完整。</p>
<audio controls src="data:audio/mpeg;base64,__B64__"></audio>
<p class="sub" style="margin:2px 0 0">rate 0.80 → 22.72s（+9.2%），语音 15.09s ≈ 151 wpm，比真人 131 wpm 略快。</p>

<h2>六、开源参考项目</h2>
__OSS__
<div class="note">「文本 → 韵律标签」这条路社区有成熟范式：<b>先预测断点位置，再回归 pitch/rate/volume 目标值</b>。区别是他们用小模型训出来，我们用规则 + 实测系数达到同样效果，不需要训练。最直接对标的是 hi-paris 那个 —— 它的两阶段结构就是本编译器的学习版。</div>

</div></body></html>"""

HTML = (HTML.replace("__RATE__", rate_html).replace("__GAP__", gap_html)
        .replace("__SIDE__", side_html).replace("__PLAN__", plan_html)
        .replace("__PLANSUM__", "%.2f" % plan_sum)
        .replace("__SAFE__", safe_tag.replace("<", "&lt;").replace(">", "&gt;"))
        .replace("__OSS__", oss_html).replace("__B64__", b64))

OUT.write_text(HTML, encoding="utf-8")
print("→ %s  (%.2f MB)" % (OUT, OUT.stat().st_size / 1e6))
