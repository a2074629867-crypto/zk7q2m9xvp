# -*- coding: utf-8 -*-
"""生成前三章最终试听页 castle_ch123.html（数据来自 _ch123_final.json）。"""
import base64
import json
import os
import re
import subprocess

FF = "E:/tool/oopz/ffmpeg.exe"
D = "G:/_setup/ch123"
TMP = "G:/_setup/_ch123_audio"
OUT_HTML = "G:/_setup/castle_ch123.html"
os.makedirs(TMP, exist_ok=True)

# 从旧构建器里取出中文字幕表
src = open("G:/_setup/build_ch123_page.py", encoding="utf-8").read()
m = re.search(r"^ZH = \{.*?^\}", src, re.S | re.M)
ns = {}
exec(m.group(0), ns)
ZH = ns["ZH"]

DATA = json.load(open("G:/_setup/_ch123_final.json", encoding="utf-8"))

CH = [
    ("第一章 · 祖父的病床与红房间", "#4a7fb5",
     "Edmund 和父亲 Joseph 的对话。全书第一次出现他的声音：不吵、不闹，只是把话说得很平。",
     ["L002", "L005", "L008", "L011", "L014", "L017", "L019", "L030", "L031", "L033", "L035", "L046"]),
    ("第二章 · Charles 来了", "#b5734a",
     "陌生男孩进门那一刻。Edmund 的第一反应不是好奇，是被侵入。",
     ["L044", "L045", "L050", "L051", "L052", "L053", "L054", "L055", "L056", "L057", "L058", "L059"]),
    ("第三章 · 两个男孩互相试探", "#3d7d6b",
     "从住处问到父亲，一层层往下挖。Charles 越答越低，Edmund 越问越稳。",
     ["L060", "L061", "L062", "L063", "L064", "L065", "L066", "L067", "L068", "L069", "L070",
      "L071", "L072", "L074", "L075", "L076", "L077", "L078", "L079", "L080", "L081", "L083",
      "L084", "L085", "L086", "L087", "L088", "L089", "L090", "L091", "L092", "L093"]),
    ("无引号的内心独白", "#7a6f8a",
     "原文没有引号，是叙述里的心理描写。按内心独白念，用角色本音，不打情绪标签。",
     ["I00", "I01", "I02", "I03"]),
]

WHO = {"C": ("Charles", "#3d7d6b"), "E": ("Edmund", "#8a6ab5")}
EMO_ZH = {"calm": "平静", "angry": "愤怒", "sad": "难过", "surprised": "惊讶",
          "disgusted": "轻蔑", "melancholic": "低落", "happy": "兴奋", "afraid": "害怕",
          "neutral": "中性", "拆句": "拆句"}


def mp3(p):
    m = os.path.join(TMP, os.path.basename(p) + ".mp3")
    if not os.path.exists(m) or os.path.getmtime(m) < os.path.getmtime(p):
        subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                        "-codec:a", "libmp3lame", "-b:a", "72k", "-ar", "22050", "-ac", "1", m],
                       capture_output=True)
    with open(m, "rb") as f:
        return base64.b64encode(f.read()).decode()


def cls(v, good, mid):
    return "good" if v >= good else ("mid" if v >= mid else "bad")


cards = []
for title, color, note, keys in CH:
    rows = []
    for k in keys:
        d = DATA.get(k)
        if not d:
            continue
        p = os.path.join(D, k + ".wav")
        nm, wc = WHO.get(d["who"], ("?", "#666"))
        emo = d.get("emo")
        spk = d.get("spk", 0)
        acc = d.get("acc", 0)
        rows.append(
            '<div class="ln"><div class="lh">'
            '<span class="who" style="color:%s">%s</span>'
            '<span class="emo">%s</span>'
            '%s'
            '<span class="meta">%.2fs · %d wpm · 声纹 <b class="%s">%.2f</b> · 词准 <b class="%s">%d%%</b></span>'
            '</div><div class="en">%s</div><div class="zh">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (wc, nm, EMO_ZH.get(emo, emo or "—"),
               '<span class="tag">已修</span>' if d.get("fixed") else "",
               d["dur"], d["wpm"], cls(spk, 0.65, 0.5), spk, cls(acc, 90, 75), acc,
               d["text"], ZH.get(k, ""), mp3(p)))
    if rows:
        cards.append('<div class="sec"><h2 style="border-left-color:%s">%s<span class="cnt">%d</span></h2>'
                     '<div class="note">%s</div>%s</div>' % (color, title, len(rows), note, "".join(rows)))

