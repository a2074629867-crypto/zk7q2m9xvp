# -*- coding: utf-8 -*-
"""_adv_ab4.py —— F0 曲线改写实验 + 被拦下 take 的复听页。

两段：
  A. F0 驼峰（WORLD 声码器，只改 f0 不动谱包络）
     每条都放一个「纯声码器」对照 —— 它 f0 一点没改，用来暴露声码器本身的问题。
  B. 之前被 0.55 声纹线拦下的 take，跟原版并列，交给人耳判。
"""
import base64
import json
import os
import subprocess

ROOT = "G:/_setup"
FF = "E:/tool/oopz/ffmpeg.exe"
OUT = os.path.join(ROOT, "_adv_ab4")
TMP = os.path.join(OUT, "mp3")

A = [
    dict(uid="N0627", adv="carefully", loc="−0.74",
         text="Then, he bent down and lifted the thing up carefully.",
         takes=[("原版", "_mt_pick/N0627.wav", "loc −0.74"),
                ("纯声码器（f0 未改）", "_f0_bump/N0627_vocoder.wav", "loc +1.03 ← 对照"),
                ("驼峰 +2 半音", "_f0_bump/N0627_p2.wav", "loc +1.92"),
                ("驼峰 +3 半音", "_f0_bump/N0627_p3.wav", "loc +4.07"),
                ("驼峰 +4 半音", "_f0_bump/N0627_p4.wav", "loc +5.00"),
                ("驼峰 +6 半音", "_f0_bump/N0627_p6.wav", "loc +6.03")]),
    dict(uid="N0219", adv="nervously", loc="+0.90",
         text="They all stood about nervously, Kingshaw had red hair.",
         takes=[("原版", "_mt_pick/N0219.wav", "loc +0.90"),
                ("纯声码器（f0 未改）", "_f0_bump/N0219_voc_clean.wav", "loc +6.19 ← 对照"),
                ("驼峰 +3 半音", "_f0_bump/N0219_p3.wav", "loc +6.91"),
                ("驼峰 +4 半音", "_f0_bump/N0219_p4.wav", "loc +6.50")]),
]

B = [
    dict(uid="N0634", adv="gingerly", why="旧线判 0.339；同批实测同人不同句 p5 只有 −0.06",
         text="He held it gingerly, and rather away from his body.",
         takes=[("原版（已采纳 s2035）", "_mt_pick/N0634.wav", ""),
                ("曾被拦下 s2033", "_mt_adv_s2033/N0634.wav", "loc +6.57")]),
    dict(uid="N0219", adv="nervously", why="旧线判 0.292",
         text="They all stood about nervously, Kingshaw had red hair.",
         takes=[("原版", "_mt_pick/N0219.wav", "loc +0.90"),
                ("曾被拦下 s2033", "_mt_adv_s2033/N0219.wav", "loc +1.28"),
                ("曾被拦下 s2035", "_mt_adv_s2035/N0219.wav", "loc −2.67")]),
    dict(uid="N0627", adv="carefully", why="旧线判 0.373",
         text="Then, he bent down and lifted the thing up carefully.",
         takes=[("原版", "_mt_pick/N0627.wav", "loc −0.74"),
                ("曾被拦下 s2033", "_mt_adv_s2033/N0627.wav", "loc +0.23"),
                ("曾被拦下 s2035", "_mt_adv_s2035/N0627.wav", "loc +1.87")]),
]


def mp3(src):
    os.makedirs(TMP, exist_ok=True)
    p = os.path.join(TMP, os.path.basename(os.path.dirname(src)) + "_" +
                     os.path.basename(src)[:-4] + ".mp3")
    if not (os.path.exists(p) and os.path.getsize(p) > 1000):
        subprocess.run([FF, "-y", "-v", "error", "-i", os.path.join(ROOT, src),
                        "-ac", "1", "-ar", "44100", "-b:a", "64k", p], capture_output=True)
    return p if os.path.exists(p) and os.path.getsize(p) > 1000 else None


def b64(p):
    return "data:audio/mpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()


