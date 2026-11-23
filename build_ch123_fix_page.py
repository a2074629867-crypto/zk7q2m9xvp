# -*- coding: utf-8 -*-
"""L088 修复 A/B 试听页。"""
import base64
import html
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import soundfile as sf

import ch123_level as L
import ch123_rebuild as RB
import ch123_tone as T

FF = "E:/tool/oopz/ffmpeg.exe"
TMP = "G:/_setup/_mp3fix"
OUT = "G:/_setup/castle_ch123_fix.html"
os.makedirs(TMP, exist_ok=True)


def mp3_b64(p):
    m = os.path.join(TMP, os.path.basename(p).replace(".wav", "") + "_" + str(abs(hash(p)) % 99999) + ".mp3")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                    "-codec:a", "libmp3lame", "-b:a", "80k", "-ar", "22050", "-ac", "1", m],
                   capture_output=True)
    with open(m, "rb") as f:
        return base64.b64encode(f.read()).decode()


def info(path, words):
    r = T.probe(path)
    f0s = [round(x["f0"]) for x in r["rows"]]
    dbs = [round(x["db"]) for x in r["rows"]]
    drops = [dbs[i] - dbs[i + 1] for i in range(len(dbs) - 1)]
    md = max(drops) if drops else 0
    return dict(dur=r["dur"], wpm=words / r["dur"] * 60, f0=f0s, db=dbs, span=r["span"],
                tail=r["tail_drop"], decay=r["decay"], md=md)


def badge(i):
    ok = True
    msgs = []
    if any(f > 300 or f < 175 for f in i["f0"]):
        msgs.append("音区出界")
        ok = False
    if i["md"] > 6:
        msgs.append("句间掉 %d dB" % i["md"])
        ok = False
    if i["wpm"] > 215:
        msgs.append("语速赶")
        ok = False
    if ok:
        return '<span class="ok">稳</span>'
    return '<span class="bad">%s</span>' % " · ".join(msgs)


def card(title, tagline, old, new, words, note=""):
    blocks = []
    for label, p, cls in (("旧版", old, "old"), ("新版", new, "new")):
        if not p or not os.path.exists(p):
            continue
        i = info(p, words)
        blocks.append("""
        <div class="row %s">
          <div class="lab">%s</div>
          <div class="stats">
            <span>%.2fs</span><span>%.0f wpm</span><span>F0 %s</span><span>电平 %s</span>%s
          </div>
          <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>
          <div class="flags">跨度 %.0fHz · 末句跌 %.0fHz%s</div>
        </div>""" % (cls, label, i["dur"], i["wpm"],
                     "/".join(str(x) for x in i["f0"]),
                     "/".join(str(x) for x in i["db"]),
                     badge(i), mp3_b64(p), i["span"], i["tail"],
                     ("<br><span class='note'>" + note + "</span>") if (note and cls == "new") else ""))
    return """
    <section>
      <h3>%s</h3>
      <p class="tag">%s</p>
      %s
    </section>""" % (html.escape(title), html.escape(tagline), "".join(blocks))


SECTIONS = []

SECTIONS.append(card(
    "L088　He's old, I told you. When he was in the Battle of Britain, he was twenty. That was the war.",
    "旧版拆成 4 句、每句各打一个 sad，四段是四次独立表演：首句 304Hz（发紧）、末句 145Hz（塌到 Charles 地板以下），中间电平还掉 10dB。新版整句一次生成、不加 emo、自己重排停顿，再降到 192 wpm。",
    "G:/_setup/ch123_old/L088.wav", "G:/_setup/ch123/L088.wav", 23,
    "整句生成 → 按句间静音切段 → 逐段电平对齐 → 加长句间停顿 → rubberband 0.80x"))

SECTIONS.append(card(
    "L075　Oh, yes. Well, a bit. He was a pilot, once. He was in the Battle of Britain.",
    "旧版 8.32s，最后一段掉到 −40dB（“I've got...” 前面那口气塌了）。新版四段 223/224/221/228Hz——跨度 7Hz，几乎是一条直线。",
    "G:/_setup/ch123_old/L075.wav", "G:/_setup/ch123/L075.wav", 17))

SECTIONS.append(card(
    "L083　Here's the picture. Look, that's my father.",
    "旧版三段全在 269–290Hz（整体飙高，像兴奋），新版 229/255/221，落回正常音区。",
    "G:/_setup/ch123_old/L083.wav", "G:/_setup/ch123/L083.wav", 7))

SECTIONS.append(card(
    "L085　A few years ago. I was about five. Or six.",
    "旧版末段飙到 266Hz（“Or six.” 吊起来），新版 194/183/179，跨度剩 15Hz。",
    "G:/_setup/ch123_old/L085.wav", "G:/_setup/ch123/L085.wav", 9))

