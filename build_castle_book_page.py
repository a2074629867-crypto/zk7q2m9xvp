# -*- coding: utf-8 -*-
"""8 组法语原声音色 · 念小说对应台词"""
import base64
import os
import subprocess

import numpy as np
import parselmouth
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
OUT_HTML = "G:/_setup/castle_book_lines.html"
TMP = "G:/_setup/_bk_audio"
DOTS = "G:/_setup/dots_edit2"
REF = "G:/_setup/castle_fr_ref"

ROWS = [
    ("BK_1", "1_charles_normal", "Charles", "日常说话", "#4a7fb5",
     "It's called St Vincent's. That's nothing. It's only an old house. I'm all right.",
     "学校叫圣文森特。那没什么。不过是栋旧房子。我没事。",
     "初次见面被追问学校、被压一头时的应答。三句都是短句，克制，不解释。"),
    ("BK_2", "2_charles_soft", "Charles", "轻声", "#3d7d6b",
     "I'm all right. I don't want to touch one, that's all. No. I'd rather not.",
     "我没事。我只是不想碰它们，就这样。不。我宁愿不要。",
     "被逼摸蛾子标本时。全库最低音色，句句往回收，拒绝但不吵。"),
    ("BK_3", "3_charles_excited", "Charles", "激动", "#b5734a",
     "I'm a bowman, I'm the head warrior of this castle. If I shoot an arrow, I can kill you.",
     "我是弓手，我是这座城堡的主将。我一箭就能射死你。",
     "全书他唯一一次站上城墙、真正觉得自己赢了。唯一的宣言式台词。"),
    ("BK_4", "4_charles_angry", "Charles", "生气", "#b54a4a",
     "But I wouldn't go on whining, like you. Scaredy Hooper. You are scared. You're scared now.",
     "可我不会像你那样一直哼哼唧唧。胆小鬼霍珀。你怕了。你现在就怕了。",
     "火堆旁反攻。三句一层层逼上去，是 Charles 少有的主动进攻。"),
    ("BK_5", "5_hooper_loud", "Hooper", "大声", "#8a6ab5",
     "It's because of me. You're scared of me, Kingshaw, you're Mummy's little scaredy-pet. "
     "You don't know what I might do to you, I could do anything at all.",
     "是因为我。你怕我，金斯肖，你是妈妈的小胆小鬼。你不知道我会对你做什么，我什么都做得出来。",
     "揭穿对方恐惧、宣示无限权力。Hooper 的支配态峰值。"),
    ("BK_6", "6_hooper_calm", "Hooper", "平静", "#6a7f8a",
     "I'm King of the Castle! You'd better come down, show-off, if you fall you'll split your head open.",
     "我是城堡之王！你最好下来，爱显摆的家伙，摔下去你脑袋就开花了。",
     "书名那句。喊完立刻转成冷淡的威胁，一扬一收。"),
    ("BK_6b", "6b_hooper_scold", "Hooper", "质问", "#7a6f5a",
     "Open one of the cases, then. I'll let you. Why not? Scaredy-baby, scared of a moth! Pick one up.",
     "那你打开一个盒子。我让你开。怎么不敢？胆小鬼宝宝，怕一只蛾子！拿一只起来。",
     "逼人摸死蛾子。不吼，一句接一句压，靠停顿施压。"),
    ("BK_7", "7_hooper_begging", "Hooper", "求饶", "#8a6a8a",
     "I don't like it here, I want to go home. I don't want to be lost. I want to go home.",
     "我不喜欢这里，我要回家。我不想迷路。我要回家。",
     "树林里迷路、终于示弱。同一句话重复两遍，第二遍更低。"),
]


def f0(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=400)
    f = pit.selected_array["frequency"]
    m = f > 0
    return float(np.median(f[m])) if m.any() else 0.0


def dur(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return len(a) / sr


def to_mp3(src, dst):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-codec:a", "libmp3lame", "-b:a", "96k", "-ar", "24000", "-ac", "1", dst],
                   capture_output=True)


