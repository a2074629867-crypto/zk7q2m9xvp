# -*- coding: utf-8 -*-
"""build_dots_emo_page.py —— dots.tts 官方情绪/韵律控制 语法 + 本机实测页"""
import base64, glob, json, os, subprocess, tempfile
import soundfile as sf

OUT = "G:/_setup/dots_emo"
HTML = "G:/_setup/dots_emo_control.html"
FFMPEG = "E:/tool/oopz/ffmpeg.exe"


def mp3_b64(path):
    tmp = tempfile.mktemp(suffix=".mp3")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path,
                    "-ac", "1", "-ar", "32000", "-b:a", "64k", tmp], check=True)
    b = open(tmp, "rb").read()
    os.remove(tmp)
    return base64.b64encode(b).decode()


def dur(path):
    a, sr = sf.read(path)
    return len(a) / sr


GROUPS = [
    ("A · 控制是否真的生效（4 词短句，seed 对比）",
     "同文本、同参考，只改 seed 看随机波动；再改标签看是否超出噪声。",
     [("A_base", "纯文本 · seed 42", "基线"),
      ("S7_plain", "纯文本 · seed 7", "同一文本换 seed"),
      ("S2024_plain", "纯文本 · seed 2024", "同一文本换 seed"),
      ("R055", "rate 0.55", "<rate, factor=0.55>"),
      ("B_rate070", "rate 0.70", "<rate, factor=0.70>"),
      ("R195", "rate 1.95", "<rate, factor=1.95>"),
      ("C_calm3", "emo calm L3", '<emo type="calm" level="3">'),
      ("E_sad3", "emo sad L3", '<emo type="sad" level="3">')]),

    ("B · rate 扫（完整 38 词，对齐真人 29.41s）",
     "rate 是真实单调控制，但只拉长语音段，静音段不动。",
     [("F0_plain", "纯文本（基线）", "对照"),
      ("F1_r085", "rate 0.85", ""),
      ("F2_r071", "rate 0.71", "按 21.1/29.4 算出的理论值"),
      ("F3_r060", "rate 0.60", ""),
      ("G058", "rate 0.58", ""),
      ("G055", "rate 0.55（官方下限）", "★ rate 能到的最长"),
      ("J_r060_seed7", "rate 0.60 · seed 7", "同一配置换 seed，差 2.2s ⇒ rate 效果有不确定性"),
      ("F4_r071_calm", "rate 0.71 + emo calm L2", "★ 反例：calm 会抵消并超过 rate")]),

    ("C · pause 补静音 —— 单用有效，和 rate 叠加会冲突",
     "<pause act=\"ins\" level=N/> 插在逗号/句号后（共 8 处）。单独用 +2.40s，但一叠上 rate 就反过来缩短。",
     [("P_only_lv3", "纯文本 + pause L3（对照 20.80s）", "★ pause 单独有效 +2.40s"),
      ("H_lv1", "rate 0.55 + pause L1", "叠加后反而变短"),
      ("H_lv2", "rate 0.55 + pause L2", "叠加后反而变短"),
      ("H_lv3", "rate 0.55 + pause L3", "叠加后反而变短")]),
]

REAL = "E:/tts-models/acpp/out/calmdeep_final/real_trim.wav"

# 声纹（WeSpeaker CAM++ vs 真人 real_trim.wav），已实测
SPK = [
    ("F0_plain", "纯文本基线", 20.80, 0.8504),
    ("F2_r071", "rate 0.71", 23.52, 0.8537),
    ("F3_r060", "rate 0.60", 25.28, 0.8641),
    ("G055", "rate 0.55", 26.08, 0.8432),
    ("H_lv2", "rate 0.55 + pause L2", 24.32, 0.8303),
    ("F4_r071_calm", "rate 0.71 + emo calm L2", 19.84, 0.7867),
]


