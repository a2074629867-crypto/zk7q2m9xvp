# -*- coding: utf-8 -*-
"""build_collapse_page.py —— 离线单文件对比试听页（内嵌 base64 MP3）

对比同一段分布外文本（38 词）在各权重下的输出：
    base 22.28s | mini_e10 17.68s ✓ | mini_e20 3.32s ✗ | mini_e30 2.00s ✗
    fix_e1 10.08s | fix_e11 2.52s ✗
外加「训练集内句子」验证背诵能力。
"""
import base64
import json
import os
import subprocess
from pathlib import Path

SRC = Path(r"E:/tts-models/acpp/out/v5mini")
OUT = Path(r"G:/_setup/gsv5_collapse_listen.html")
FF = r"E:/tool/oopz/ffmpeg.exe"

TARGET = [
    ("base", "base_target.wav", 22.28, "底模 s1v3（未微调）", "ok"),
    ("mini e10", "mini_e10_target.wav", 17.68, "24片最干净数据 · top3≈0.85", "best"),
    ("mini e20", "mini_e20_target.wav", 3.32, "top3≈0.99 —— 过拟合塌缩", "bad"),
    ("mini e30", "mini_e30_target.wav", 2.00, "top3≈1.00 —— 彻底塌缩", "bad"),
    ("fix e1", "fix_e1_target.wav", 10.08, "旧数据+掩码修复 · top3≈0.42", "mid"),
    ("fix e11", "fix_e11_target.wav", 2.52, "旧数据+掩码修复 · top3≈0.68", "bad"),
]
SEEN = [
    ("base", "base_seen.wav", 3.00, "底模", "ok"),
    ("mini e10", "mini_e10_seen.wav", 2.36, "训练集内句子 ✓", "best"),
    ("mini e20", "mini_e20_seen.wav", 2.40, "训练集内句子 ✓（但分布外崩）", "mid"),
    ("mini e30", "mini_e30_seen.wav", 0.68, "已崩", "bad"),
]


def mp3_b64(p: Path) -> str:
    tmp = OUT.parent / ("_tmp_" + p.stem + ".mp3")
    subprocess.run([FF, "-y", "-i", str(p), "-codec:a", "libmp3lame",
                    "-b:a", "128k", "-ar", "32000", str(tmp)],
                   check=True, capture_output=True)
    b = base64.b64encode(tmp.read_bytes()).decode()
    tmp.unlink(missing_ok=True)
    return b


def rows(items):
    out = []
    for name, fn, dur, note, cls in items:
        p = SRC / fn
        if not p.exists():
            continue
        b = mp3_b64(p)
        out.append(dict(name=name, dur=dur, note=note, cls=cls, b64=b))
    return out


data = {"target": rows(TARGET), "seen": rows(SEEN)}

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPT 微调塌缩 · 对比试听</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1a1d21;--mut:#5b6472;--line:#e3e6ea;--ok:#0a7d43;--bad:#c0392b;--warn:#b7791f}
html.dark{--bg:#14171a;--card:#1c2024;--fg:#e8eaed;--mut:#9aa4b2;--line:#2c3238;--ok:#4ecb8a;--bad:#ff7b6b;--warn:#e3b341}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:920px;margin:0 auto;padding:32px 20px 70px}
h1{font-size:23px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px;margin-bottom:24px}
h2{font-size:18px;margin:32px 0 6px}
.hint{color:var(--mut);font-size:13px;margin-bottom:12px}
.row{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:13px 16px;margin:9px 0;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.row.best{border-left:4px solid var(--ok)}
.row.bad{border-left:4px solid var(--bad)}
.row.mid{border-left:4px solid var(--warn)}
.row.ok{border-left:4px solid var(--mut)}
.nm{font-weight:600;min-width:92px}
.dur{font-variant-numeric:tabular-nums;font-size:17px;font-weight:700;min-width:74px}
.dur.bad{color:var(--bad)} .dur.best{color:var(--ok)}
.note{color:var(--mut);font-size:12.5px;flex:1;min-width:180px}
audio{height:36px}
.tag{font-size:11.5px;padding:2px 9px;border-radius:20px;border:1px solid var(--line);color:var(--mut)}
.toggle{position:fixed;top:14px;right:16px;background:var(--card);border:1px solid var(--line);color:var(--fg);border-radius:8px;padding:6px 12px;cursor:pointer;font-size:13px}
</style></head><body>
<button class="toggle" onclick="document.documentElement.classList.toggle('dark')">◐ 主题</button>
<div class="wrap">
<h1>GPT 微调塌缩 · 对比试听</h1>
<div class="sub">Matthew McConaughey / Calm《Wonder》 · v5turbo · vits 部分统一用 gsv-v5-pretrained/s2Gv5turbo.pth</div>

<h2>① 分布外文本（38 词，底模约 22.3s）</h2>
<div class="hint">"and heating into vapor. It is swirling in lakes, swelling in oceans…"　—— 绿边框 = 唯一可用的微调结果</div>
<div id="A"></div>

<h2>② 训练集内句子（"she wrapped herself in a fuzzy blanket," 底模约 3.0s）</h2>
<div class="hint">用来区分「过拟合」和「彻底崩」：能背出来但分布外崩 = 过拟合</div>
<div id="B"></div>

<div class="sub" style="margin-top:34px">
结论：<b>top_3_acc 越高 ≠ 越能用</b>。mini 训练集上 acc 冲到 0.996 的 e17/e30 完全塌缩，
而 acc≈0.85 的 e10 是唯一两栏都正常的权重。→ 必须逐 epoch 留存并试听取最佳点。
</div>
</div>
<script>
const D = __DATA__;
function render(el, list){
  el.innerHTML = list.map(r => `
   <div class="row ${r.cls}">
     <div class="nm">${r.name}</div>
     <div class="dur ${r.cls==='bad'?'bad':(r.cls==='best'?'best':'')}">${r.dur.toFixed(2)}s</div>
     <audio controls preload="none" src="data:audio/mpeg;base64,${r.b64}"></audio>
     <div class="note">${r.note}</div>
   </div>`).join('');
}
render(document.getElementById('A'), D.target);
render(document.getElementById('B'), D.seen);
</script>
</body></html>"""

html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False))
OUT.write_text(html, encoding="utf-8")
print("✅ 写出 %s  (%.2f MB)" % (OUT, OUT.stat().st_size / 1024 / 1024))
