# -*- coding: utf-8 -*-
"""前三章配音台本页。"""
import base64
import json
import os
import subprocess

import numpy as np
import parselmouth
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
D = "G:/_setup/ch123"
TMP = "G:/_setup/_ch123_audio"
OUT_HTML = "G:/_setup/castle_ch123.html"
os.makedirs(TMP, exist_ok=True)

ZH = {
    "L002": "我从来不怕。",
    "L005": "他看起来只像他那些死掉的旧蛾子。",
    "L008": "那也不算新鲜事，对吧？",
    "L011": "我又不会弄坏什么。为什么不能去？",
    "L014": "那我现在能拿钥匙吗？",
    "L017": "没人陪我打板球。",
    "L019": "反正我也不喜欢板球。",
    "L030": "蝴蝶只是上学期一阵风。我们抓了幼虫看它们孵化。现在没人感兴趣了。",
    "L031": "你以前为什么不带我来这儿？",
    "L033": "那是好几年前了。",
    "L035": "我猜你那时候跟祖父吵翻了。",
    "L046": "这是我的房子，是私人的。我先来的。谁都不该进来。",
    "L044": "我挺好的。一点问题都没有。",
    "L045": "没什么事。",
    "L050": "噢——那是什么？你找到什么了？",
    "L051": "没什么，什么都不是。就是颗小石子。",
    "L052": "我不想让你来这儿。",
    "L053": "你来这儿干什么？",
    "L054": "你干吗非得找个新地方住？",
    "L055": "等我父亲死了，这房子就归我。我就是主人了。全都是我的。",
    "L056": "那没什么。不过是栋旧房子。",
    "L057": "楼下有个很值钱的东西。你从没见过的东西。",
    "L058": "那又怎样？",
    "L059": "我祖父就死在这个房间。没多久以前。他躺在那张床上死的。现在那是你的床。",
    "L060": "你以前住哪儿？",
    "L061": "一套公寓。",
    "L062": "你自己的公寓？",
    "L063": "是——不是。嗯，是在别人家的房子里。",
    "L064": "那你们只是租客。",
    "L065": "那其实不是你们的。",
    "L066": "你父亲为什么没买一栋像样的房子？",
    "L067": "我父亲死了。",
    "L068": "嗯，我母亲买不起房子，她有什么办法？这我们也无能为力。",
    "L069": "那你父亲该给你留点钱才对，不是吗？他没有房子吗？",
    "L070": "有。但只能卖掉。",
    "L071": "我不知道。",
    "L072": "为了还清他所有的债。",
    "L074": "你记得你父亲吗？",
    "L075": "噢，记得。嗯——有一点。他当过飞行员。他参加过不列颠空战。我有……我有他的照片。",
    "L077": "是他在空战里的照片吗？",
    "L078": "不是。但是……",
    "L079": "我不信你。你是个骗子。不列颠空战是打仗时候的事。",
    "L080": "嗯，我知道。谁都知道。",
    "L081": "那是很多年前，几十年前。那是历史。他不可能参加过。",
    "L083": "照片在这儿，看——那是我父亲。",
    "L084": "我问你他什么时候死的。",
    "L085": "几年前。我大概五岁。或者六岁。",
    "L086": "那他那时候该挺老了。他多大？",
    "L087": "我不知道。挺老的吧。你看，照片在这儿。",
    "L088": "他老，我跟你说过了。他参加不列颠空战的时候二十岁。那是战争。",
    "L089": "你上哪个学校？",
    "L090": "在威尔士。",
    "L091": "我猜威尔士得有一百所学校。不止一百所。",
    "L092": "叫圣文森特。",
    "L093": "那是所正经学校吗？",
    "I00": "他的皮肤已经死了，他想。又老又干。",
    "I01": "病房里有一股酸味。",
    "I02": "他不会让他们看出他害怕。",
    "I03": "这不是他的房子。这里没有一样东西是他的。",
}

CH = [
    ("第一章 · 祖父的病床与红房间", "#4a7fb5",
     "Edmund 和父亲 Joseph 的对话。全书第一次出现他的声音：不吵、不闹，只是把话说得很平。", ["L002", "L005", "L008", "L011", "L014", "L017", "L019", "L030", "L031", "L033", "L035", "L046"]),
    ("第二章 · Charles 来了", "#b5734a",
     "陌生男孩进门那一刻。Edmund 的第一反应不是好奇，是被侵入。", ["L044", "L045", "L050", "L051", "L052", "L053", "L054", "L055", "L056", "L057", "L058", "L059"]),
    ("第三章 · 两个男孩互相试探", "#3d7d6b",
     "从住处问到父亲，一层层往下挖。Charles 越答越低，Edmund 越问越稳。", ["L060", "L061", "L062", "L063", "L064", "L065", "L066", "L067", "L068", "L069", "L070", "L071", "L072", "L074", "L075", "L077", "L078", "L079", "L080", "L081", "L083", "L084", "L085", "L086", "L087", "L088", "L089", "L090", "L091", "L092", "L093"]),
    ("无引号的内心独白", "#7a6f8a",
     "原文没有引号，是叙述里的心理描写。按内心独白念，用角色本音，不打情绪标签。", ["I00", "I01", "I02", "I03"]),
]


def f0(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=420)
    f = pit.selected_array["frequency"]
    m = f > 0
    return float(np.median(f[m])) if m.any() else 0.0