def build():
    cards = []
    for title, note, items in GROUPS:
        rows = []
        for tag, label, extra in items:
            p = os.path.join(OUT, tag + ".wav")
            if not os.path.exists(p):
                continue
            d = dur(p)
            pct = (d / 20.80 - 1) * 100 if tag.startswith(("F", "G", "H")) else None
            badge = ""
            if pct is not None:
                badge = '<span class="pct">%+.1f%%</span>' % pct
            rows.append("""
      <div class="row">
        <div class="lbl"><b>%s</b>%s%s</div>
        <div class="meta"><span class="dur">%.2fs</span>%s</div>
        <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>
      </div>""" % (label, ("<code>%s</code>" % extra) if extra.startswith("<") else "",
                   ("<span class=\"hintline\">%s</span>" % extra) if extra and not extra.startswith("<") else "",
                   d, badge, mp3_b64(p)))
        cards.append('<section class="card"><h2>%s</h2><p class="note">%s</p>%s</section>' % (title, note, "".join(rows)))

    spk_rows = "".join(
        '<tr><td>%s</td><td><code>%s</code></td><td>%.2fs</td><td class="%s">%.4f</td></tr>'
        % (n, l, d, "k" if sc >= 0.86 else ("warn" if sc < 0.82 else ""), sc)
        for n, l, d, sc in SPK)
    spk_html = ('<section class="card"><h2>D · 声纹代价（CAM++ vs 真人 real_trim.wav）</h2>'
                '<p class="note">rate 放慢几乎不伤音色；<b class="warn">emo calm 反而伤</b>（0.7867）。'
                '参照：GSV 微调 0.8567 / 真人跨段天花板 0.88~0.91。</p>'
                '<table><tr><th>文件</th><th>配置</th><th>时长</th><th>声纹</th></tr>%s</table></section>' % spk_rows)

    real = ('<section class="card real"><h2>真人对照（锚点）</h2>'
            '<p class="note">Calm《Wonder》t≈768.5–796.4s，同一段 38 词。</p>'
            '<div class="row"><div class="lbl"><b>Matthew McConaughey 真人</b></div>'
            '<div class="meta"><span class="dur">%.2fs</span></div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div></section>'
            % (dur(REAL), mp3_b64(REAL)))

    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>dots.tts 情绪/韵律控制 · 语法与实测</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--fg:#e8eaf0;--dim:#9aa3b2;--acc:#ff6b5b;--ok:#54d18c;--bd:#252a34}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;padding:28px 20px 80px}