def card(c, note_key):
    aud = []
    for i, (name, src, note) in enumerate(c["takes"]):
        p = mp3(src)
        if not p:
            aud.append('<div class="take">缺文件 %s</div>' % src)
            continue
        aud.append("""
      <div class="take%s">
        <div class="tk-h"><b>%s</b></div>
        <div class="tk-n">%s</div>
        <audio controls preload="none" src="%s"></audio>
      </div>""" % (" first" if i == 0 else "", name, note or "&nbsp;", b64(p)))
    return """
  <section class="card">
    <div class="hd"><span class="uid">%s</span><span class="adv">%s</span>%s</div>
    <div class="txt">%s</div>
    <div class="takes">%s</div>
  </section>""" % (c["uid"], c["adv"],
                   ('<span class="why">%s</span>' % c["why"]) if c.get("why") else "",
                   c["text"].replace("<", "&lt;"), "".join(aud))


html = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>F0 曲线改写 + 声纹复查</title>
<style>
:root{--bg:#f6f7f9;--fg:#1b1f24;--mut:#5f6b7a;--line:#e2e6ec;--card:#fff;
--ok:#197a4b;--warn:#9a6b00;--bad:#b03030;}
@media(prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e8ecf2;--mut:#93a0b0;
--line:#2a313a;--card:#1b1f26;--ok:#4cc38a;--warn:#e0a83a;--bad:#ef6b6b;}}
*{box-sizing:border-box}
body{margin:0;padding:28px 18px 60px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,"Segoe UI",system-ui,"Microsoft YaHei",sans-serif}
.wrap{max-width:1120px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}
h2{font-size:15px;margin:30px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.lead{color:var(--mut);font-size:13.5px;margin:0 0 6px}
.lead code{background:rgba(127,127,127,.14);padding:1px 5px;border-radius:4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 16px;margin:0 0 14px}
.hd{display:flex;gap:10px;align-items:center;margin-bottom:6px;flex-wrap:wrap}
.uid{font:600 12.5px/1 ui-monospace,Consolas,monospace;color:var(--mut);letter-spacing:.04em}
.adv{font-weight:700;font-size:15px}
.why{font-size:11.5px;color:var(--bad);border:1px solid currentColor;border-radius:99px;
padding:1px 8px}
.txt{color:var(--mut);font-size:13px;margin-bottom:10px;word-break:break-word}
.takes{display:flex;gap:10px;overflow-x:auto;padding-bottom:2px}
.take{flex:0 0 232px;border:1px solid var(--line);border-radius:9px;padding:9px 11px}
.take.first{background:rgba(127,127,127,.05)}
.tk-h{margin-bottom:3px;font-size:13.5px}
.tk-n{font:11.5px/1.4 ui-monospace,Consolas,monospace;color:var(--mut);
margin-bottom:6px;min-height:16px}
audio{width:100%;height:32px}
</style></head><body><div class="wrap">
<h1>F0 曲线改写 + 声纹复查</h1>
<p class="lead">A 段：用 WORLD 只改基频轨迹（谱包络原样送回）给副词加一个升余弦驼峰。
<b>每一组第二个都是「纯声码器」对照</b>——它 f0 完全没改，如果它听起来已经不对，那这条路就不能用。</p>
<p class="lead">B 段：之前被 0.55 声纹线拦下的 take。重新标定后这条线不成立，交给你听。</p>

<h2>A · F0 驼峰</h2>
@A@

<h2>B · 声纹存疑 take 复听</h2>
@B@
</div></body></html>"""

html = html.replace("@A@", "".join(card(c, "a") for c in A))
html = html.replace("@B@", "".join(card(c, "b") for c in B))

os.makedirs(OUT, exist_ok=True)
p = os.path.join(OUT, "F0驼峰与声纹复查.html")
open(p, "w", encoding="utf-8").write(html)
n = sum(len(c["takes"]) for c in A + B)
print("卡片 %d，音频 %d 条 → %s（%.1f KB）"
      % (len(A + B), n, p, os.path.getsize(p) / 1024.0))