CSS = """*{box-sizing:border-box}
body{margin:0;padding:30px 18px 70px;background:#0f1116;color:#c8cfda;
 font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:940px;margin:0 auto}
h1{font-size:23px;font-weight:600;color:#eef2f8;margin:0 0 5px}
.sub{color:#7d8797;font-size:13px;margin-bottom:16px}
.sec{margin:22px 0}
h2{font-size:16px;color:#e6ecf5;margin:0 0 6px;padding-left:10px;border-left:3px solid #4a7fb5;
 display:flex;align-items:center;gap:8px}
.cnt{color:#6f7c8e;font-size:11.5px;font-weight:400}
.note{color:#8b95a6;font-size:12.5px;margin:0 0 10px;padding-left:11px}
.ln{background:#161a21;border:1px solid #232a35;border-radius:9px;padding:10px 13px;margin:7px 0}
.lh{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:4px}
.who{font-weight:600;font-size:13px}
.emo{background:#1b2430;color:#8fb8e0;font-size:11px;border-radius:20px;padding:1px 8px}
.tag{background:#2a2118;color:#d4a86a;font-size:10.5px;border-radius:20px;padding:1px 7px}
.meta{color:#6f7c8e;font-size:11px;margin-left:auto;font-variant-numeric:tabular-nums}
.en{color:#dfe6f0;font-size:13.5px;line-height:1.6}
.zh{color:#7d8797;font-size:12px;margin:1px 0 6px}
audio{width:100%;height:30px}
.good{color:#6fcf9a}.mid{color:#d4b062}.bad{color:#e08a8a}
.sum{background:#141821;border:1px solid #232a35;border-radius:10px;padding:13px 16px;
 font-size:13px;color:#a9b3c2;margin:14px 0;line-height:1.85}
.sum b{color:#e6ecf5}
.sum code{background:#1b2129;color:#9fc4e8;padding:1px 5px;border-radius:4px;font-size:11.5px}
.sum table{border-collapse:collapse;margin:8px 0;font-size:12.5px}
.sum td,.sum th{border-bottom:1px solid #232a35;padding:3px 12px 3px 0;text-align:left}
.sum th{color:#8b95a6;font-weight:500}
"""

n = len(DATA)
bad_spk = sum(1 for v in DATA.values() if v["spk"] < 0.5)
bad_acc = sum(1 for v in DATA.values() if v["acc"] < 80)

html = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>我是城堡之王 · 前三章配音台本</title><style>' + CSS + '</style></head><body><div class="wrap">'
        '<h1>前三章 · 逐句配音台本</h1>'
        '<div class="sub">%d 条 · 音色：Charles = 法语原声中性锚（24.5s）· Edmund = Hooper 平静锚（13.6s）· '
        '每条都过 ASR 逐词校对与声纹核对</div>' % n
        + '<div class="sum"><b>这一版改了什么</b><br>'
          '① <b>Hooper 的 angry 全部换成 disgusted</b>——angry 把 F0 抬高 50–100 Hz、声纹掉到 0.31–0.55；'
          'happy 会在句首带笑声。换成 disgusted（轻蔑）后声纹回到 0.63–0.78，F0 也落回少年区。<br>'
          '② <b>语速过快的长句改成拆句生成</b>——dots 的 <code>--speaking-rate</code> 是空参数（0.82 与 0.88 输出字节完全相同），'
          '只能靠分句 + 标点停顿把节奏拉开。标记「拆句」的就是这一批。<br>'
          '③ <b>疑问语气</b>：实测 yes/no 与反义疑问句在句尾会自然升 2–3 半音（<code>will it?</code> 202→231 Hz），'
          '但只占最后 150 ms，听感很弱；wh- 疑问句本来就是降调（英语如此）。'
          '所以把 <code>..., will it?</code> / <code>..., then?</code> 切开单独生成，收尾就有了升调。'
          '种子扫描、局部 emo、疑问句密集参考三条路都试过，前两条无效，第三条能把句尾抬到 +4.9 半音但声纹只剩 0.10（换人）。<br>'
          '④ <b>极短句</b>（<code>I don\'t know.</code> / <code>No.</code>）会让模型立刻 EOS，只吐 0.08 秒空音；'
          '改成与下一句合并生成再按静音切开。</div>' % ()
        + "".join(cards) +
        '<div class="sum"><b>还差什么</b><br>'
        '声纹低于 0.5 的 %d 条、词准低于 80%% 的 %d 条已在卡片上标红——'
        '多半是 2–4 个词的极短句，声纹模型本身取样不足，听感上未必有问题，需要你耳朵定。'
        '疑问句的升调仍是「短句自然升」，没有做 DSP 强行抬音高（试过 rubberband 升调，'
        '能抬到 +3 半音但会把句尾拉成阶梯，风险大于收益）。</div>' % (bad_spk, bad_acc)
        + '</div></body></html>')

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print("OK", OUT_HTML, round(os.path.getsize(OUT_HTML) / 1024 / 1024, 2), "MB", n, "条")