.wrap{max-width:940px;margin:0 auto}
h1{font-size:25px;margin:0 0 6px;letter-spacing:-.3px}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:26px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:20px 22px;margin-bottom:18px}
.card h2{font-size:16.5px;margin:0 0 4px;color:#fff}
.note{color:var(--dim);font-size:13px;margin:0 0 14px}
.row{display:grid;grid-template-columns:1fr 96px;gap:10px 14px;align-items:center;padding:9px 0;border-top:1px solid #1e232c}
.row:first-of-type{border-top:0}
.lbl b{font-size:14px;font-weight:600}
.lbl code{display:inline-block;margin-left:8px;background:#0b0d11;border:1px solid #2b3240;color:#ffb3a8;padding:1px 6px;border-radius:5px;font-size:11.5px;font-family:ui-monospace,Consolas,monospace}
.hintline{display:block;color:var(--dim);font-size:12px;margin-top:2px}
.meta{text-align:right}
.dur{font-family:ui-monospace,Consolas,monospace;font-size:13.5px;color:var(--ok)}
.pct{display:block;font-size:11.5px;color:var(--dim);font-family:ui-monospace,monospace}
audio{grid-column:1/-1;width:100%%;height:32px;filter:invert(.92) hue-rotate(180deg)}
.real{border-color:#3a2a2a;background:#1d1919}
table{width:100%%;border-collapse:collapse;font-size:13.5px;margin-top:8px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid #1e232c}
th{color:var(--dim);font-weight:500;font-size:12.5px}
td code{background:#0b0d11;border:1px solid #2b3240;color:#ffb3a8;padding:1px 6px;border-radius:5px;font-size:12px}
.k{color:#ffd479}
.warn{color:var(--acc)}
ul{margin:10px 0 0;padding-left:20px}
li{margin:5px 0}
</style></head><body><div class="wrap">
<h1>dots.tts 情绪 / 韵律控制 · 官方语法 + 本机实测</h1>
<div class="sub">官方仓库 <code style="color:#ffb3a8">studio-dots-ai/dots.tts</code>（原 rednote-hilab，1392★，2026-10-08 更新）· 本机 GGUF q8_0 / RX 580 Vulkan</div>

<section class="card">
<h2>一、两套 prompt 模板 —— 能力边界在这里</h2>
<p class="note">同一份权重，两种输入模板，标签只在第二种里有效。这是所有问题的根源。</p>
<table>
<tr><th>模式</th><th>模板</th><th>情绪/韵律控制</th></tr>
<tr><td>TTS</td><td><code>[文本]{text}[语音]{audio}</code></td><td>官方只给 <code>--seed</code>（"Try different --seed values for prosody variation"）</td></tr>
<tr><td>Edit</td><td><code>[原文本]{instruction}[原语音]{src}[编辑后语音]{tgt}</code></td><td>全套标签：emo / pitch / rate / pause / enhance / bg / spk_transfer / sub / ins / del</td></tr>
</table>
<p class="note" style="margin-top:12px">源码位置：<code>src/dots_tts/data/pipelines/tts_pipeline.py:17</code>、<code>src/dots_tts/edit_runtime.py:26-30</code>。<br>
本地 acpp 的 dots_tts <b class="warn">只注册了 tts / clon，没有 edit task</b>（<code>--list-loaders</code> 实测），所以本地只能走 TTS 模板。</p>
</section>

<section class="card">
<h2>二、完整标签语法（取自官方 UI 校验代码 apps/edit_playground/editing.py）</h2>
<table>
<tr><th>标签</th><th>语法</th><th>合法取值</th></tr>
<tr><td><code>&lt;emo&gt;</code></td><td><code>&lt;emo type="calm" level="2"&gt;文字&lt;/emo&gt;</code></td><td>type ∈ happy / angry / sad / afraid / disgusted / melancholic / surprised / <b class="k">calm</b>；level ∈ 1,2,3（默认 2）</td></tr>
<tr><td><code>&lt;emo&gt;</code> 自由描述</td><td><code>&lt;emo desc="a sleepy whisper"&gt;文字&lt;/emo&gt;</code></td><td>desc 与 type/level <b>互斥</b>，不能同时给</td></tr>
<tr><td><code>&lt;pitch&gt;</code></td><td><code>&lt;pitch, semitones=-5&gt;文字&lt;/pitch&gt;</code></td><td><b class="warn">只有 −9 −7 −5 5 7 9</b>（没有 0、没有 ±1~4）</td></tr>
<tr><td><code>&lt;rate&gt;</code></td><td><code>&lt;rate, factor=0.71&gt;文字&lt;/rate&gt;</code></td><td><b class="k">0.55–0.99 或 1.01–1.95</b>，0.01 步进，<b>不能 1.00</b></td></tr>
<tr><td><code>&lt;pause/&gt;</code></td><td><code>&lt;pause act="ins" level="3"/&gt;</code></td><td>act ∈ ins（插入）/ red（减少）；level ∈ 1,2,3</td></tr>
<tr><td><code>&lt;enhance&gt;</code></td><td><code>&lt;enhance&gt;整段指令&lt;/enhance&gt;</code></td><td>无参数，音质增强</td></tr>
<tr><td><code>&lt;bg&gt;</code></td><td>容器标签</td><td>README 列出，UI 未开放</td></tr>
<tr><td><code>&lt;sub&gt;</code> / <code>&lt;ins&gt;</code> / <code>&lt;del&gt;</code></td><td><code>&lt;sub targ="新"&gt;原&lt;/sub&gt;</code></td><td>换词 / 插词 / 删词</td></tr>
<tr><td><code>&lt;spk_transfer/&gt;</code></td><td>自闭合</td><td>说话人切换边界，程序自动插</td></tr>
</table>
<p class="note" style="margin-top:12px">解析器 <code>edit_instruction.py</code> 只校验 <code>&lt;sub&gt;</code> 的 targ 属性；其余标签的属性由模型在训练时见过的方式决定 —— 所以上面这张取值表就是<b>硬约束</b>，写错会被模型当普通文字。</p>
</section>

%s
%s
%s

<section class="card">
<h2>结论 · 可落地的配方</h2>
<ul>
<li><b>标签是真的生效的</b>，即使走 TTS 模板。rate 两端差 2.2 倍，而 seed 噪声只有 1.15 倍。</li>
<li><b class="k">rate 只拉长语音段，不动静音段</b>。20.80s = 语音 13.0 + 静音 7.8，所以 rate 0.55 只到 26.08s，不是理论上的 31.4s。</li>
<li><b class="k">rate 几乎不伤音色，甚至更好</b>：rate 0.60 → 声纹 <b>0.8641</b>，高于基线 0.8504，也高于 GSV 微调的 0.8567。</li>
<li><b class="warn">emo calm 是反方向</b>：它让语速变快（19.84s）且伤音色（0.7867）。睡前故事不要用它。</li>
<li><b class="warn">pause 和 rate 不能叠加</b>：pause 单独用 +2.40s（有效），但一叠到 rate 上就反向缩短 1.8~3.4s。</li>
<li><b>rate 效果受 seed 影响</b>：同是 rate 0.60，seed 42 → 25.28s，seed 7 → 23.04s（差 9%%）。要出成品就多 seeds 挑。</li>
</ul>
<p class="note" style="margin-top:14px">
<b>推荐配方</b>：<code>&lt;rate, factor=0.60&gt;整段&lt;/rate&gt;</code> + seed 扫 3~5 个 →
取最接近 29.41s 的那条（预期 24~26s / 声纹 ~0.86）→ 再用现成的
<code>insert_pauses.py --donor real.wav</code> + <code>room_tone.py</code> 补剩下的 3~4 秒与底噪。<br>
这样 rate 在生成端就把语速压下来了（不是事后拉伸波形），外部工具只做轻微收尾 —— 比原来
「21.12s 全交给 rubberband 0.88x」音质更好。
</p>
</section>

</div></body></html>""" % ("".join(cards), spk_html, real)

    open(HTML, "w", encoding="utf-8").write(html)
    print("written:", HTML, len(html) // 1024, "KB")


if __name__ == "__main__":
    build()
