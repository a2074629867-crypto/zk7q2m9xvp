# -*- coding: utf-8 -*-
"""Charles 音色路线对照试听页"""
import base64, io, os, subprocess

OUT_HTML = "G:/_setup/dots_charles.html"
TMP_MP3 = "G:/_setup/_charles_audio"

ROWS = [
    dict(id="matthew_src", name="① 马修原声（成年男声，参考锚）",
         path="G:/_setup/dots_edit2/ES_src.wav",
         f0="73.4", dur="16.80", sim="—", note="生产链现在用的音色，对照基准"),
    dict(id="dots_matthew", name="② dots + 马修参考（当前生产链）",
         path="G:/_setup/dots_edit2/MCH_matthew.wav",
         f0="72.5", dur="11.20", sim="0.7780", note="音色几乎 1:1 复制，语速 155 wpm"),
    dict(id="qwen_quiet", name="③ Qwen 直出 boy10_quiet（255Hz 原始）",
         path="E:/tts-models/out/qwen_boy/boy10_quiet.wav",
         f0="255.0", dur="3.68", sim="—", note="文字描述造的童声参考，不是 dots 产物"),
    dict(id="dots_quiet", name="④ dots + boy10_quiet ★ 推荐",
         path="G:/_setup/dots_edit2/MCH_quiet.wav",
         f0="201.5", dur="7.52", sim="0.7776", note="童声成立，落在 11 岁区间；语速 231 wpm"),
    dict(id="dots_child", name="⑤ dots + child.wav（10.4s 长参考）",
         path="G:/_setup/dots_edit2/MCH_child.wav",
         f0="120.4", dur="7.20", sim="0.8895", note="F0 保真最高，但参考本身偏低音"),
    dict(id="qwen_lonely", name="⑥ Qwen 直出 charles_lonely（长文本）",
         path="E:/tts-models/out/charles_ref/charles_lonely.wav",
         f0="154.6", dur="13.04", sim="—", note="同一描述，长文本把 F0 压低了 50Hz"),
    dict(id="dots_concat", name="⑦ dots + 拼接 11s 参考（boy10_quiet×3）",
         path="G:/_setup/dots_edit2/MCH_concat.wav",
         f0="243.3", dur="8.16", sim="0.5761", note="F0 保真 95%（255→243），但声纹反而降到 0.58"),
]


def to_mp3(src, dst):
    subprocess.run(["E:/tool/oopz/ffmpeg.exe", "-y", "-i", src, "-codec:a", "libmp3lame",
                    "-b:a", "96k", "-ar", "24000", "-ac", "1", dst],
                   capture_output=True)


def b64(p):
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()


os.makedirs(TMP_MP3, exist_ok=True)
cards = []
for r in ROWS:
    if not os.path.exists(r["path"]):
        continue
    mp3 = os.path.join(TMP_MP3, r["id"] + ".mp3")
    to_mp3(r["path"], mp3)
    cards.append((r, b64(mp3)))

html = ["""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Charles 音色路线对照</title><style>
*{box-sizing:border-box}
body{margin:0;padding:34px 22px 70px;background:#0f1116;color:#c8cfda;
 font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:24px;font-weight:600;color:#eef2f8;margin:0 0 6px}
.sub{color:#7d8797;font-size:13px;margin-bottom:26px}
h2{font-size:16px;font-weight:600;color:#e2e8f2;margin:34px 0 12px;
 padding-left:11px;border-left:3px solid #4a7fb5}
p{color:#a9b3c2;margin:10px 0}
.kpi{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0 26px}
.kpi div{flex:1;min-width:150px;background:#161a21;border:1px solid #232a35;
 border-radius:10px;padding:13px 15px}
.kpi b{display:block;font-size:20px;color:#7fb3e8;font-weight:600}
.kpi span{font-size:12px;color:#7d8797}
.card{background:#161a21;border:1px solid #232a35;border-radius:12px;
 padding:15px 17px;margin:12px 0}
.card.best{border-color:#3d6b45;background:#151d18}
.hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.nm{font-weight:600;color:#e6ecf5;font-size:14.5px}
.card.best .nm{color:#8fd39b}
.meta{font-size:12px;color:#6f7a8b;font-variant-numeric:tabular-nums}
.note{font-size:12.5px;color:#8b95a6;margin:6px 0 9px}
audio{width:100%;height:34px;margin-top:4px}
table{width:100%;border-collapse:collapse;background:#141821;border-radius:10px;
 overflow:hidden;font-size:13px;margin:14px 0}
th{background:#1a1f29;color:#8b95a6;font-weight:500;font-size:12px;
 text-align:left;padding:9px 12px}
td{padding:9px 12px;border-top:1px solid #1f2530;color:#b4bdcb}
td.n{font-variant-numeric:tabular-nums}
.hl{color:#8fd39b;font-weight:600}
.warn{color:#e0a05a}
.foot{margin-top:44px;padding-top:16px;border-top:1px solid #1f2530;
 font-size:12px;color:#636d7d}
code{background:#1c222c;padding:1px 6px;border-radius:4px;font-size:12.5px;color:#9db4cd}
</style></head><body><div class="wrap">
<h1>Charles 的音色</h1>
<div class="sub">《我是城堡之王》· 11 岁英国男孩 · dots.tts 与 Qwen3 VoiceDesign 两条路线实测</div>

<h2>先回答：音色有，开源就有</h2>
<p><b>不用自己训练。</b>Qwen3-TTS 的 VoiceDesign 可以用一句文字描述造音色，10 月 13 日已经造过 24 个男孩音色，
覆盖 7–12 岁、不同性格与英国口音，文件都还在 <code>E:/tts-models/out/qwen_boy/</code>。
今晚验证的是另一件事：<b>把这些童声当参考喂给 dots，能不能克隆出童声</b>——结论是能。</p>

<div class="kpi">
<div><b>201.5 Hz</b><span>dots 输出的童声 F0（马修 73 Hz）</span></div>
<div><b>0.7776</b><span>声纹（判定线 0.7，判为同一人）</span></div>
<div><b>29 / 29</b><span>内容完整度，相似度 1.0000</span></div>
</div>

<h2>七段对照</h2>
""",]