SECTIONS.append(card(
    "L087　I don't know. Quite old, I suppose. Look, then, there's the photograph.",
    "旧版第二段掉到 −34dB（“Quite old, I suppose.” 整句缩了），新版四段 −24/−25/−18/−23。",
    "G:/_setup/ch123_old/L087.wav", "G:/_setup/ch123/L087.wav", 13))

SECTIONS.append(card(
    "L068　Well, my mother can't afford to buy us a house, can she? We can't help that.",
    "旧版四段 297/264/325Hz——中间一句冲到 325，比 Charles 的激动参考（283）还高。新版两句 202/233，第二句做了 −2 半音校正。",
    "G:/_setup/ch123_old/L068.wav", "G:/_setup/ch123/L068.wav", 17))

SECTIONS.append(card(
    "L050　Oh, what is it? What have you found?",
    "原来是 surprised 标签，飙到 311/313Hz，像变了个人。改成不加 emo，281/261，降速到 227 wpm 保留那股兴奋。",
    None, "G:/_setup/ch123/L050.wav", 8))

SECTIONS.append(card(
    "L069　Your father should have left you some money, then, shouldn't he? Didn't he have a house?",
    "旧版 −15/−20/−18，中间一句掉 5dB；新版重排后 −25/−23/−24，F0 223/215/199。",
    "G:/_setup/ch123_old/L069.wav", "G:/_setup/ch123/L069.wav", 18))

SECTIONS.append(card(
    "L055　When my father dies, this house will belong to me. I shall be master. It'll all be mine.",
    "这条没有重生成——它的音区本来是好的（202/187/194），只是整体电平比其他条高 5dB。统一到 −24dBFS 就解决了。",
    None, "G:/_setup/ch123/L055.wav", 22))

BODY = "".join(SECTIONS)

HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>城堡之王 · 语调修复对照</title><style>
:root{--bg:#0f1115;--panel:#171a21;--line:#262b35;--fg:#e6e9ef;--dim:#8b93a3;--accent:#6ea8fe;--ok:#4ec9a0;--bad:#f2707f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 -apple-system,"Segoe UI","Microsoft Yahei",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:34px 20px 80px}
h1{font-size:23px;margin:0 0 6px;letter-spacing:.3px}
.sub{color:var(--dim);font-size:13.5px;margin:0 0 26px}
h3{font-size:15.5px;margin:0 0 4px;font-weight:600;line-height:1.5}
.tag{color:var(--dim);font-size:13px;margin:0 0 14px}
section{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 18px 14px;margin-bottom:18px}
.row{display:grid;grid-template-columns:56px 1fr;gap:6px 12px;align-items:center;padding:9px 10px;border-radius:10px;margin-bottom:8px;border:1px solid transparent}
.row.old{background:#1d1a1d;border-color:#33272c}
.row.new{background:#151d1b;border-color:#233b33}
.lab{font-size:12.5px;color:var(--dim);letter-spacing:.5px}
.row.new .lab{color:var(--ok)}
.stats{font-size:12.5px;color:var(--dim);display:flex;flex-wrap:wrap;gap:10px}
.stats span{background:#20242d;padding:1px 7px;border-radius:5px}
.row.new .stats span{background:#1b2a26}
audio{grid-column:2;width:100%;height:34px;margin-top:2px}
.flags{grid-column:2;font-size:12px;color:#6f7889}
.note{color:var(--ok)}
.ok{color:var(--ok);background:#16302a;padding:1px 7px;border-radius:5px;font-size:12px}
.bad{color:var(--bad);background:#331d22;padding:1px 7px;border-radius:5px;font-size:12px}
.legend{font-size:12.5px;color:var(--dim);background:#14171d;border:1px dashed var(--line);border-radius:10px;padding:12px 14px;margin-bottom:22px}
code{background:#20242d;padding:1px 5px;border-radius:4px;font-size:12px}
</style></head><body><div class="wrap">
<h1>语调修复对照 · 父亲这一段</h1>
<p class="sub">同一个语料，旧版 vs 新版。旧版的问题不是“小声”，是音区塌了 — Charles 正常 184–252Hz，旧版末句 145Hz。</p>
<div class="legend">
<b>怎么读这些数字</b><br>
<code>F0</code> 是按句间静音切开后，每句的基频中位（Hz）。Charles 这个角色在 184–252Hz 之间，<b>低于 175 就是“塌”</b>，高过 300 是“飘”。<br>
<code>电平</code> 每句的有声段 dB，相邻两句差 6dB 以上就是“越说越小”。<br>
<code>wpm</code> 每分钟词数，中文朗读一般 150–180，童声 180–210 算正常，超过 215 就赶了。
</div>
__BODY__
</div></body></html>""".replace("__BODY__", BODY)

with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML)
print("->", OUT, "%.2f MB" % (os.path.getsize(OUT) / 1048576))