def mp3(p):
    m = os.path.join(TMP, os.path.basename(p) + ".mp3")
    if not os.path.exists(m):
        subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                        "-codec:a", "libmp3lame", "-b:a", "72k", "-ar", "22050", "-ac", "1", m],
                       capture_output=True)
    with open(m, "rb") as f:
        return base64.b64encode(f.read()).decode()


CHK = json.load(open("G:/_setup/_ch123_check.json", encoding="utf-8")) if os.path.exists("G:/_setup/_ch123_check.json") else {}

WHO = {"C": ("Charles", "#3d7d6b"), "E": ("Edmund", "#8a6ab5")}
EMO_ZH = {"calm": "平静", "angry": "愤怒", "sad": "难过", "surprised": "惊讶",
          "disgusted": "厌恶", "melancholic": "低落", "happy": "兴奋", "afraid": "害怕",
          "neutral": "中性"}

cards = []
for title, color, note, keys in CH:
    rows = []
    for k in keys:
        p = os.path.join(D, k + ".wav")
        if not os.path.exists(p):
            continue
        c = CHK.get(k, {})
        who = c.get("who", "E")
        nm, wc = WHO.get(who, ("?", "#666"))
        emo = c.get("emo")
        a, sr = sf.read(p, dtype="float32", always_2d=True)
        dur = len(a) / sr
        acc = c.get("acc")
        asr_cls = "good" if (acc or 0) >= 90 else ("mid" if (acc or 0) >= 75 else "bad")
        rows.append(
            '<div class="ln"><div class="lh">'
            '<span class="who" style="color:%s">%s</span>'
            '<span class="emo">%s</span>'
            '<span class="meta">%.2fs · F0 %.0f Hz · 词准 <b class="%s">%s%%</b></span></div>'
            '<div class="en">%s</div><div class="zh">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (wc, nm, EMO_ZH.get(emo, emo or "—"), dur, f0(p), asr_cls,
               acc if acc is not None else "—", c.get("text", ""), ZH.get(k, ""), mp3(p)))
    if rows:
        cards.append('<div class="sec"><h2 style="border-left-color:%s">%s</h2>'
                     '<div class="note">%s</div>%s</div>' % (color, title, note, "".join(rows)))

CSS = """*{box-sizing:border-box}
body{margin:0;padding:30px 18px 70px;background:#0f1116;color:#c8cfda;
 font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:920px;margin:0 auto}
h1{font-size:23px;font-weight:600;color:#eef2f8;margin:0 0 5px}
.sub{color:#7d8797;font-size:13px;margin-bottom:16px}
.sec{margin:22px 0}
h2{font-size:16px;color:#e6ecf5;margin:0 0 6px;padding-left:10px;border-left:3px solid #4a7fb5}
.note{color:#8b95a6;font-size:12.5px;margin:0 0 10px;padding-left:11px}
.ln{background:#161a21;border:1px solid #232a35;border-radius:9px;padding:10px 13px;margin:7px 0}
.lh{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap;margin-bottom:4px}
.who{font-weight:600;font-size:13px}
.emo{background:#1b2430;color:#8fb8e0;font-size:11px;border-radius:20px;padding:1px 8px}
.meta{color:#6f7c8e;font-size:11px;margin-left:auto;font-variant-numeric:tabular-nums}
.en{color:#dfe6f0;font-size:13.5px;line-height:1.6}
.zh{color:#7d8797;font-size:12px;margin:1px 0 6px}
audio{width:100%;height:30px}
.good{color:#6fcf9a}.mid{color:#d4b062}.bad{color:#e08a8a}
.sum{background:#141821;border:1px solid #232a35;border-radius:10px;padding:13px 16px;
 font-size:13px;color:#a9b3c2;margin:14px 0;line-height:1.8}
.sum b{color:#e6ecf5}
.sum code{background:#1b2129;color:#9fc4e8;padding:1px 5px;border-radius:4px;font-size:11.5px}
"""

html = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>我是城堡之王 · 前三章配音台本</title><style>' + CSS + '</style></head><body><div class="wrap">'
        '<h1>前三章 · 逐句配音台本</h1>'
        '<div class="sub">音色：Charles = 法语原声中性锚（24.5s 拼接）· Edmund = Hooper 平静锚（13.6s）· 每句都过 ASR 逐词校对</div>'
        '<div class="sum"><b>怎么做的</b><br>'
        '每个角色只用<b>一个中性参考</b>锚音色，情绪靠 <code>&lt;emo&gt;</code> 标签局部注入——'
        '因为用「愤怒参考」生成出来的其实是另一个人的嗓子（互比只有 0.21）。<br>'
        '心理描写原文没有引号，单独归到最后一节，按内心独白处理，不打情绪标签。<br>'
        '每条生成完立刻过 ASR，缺词 ≥2 或词准 &lt;72% 判为吞字，重生成。</div>'
        + "".join(cards) +
        '<div class="sum"><b>Charles 的「生气」没有用 angry</b><br>'
        '实测 angry 会把 F0 抬高一个八度、音色跑掉。换成 <code>happy</code> 后 F0 从 211 Hz 降到 185 Hz，'
        '更贴少年本音，语气还是上扬的——揭穿对方时那种「我赢了」的调子，比纯愤怒更贴原文。</div>'
        '</div></body></html>')

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print("OK", OUT_HTML, round(os.path.getsize(OUT_HTML) / 1024 / 1024, 2), "MB")