for r, data in cards:
    cls = "card best" if r["id"] == "dots_quiet" else "card"
    html.append('<div class="%s"><div class="hd"><span class="nm">%s</span>'
                '<span class="meta">F0 %s Hz · %s s · 声纹 %s</span></div>'
                '<div class="note">%s</div>'
                '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
                % (cls, r["name"], r["f0"], r["dur"], r["sim"], r["note"], data))

html.append("""
<h2>三条实测结论</h2>
<table>
<tr><th>参考</th><th>参考 F0</th><th>输出 F0</th><th>保真</th><th>声纹</th><th>语速</th></tr>
<tr><td>马修 baseA（8.3s）</td><td class="n">73.4</td><td class="n">72.5</td><td class="n hl">99%</td><td class="n">0.7780</td><td class="n">155 wpm</td></tr>
<tr><td>boy10_quiet（3.68s）</td><td class="n">255.0</td><td class="n">201.5</td><td class="n warn">79%</td><td class="n">0.7776</td><td class="n">231 wpm</td></tr>
<tr><td>child.wav（10.41s）</td><td class="n">118.5</td><td class="n">120.4</td><td class="n hl">102%</td><td class="n hl">0.8895</td><td class="n">242 wpm</td></tr>
<tr><td>boy10_quiet×3（11.74s）</td><td class="n">255.0</td><td class="n">243.3</td><td class="n hl">95%</td><td class="n warn">0.5761</td><td class="n">213 wpm</td></tr>
</table>

<p><b>一、dots 能克隆童声。</b>三条参考全部落在「同一人」判定线上，内容 29/29 全对。
不需要训练，换一段参考音就换了一个人。</p>

<p><b>二、参考越长，F0 保真越好。</b>10.41 秒的 child.wav 做到了 118.5 → 120.4（几乎 1:1），
声纹也是最高的 0.8895；3.68 秒的短参考掉了 53 Hz（255 → 201.5）。这是取长参考的理由。</p>

<p><b>三、但童声会带来快语速。</b>童声输出的 231–242 wpm，比马修 155 wpm 快 50%。
孩子说话本来就快，做台词没问题；要做睡前旁白就得压——用 edit 整段 rate（兑现 84–93%）能拉回来。</p>

<h2>一个必须说明的坑：Qwen 生成长文本会把音色压低</h2>
<p>同一句描述 <code>An eleven-year-old English boy...</code>，短句（3.68s）产出 255 Hz，
但换成 37 词长文本（13.04s）只剩 <b>154.6 Hz</b>；<code>charles_quiet</code> 更夸张，99.5 Hz。
<b>所以不能用 Qwen 的长输出直接当参考</b>，会得到低音男声。短句参考才准。</p>

<p>第 ⑦ 段是为这个坑做的对照：把 3.68 秒短参考拼成 11.74 秒（<code>boy10_quiet×3</code>）。
结果 <b>F0 保真从 79% 提到 95%</b>（255 → 243.3），但声纹反而从 0.7776 掉到 0.5761。
说明「音高」和「音色包络」是两回事——拼长能修音高，修不了包络。</p>

<p>所以两个版本各有取舍：<b>短参考音色更像（0.78）但音高偏低（200 Hz）；拼接版音高更准（243 Hz）但音色偏差（0.58）</b>。
哪个更"像 Charles"，得听。</p>

<h2>落地方式</h2>
<p>选定一个童声参考后，生产链完全不变：</p>
<p><code>Charles 参考音 → dots tts 生成 → emo 打情绪 → edit 整段 rate 控速 → 后期插停顿</code></p>
<p>emo 的 8 种情绪、句首/句中/句尾任意位置、8–11 词范围，全部照旧可用——
这些能力不依赖音色是成人还是儿童。</p>

<div class="foot">
参考音：Qwen3-TTS-12Hz-1.7B-VoiceDesign（文字描述驱动，无需参考音）<br>
生成：dots.tts DotTTS-Edit-GGUF q8_0 / Vulkan / seed 42<br>
测试文本：He did not want to go into the house. He stood at the gate and looked back at the road,
and thought about the long way he had come.（29 词）
</div>
</div></body></html>""")

with io.open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write("".join(html))
print("written", OUT_HTML, os.path.getsize(OUT_HTML), "bytes,", len(cards), "clips")
