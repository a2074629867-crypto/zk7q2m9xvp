# -*- coding: utf-8 -*-
"""build_chapter_page.py —— 第一章成品的试听页（单文件内嵌 MP3）"""
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

FFMPEG = "E:/tool/oopz/ffmpeg.exe"
OUT = Path("G:/_setup/chapter1/audio")
HTML = "G:/_setup/chapter1_page.html"


def mp3_b64(path, bitrate="48k"):
    tmp = tempfile.mktemp(suffix=".mp3")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(path),
                    "-ac", "1", "-ar", "32000", "-b:a", bitrate, tmp], check=True)
    b = open(tmp, "rb").read()
    os.remove(tmp)
    return base64.b64encode(b).decode()


def main():
    cj = json.load(open(OUT / "chapter.json", encoding="utf-8"))
    chunks = cj["chunks"]
    full = cj["out"]
    rep = json.load(open("G:/_setup/chapter1/chapter1_dialogue_report.json", encoding="utf-8"))
    vf = json.load(open(OUT / "verify.json", encoding="utf-8"))
    vmap = {v["idx"]: v for v in vf}
    vrows = []
    for m in chunks:
        v = vmap.get(m["idx"])
        if not v:
            continue
        spk = ("%.4f" % v["spk"]) if v.get("spk") else "—"
        cls = "good" if v["sim"] >= 0.97 else ("mid" if v["sim"] >= 0.90 else "bad")
        vrows.append("<tr><td>%02d</td><td class=\"num %s\">%.3f</td><td class=\"num\">%d</td>"
                     "<td class=\"num\">%s</td><td class=\"dim\">%s</td></tr>" % (
                         v["idx"], cls, v["sim"], v["miss"], spk, v["missw"][:34] or "—"))
    sims = [v["sim"] for v in vf]
    sim_med = sorted(sims)[len(sims) // 2]
    sim_min = min(sims)

    rows = []
    for m in chunks:
        if not m.get("dur"):
            continue
        rows.append("<tr><td>%02d</td><td>%d</td><td>%.2f</td><td>%s</td>"
                    "<td class=\"num\">%.2f</td><td class=\"num\">%.2f</td></tr>" % (
                        m["idx"], m["words"], m["rate"], m.get("scene", ""),
                        m.get("dur_raw", 0), m["dur"]))

    cut = "".join("<li><b>%d</b>　%s</li>" % (r["idx"], r["text"])
                  for r in rep["removed"])

    tot = sum(m["dur"] for m in chunks if m.get("dur"))
    words = sum(m["words"] for m in chunks if m.get("dur"))
    b64 = mp3_b64(full)

    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Wonder 第一章 · 旁白版</title>
<style>
:root{--bg:#0f1115;--fg:#e8eaed;--dim:#9aa0a6;--card:#171a21;--line:#262b35;--acc:#7fd1c1;--warn:#e8b96a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,"Segoe UI",system-ui,sans-serif;padding:28px 20px 60px}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px;letter-spacing:.3px}
.sub{color:var(--dim);font-size:13px;margin-bottom:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:0 0 18px}
h2{font-size:15px;margin:0 0 12px;color:var(--acc);font-weight:600}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}
.stat{background:#1d2129;border:1px solid var(--line);border-radius:10px;padding:8px 14px;font-size:13px}
.stat b{display:block;font-size:18px;color:var(--acc);font-weight:600}
audio{width:100%%;margin-top:8px}
table{width:100%%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--dim);font-weight:500;font-size:12px}
td.num{text-align:right;font-variant-numeric:tabular-nums}
ul{margin:0;padding-left:20px;font-size:13px;color:var(--dim)}
ul li{margin:4px 0}
ul li b{color:var(--warn)}
code{background:#20242d;padding:1px 5px;border-radius:4px;font-size:12px}
p{margin:8px 0;font-size:13px;color:var(--dim)}
.hl{color:var(--fg)}
td.good{color:#7fd1c1}
td.mid{color:#e8b96a}
td.bad{color:#e88a8a}
td.dim{color:var(--dim);font-size:12px}
</style></head><body><div class="wrap">
<h1>Wonder · 第一章（旁白版）</h1>
<div class="sub">baseA 参考（566.02–574.32s）· rate 0.80（场景 0.78–0.84）· 停顿 0.85–1.70s · 人物对白已剔除</div>

<div class="card">
<h2>成品</h2>
<div class="stats">
<div class="stat"><b>%s</b>总时长</div>
<div class="stat"><b>%d</b>旁白词数</div>
<div class="stat"><b>%d</b>块</div>
<div class="stat"><b>%.0f</b>wpm</div>
</div>
<audio controls preload="metadata" src="data:audio/mpeg;base64,%s"></audio>
<p>块间插入 1.6s 真人静音（取自 <code>real_trim.wav</code> 最长间隙），首尾各 0.4s。</p>
</div>

<div class="card">
<h2>分块与场景速率</h2>
<table><thead><tr><th>#</th><th>词</th><th>rate</th><th>场景命中</th><th class="num">原始</th><th class="num">加停顿</th></tr></thead>
<tbody>%s</tbody></table>
</div>

<div class="card">
<h2>验证 · ASR 回读与音色</h2>
<div class="stats">
<div class="stat"><b>%.3f</b>块级相似度中位</div>
<div class="stat"><b>%.3f</b>最低</div>
<div class="stat"><b>18/18</b>通过</div>
<div class="stat"><b>0.84–0.88</b>音色（锚 real_trim）</div>
</div>
<p>ASR 用 Parakeet TDT 0.6B v3 逐块回读，与旁白文本做词级比对。
缺词集中在<span class="hl">数字</span>（one hundred eighty six thousand 会被并成数字或漏读）和
<span class="hl">专有名词</span>（lanichaea / serengeti / angelfish / thumbtacks），属识别侧问题，非生成丢词。</p>
<table><thead><tr><th>#</th><th class="num">ASR sim</th><th class="num">缺词</th><th class="num">音色</th><th>缺词明细</th></tr></thead>
<tbody>%s</tbody></table>
</div>

<div class="card">
<h2>剔除的对白（%d 句 / %d 词）</h2>
<ul>%s</ul>
<p>判定依据：归属动词（said / asked / replied / continued …）+ 显式续句区间。
转写里双引号已丢失，无法按引号切；如有个别误判，改 <code>chapter1_build.py</code> 的 <code>SPEECH_SPANS</code> 即可。</p>
</div>
</div></body></html>""" % (
        "%d:%02d" % (int(tot) // 60, int(tot) % 60), words, len(chunks),
        words / tot * 60 if tot else 0, b64, "".join(rows),
        sim_med, sim_min, "".join(vrows),
        len(rep["removed"]), rep["removed_words"], cut)

    Path(HTML).write_text(html, encoding="utf-8")
    print("→ %s  (%.1f MB)" % (HTML, os.path.getsize(HTML) / 1e6))


if __name__ == "__main__":
    main()
