# -*- coding: utf-8 -*-
"""Charles 音色 v2：低音对照 + 跨语言克隆说明"""
import base64
import os
import subprocess

OUT_HTML = "G:/_setup/dots_charles2.html"
TMP = "G:/_setup/_charles_audio2"

ROWS = [
    dict(id="quiet", name="旧版 · boy10_quiet", tag="200.5 Hz",
         path="G:/_setup/dots_edit2/MCH_quiet.wav",
         note="上一轮给你的版本，你说太女性化。参考本身 255Hz，落在女声区。"),
    dict(id="c3ref", name="新参考 · c3_breaking（Qwen 直出）", tag="158.3 Hz",
         path="E:/tts-models/out/charles_ref2/c3_breaking.wav",
         note="描述改成「十二岁刚开始变声、低、略哑」，没写 sad/lonely/wistful。"),
    dict(id="c3", name="新版 · dots 克隆 c3 ★", tag="169.4 Hz", best=True,
         path="G:/_setup/dots_edit2/MCH_c3.wav",
         note="声纹 0.9279（同一人档），比旧版低 31Hz。同一段文本，可直接 A/B。"),
    dict(id="matthew", name="马修基准（成年男声）", tag="72.5 Hz",
         path="G:/_setup/dots_edit2/MCH_matthew.wav",
         note="生产链现在的声音，放这里只为让你有低音参照。"),
]


def to_mp3(src, dst):
    subprocess.run(["E:/tool/oopz/ffmpeg.exe", "-y", "-i", src, "-codec:a", "libmp3lame",
                    "-b:a", "96k", "-ar", "24000", "-ac", "1", dst], capture_output=True)


def b64(p):
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()


os.makedirs(TMP, exist_ok=True)
cards = []
for r in ROWS:
    if not os.path.exists(r["path"]):
        continue
    mp3 = os.path.join(TMP, r["id"] + ".mp3")
    to_mp3(r["path"], mp3)
    cards.append((r, b64(mp3)))

parts = []
parts.append("""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Charles 音色 v2</title><style>
*{box-sizing:border-box}
body{margin:0;padding:34px 22px 70px;background:#0f1116;color:#c8cfda;
 font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:820px;margin:0 auto}
h1{font-size:23px;font-weight:600;color:#eef2f8;margin:0 0 6px}
.sub{color:#7d8797;font-size:13px;margin-bottom:24px}
h2{font-size:16px;font-weight:600;color:#e2e8f2;margin:32px 0 12px;
 padding-left:11px;border-left:3px solid #4a7fb5}
p{color:#a9b3c2;margin:10px 0}
.card{background:#161a21;border:1px solid #232a35;border-radius:12px;
 padding:15px 17px;margin:12px 0}
.card.best{border-color:#3d6b45;background:#151d18}
.hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.nm{font-weight:600;color:#e6ecf5;font-size:14.5px}
.card.best .nm{color:#8fd39b}
.tag{font-size:12px;color:#7fb3e8;font-variant-numeric:tabular-nums;
 background:#1b2430;border-radius:20px;padding:2px 10px}
.note{font-size:12.5px;color:#8b95a6;margin:6px 0 9px}
audio{width:100%;height:34px;margin-top:4px}
ul{color:#a9b3c2;padding-left:20px;margin:8px 0}
li{margin:6px 0}
code{background:#1b2129;color:#9fc4e8;padding:1px 5px;border-radius:4px;font-size:12.5px}
</style></head><body><div class="wrap">
<h1>Charles 音色 v2 — 把音高压下来</h1>
<div class="sub">同一段文本（29 词旁白），dots tts，seed 42，只换 voice_ref</div>
""")

parts.append("<h2>A/B 对照</h2>\n")
for r, mp3 in cards:
    cls = "card best" if r.get("best") else "card"
    parts.append(
        '<div class="%s"><div class="hd"><div class="nm">%s</div>'
        '<div class="tag">%s</div></div>'
        '<div class="note">%s</div>'
        '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>\n'
        % (cls, r["name"], r["tag"], r["note"], mp3))

parts.append("""
<h2>为什么会偏女声</h2>
<p>不是 dots 的问题，是<b>参考音频本身</b>的问题。上一轮的 <code>boy10_quiet</code> 是 255 Hz——
成年女声的中位区就在 200–260 Hz。dots 的音色是 1:1 跟参考走的，参考在女声区，输出就在女声区。</p>
<p>这一轮把描述从「soft / light / timid / wistful」换成「刚开始变声 / 低 / 略哑」，
Qwen 直出就从 255 Hz 掉到 <b>158 Hz</b>，dots 克隆后 <b>169 Hz</b>，落到少年男声区。</p>

<h2>关于「克制、内敛」</h2>
<p>这件事和音色是两条独立的线，而且<b>比音色好办</b>：</p>
<ul>
<li>dots 默认输出就是<b>平的</b>——不打 emo 标签，它不会自己加情绪。</li>
<li>所以「克制」= <b>不加 emo</b>，只靠标点停顿和语速。</li>
<li>反过来说，之前那些 sad / tearful 的 Qwen 描述不只是把音色调软，还给了模型一个「有情绪」的底子。
真正克制的描述应该写 <code>flat</code> / <code>controlled</code> / <code>no audible emotion</code>，而不是 sad。</li>
<li>后面需要他爆发（书里那几场对峙）时，再单独给那几句打 emo——emo 是严格局部的，不会污染整段。</li>
</ul>

<h2>下一步</h2>
<p>这版 169 Hz 你听听够不够低。如果还要再低，方向是把 Qwen 描述里的 low 程度再加半档，
落在 130–150 Hz；但要注意 11 岁男孩低于 130 Hz 就开始像成年男人了。</p>
</div></body></html>
""")

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write("".join(parts))
print("OK", OUT_HTML, round(os.path.getsize(OUT_HTML) / 1024, 1), "KB", "cards=", len(cards))
