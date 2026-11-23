# -*- coding: utf-8 -*-
"""本轮修复 A/B 页：旧版 vs 新版，两侧都过同一套电平规范，避免"谁响谁好"。"""
import base64
import html
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import soundfile as sf

import ch123_rebuild as RB
import ch123_tone as T
import ch123_unify as U

FF = "E:/tool/oopz/ffmpeg.exe"
TMP = "G:/_setup/_mp3fix2"
OUT = "G:/_setup/castle_fix2.html"
os.makedirs(TMP, exist_ok=True)


def norm_copy(src, dst):
    a, sr = sf.read(src, dtype="float32", always_2d=True)
    y = U.proc(a.mean(1), sr)
    sf.write(dst, y, sr, subtype="PCM_16")
    return dst


def mp3_b64(p):
    m = os.path.join(TMP, os.path.basename(p).replace(".wav", "") + ".mp3")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                    "-codec:a", "libmp3lame", "-b:a", "96k", "-ar", "24000", "-ac", "1", m],
                   capture_output=True)
    with open(m, "rb") as f:
        return base64.b64encode(f.read()).decode()


def info(p, words):
    r = T.probe(p)
    f0s = [round(x["f0"]) for x in r["rows"]]
    dbs = [round(x["db"]) for x in r["rows"]]
    drops = [dbs[i] - dbs[i + 1] for i in range(len(dbs) - 1)]
    return dict(dur=r["dur"], wpm=words / r["dur"] * 60, f0=f0s, db=dbs,
                span=r["span"], tail=r["tail_drop"], md=max(drops) if drops else 0)


def badge(i):
    msgs = []
    if any(f > 300 or f < 175 for f in i["f0"]):
        msgs.append("音区出界")
    if i["md"] > 6:
        msgs.append("句间掉%d dB" % i["md"])
    if i["wpm"] > 215:
        msgs.append("语速赶")
    if not msgs:
        return '<span class="ok">稳</span>'
    return '<span class="bad">%s</span>' % " · ".join(msgs)


def card(title, tagline, old, new, words, note=""):
    blocks = []
    for label, p, cls in (("旧版", old, "old"), ("新版", new, "new")):
        if not p or not os.path.exists(p):
            continue
        q = norm_copy(p, os.path.join(TMP, os.path.basename(p)))
        i = info(q, words)
        blocks.append("""
        <div class="row %s">
          <div class="lab">%s</div>
          <div class="stats"><b>%.2fs</b><span>%.0f wpm</span><span>F0 %s</span><span>%s dB</span>%s</div>
          <audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio>
          <div class="flags">跨度 %.0fHz · 末句跌 %.0fHz%s</div>
        </div>""" % (cls, label, i["dur"], i["wpm"],
                     "/".join(map(str, i["f0"])), "/".join(map(str, i["db"])),
                     badge(i), mp3_b64(q), i["span"], i["tail"],
                     ("<div class='note'>" + html.escape(note) + "</div>") if (note and cls == "new") else ""))
    return """
    <section>
      <h3>%s</h3>
      <p class="tag">%s</p>
      %s
    </section>""" % (html.escape(title), html.escape(tagline), "".join(blocks))