def b64(p):
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()


os.makedirs(TMP, exist_ok=True)
cards = []
for bid, gid, who, mood, color, en, zh, note in ROWS:
    p = os.path.join(DOTS, bid + ".wav")
    if not os.path.exists(p):
        continue
    refp = os.path.join(REF, gid + ".wav")
    rf = f0(refp) if os.path.exists(refp) else 0
    of = f0(p)
    m = os.path.join(TMP, bid + ".mp3")
    to_mp3(p, m)
    cards.append(
        '<div class="card" style="border-left-color:%s"><div class="hd">'
        '<div class="nm">%s · %s</div>'
        '<div class="tag">%.2fs · 参考 %.0f → 输出 %.0f Hz</div></div>'
        '<div class="en">%s</div><div class="zh">%s</div>'
        '<div class="note">%s</div>'
        '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
        % (color, who, mood, dur(p), rf, of, en, zh, note, b64(m)))

html = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>城堡之王 · 音色念小说台词</title><style>
*{box-sizing:border-box}
body{margin:0;padding:32px 20px 70px;background:#0f1116;color:#c8cfda;
 font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:23px;font-weight:600;color:#eef2f8;margin:0 0 6px}
.sub{color:#7d8797;font-size:13px;margin-bottom:22px}
.card{background:#161a21;border:1px solid #232a35;border-left:3px solid #4a7fb5;
 border-radius:10px;padding:14px 16px;margin:11px 0}
.hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.nm{font-weight:600;color:#e6ecf5;font-size:14px}
.tag{font-size:11.5px;color:#7fb3e8;font-variant-numeric:tabular-nums;
 background:#1b2430;border-radius:20px;padding:2px 9px;white-space:nowrap}
.en{color:#dfe6f0;font-size:13.5px;margin:8px 0 3px;line-height:1.65}
.zh{color:#8b95a6;font-size:12.5px;margin-bottom:6px}
.note{color:#7d8797;font-size:12.5px;margin:6px 0 8px;border-top:1px solid #232a35;padding-top:6px}
audio{width:100%;height:32px}
.chain{background:#141821;border:1px solid #232a35;border-radius:10px;
 padding:13px 16px;font-size:13px;color:#a9b3c2;margin:16px 0}
.chain code{background:#1b2129;color:#9fc4e8;padding:1px 5px;border-radius:4px;font-size:12px}
</style></head><body><div class="wrap">
<h1>8 组音色 · 念小说里对应的台词</h1>
<div class="sub">音色来自电影法语原声（HTDemucs 分离 + RNNoise）· 台词逐字取自 Susan Hill 原著 · dots.tts 生成</div>
<div class="chain"><b>做法</b>　每组音色 = 电影里该情绪的真人参考（8–14s），
<code>--task tts</code> + <code>--reference-text</code>（法语转写）→ 英文台词。
音色通道（CAM++ x-vector）不含语言信息，所以法语人声可以直接驱动英语发音。<br>
<span style="color:#7d8797;font-size:12.5px">参考 F0 与输出 F0 的差值反映台词本身的表情强度：喊叫/质问会自然抬升 40–90 Hz。</span></div>
""" + "".join(cards) + """
<div class="chain">
<b>两个角色的声学差别</b><br>
Charles 日常 <b>241 Hz</b>、轻声 <b>179 Hz</b>——他越收敛越低，跨度 62 Hz。<br>
Hooper 平静 <b>210 Hz</b>、大声 <b>330 Hz</b>——他越激动越高，跨度 120 Hz。<br>
<span style="color:#7d8797;font-size:12.5px">同一本书里两个孩子的表演逻辑正好相反：一个往里压，一个往外放。
标注 emo 时 Charles 用低强度、Hooper 用高强度，不要对称处理。</span>
</div>
</div></body></html>"""

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print("OK", OUT_HTML, round(os.path.getsize(OUT_HTML) / 1024, 1), "KB", "cards=", len(cards))