SEC = [
    card("L050　Oh, what is it? What have you found?",
         "旧版挂 surprised：311Hz、整句顶起来，听起来是「被吓到」，不是「好奇」——所以反应怪。新版去 emo，196→238Hz 句尾自然上扬，这是疑问句该有的走向。",
         "G:/_setup/ch123_old/L050.wav", "G:/_setup/ch123/L050.wav", 9,
         "去 surprised → 整句生成，seed 45；ASR 全对，两段 196/238"),

    card("L017　There's nobody to play cricket with.",
         "旧版是 melancholic —— 这个标签会把音色调软调飘，所以听着「怪」。新版去 emo，197Hz 落回 Hooper 正常音区。",
         "G:/_setup/ch123_old/L017.wav", "G:/_setup/ch123/L017.wav", 7,
         "去 melancholic → 整句生成，seed 43"),

    card("L075　Oh, yes. Well, a bit. He was a pilot, once. He was in the Battle of Britain. I've got — I've got a picture of him.",
         "按你说的，口吃不能拆两条。合并成一句生成后，ASR 完整念出「I've got I've got a picture of him」，中间那道停顿是模型自己给的，不是拼出来的。原 L076 已并入本条。",
         "G:/_setup/ch123_old/L075.wav", "G:/_setup/ch123/L075.wav", 22,
         "合并 L075+L076 → 破折号写法，seed 42；7.36s，句间电平差 4.5dB"),

    card("L084　When did he die, I said.",
         "旧版挂的是 happy —— 这条标签会把整句顶起来喊，所以听着像吼。新版去 emo，整句一次生成，F0 落回 200Hz、句内电平只差 7dB。",
         "G:/_setup/ch123_old/L084.wav", "G:/_setup/ch123/L084.wav", 5,
         "去 happy → 整句生成，seed 47"),

    card("L079　I don't believe you. You're a liar. The Battle of Britain was in the war.",
         "旧版同样挂 disgusted：峰值顶到 0.98、voiced RMS −11dB，是砖墙压缩，所以前面炸。新版去 emo，三句 187/176/206Hz，句间电平差 −0.3dB。",
         "G:/_setup/ch123_old/L079.wav", "G:/_setup/ch123/L079.wav", 16,
         "去 disgusted → 整句生成，seed 48；声纹 0.801"),

    card("L005　All he looks like, is one of his dead old moths.",
         "旧版 disgusted 顶到 230Hz / −16dB，是「愤慨」不是「轻蔑」。新版回到 193Hz，声纹 0.696。",
         "G:/_setup/ch123_old/L005.wav", "G:/_setup/ch123/L005.wav", 11,
         "去 disgusted → 整句生成，seed 44"),

    card("L088　He's old, I told you. When he was in the Battle of Britain, he was twenty. That was the war.",
         "这次不再拆句。整句一次生成：227/236/197Hz、句间电平差 2.1dB、跨度 39Hz、ASR 全对。没有后处理降速，比上版 7.18s 更紧。",
         "G:/_setup/ch123_old/L088.wav", "G:/_setup/ch123/L088.wav", 22,
         "整句生成，seed 42，无后处理"),

    card("L078　No. But...",
         "生成端 11 种写法都只吐「No.」，改从 L070（Yes, he did. But it had to be sold.）剪出 But 拼上：No −21.2dB / But −21.4dB，中间 0.34s。",
         "G:/_setup/ch123_old/L078.wav", "G:/_setup/_fix79/L078_but.wav", 3,
         "从 L070 剪 But（2.222–2.478s）拼接"),
]

BODY = "\n".join(SEC)
HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Charles / Hooper · 本轮修复 A/B</title>
<style>
:root{--bg:#0f1115;--fg:#e8ecf1;--dim:#8b96a5;--card:#171b22;--line:#252b35;--ok:#4ade80;--bad:#f87171;--new:#5eead4}
*{box-sizing:border-box}
body{margin:0;padding:28px 20px 60px;background:var(--bg);color:var(--fg);
 font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:20px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:24px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:16px}
h3{font-size:15px;margin:0 0 4px;font-weight:600;line-height:1.5}
.tag{color:var(--dim);font-size:13px;margin:0 0 12px}
.row{border-left:3px solid var(--line);padding:8px 0 8px 12px;margin-bottom:10px}
.row.old{border-color:#3f4756}
.row.new{border-color:var(--new)}
.lab{font-size:12px;color:var(--dim);margin-bottom:4px}
.row.new .lab{color:var(--new)}
.stats{display:flex;flex-wrap:wrap;gap:10px;font-size:12.5px;margin-bottom:6px;font-variant-numeric:tabular-nums}
.stats span{color:var(--dim)}
.stats b{color:var(--fg)}
audio{width:100%;height:34px;margin:4px 0}
.flags{font-size:12px;color:var(--dim)}
.ok{color:var(--ok);border:1px solid #1d3f2a;background:#12251a;padding:0 6px;border-radius:4px;font-size:11.5px}
.bad{color:var(--bad);border:1px solid #4a2222;background:#251414;padding:0 6px;border-radius:4px;font-size:11.5px}
.note{margin-top:6px;font-size:12px;color:#7c8899}
</style></head><body>
<h1>Charles / Hooper · 本轮修复</h1>
<div class="sub">旧版 / 新版两侧都过同一套电平规范（voiced RMS −24dBFS + 限峰 −1dBFS），差别只在表演本身。</div>
__BODY__
</body></html>"""

HTML = HTML.replace("__BODY__", BODY)
open(OUT, "w", encoding="utf-8").write(HTML)
print("OK", OUT, round(os.path.getsize(OUT) / 1e6, 2), "MB")
