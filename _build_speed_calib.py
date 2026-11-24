# -*- coding: utf-8 -*-
"""语速校准对照页：同一句三列并排 —— 旧 0.80 / 新 1.00 / 归一后。

挑三类句子，覆盖你听到的三种情况：
  A 类 最快的那批（新 1.00 明显赶）      —— 看归一有没有救回来
  B 类 中位附近（本来就正常）            —— 看归一有没有把它们弄慢
  C 类 0.84 慢读档                       —— 看慢读对比度有没有保住

用法：G:/Python310/python.exe -u _build_speed_calib.py
"""
import io
import json
import os
import sys

ROOT = r"G:/_setup"
sys.path.insert(0, ROOT)
import _speedlib  # noqa: E402

OLD = os.path.join(ROOT, "_audio_ch123", "out")
MID = os.path.join(ROOT, "_regen_1123_paused")            # 归一前（1.00 原速）
NEW = os.path.join(ROOT, "_regen_final")                  # 归一后（最终交付）
AUDIT = os.path.join(ROOT, "_speed_audit_final.json")   # 归一后（用于展示）
AUDIT_SEL = os.path.join(ROOT, "_speed_audit.json")     # 归一前（用于挑「A 类最快」）
DST = os.path.join(ROOT, "_speed_calib.html")

TARGET = 175.0


def load(p=None):
    return json.load(io.open(p or AUDIT, encoding="utf-8"))


def pick(rows, n_fast=8, n_mid=5, n_slow=4):
    ok = [r for r in rows if r.get("new") and r["new"]["wpm"] and r["words"] >= 4]
    fast = sorted([r for r in ok if r["new"]["wpm"] > 240],
                  key=lambda r: -r["new"]["wpm"])[:n_fast]
    mid = sorted([r for r in ok if 190 <= r["new"]["wpm"] <= 210
                  and r["rate"] >= 0.98], key=lambda r: abs(r["new"]["wpm"] - 198))[:n_mid]
    slow = sorted([r for r in ok if r["rate"] < 0.98],
                  key=lambda r: r["new"]["wpm"])[:n_slow]
    out, seen = [], set()
    for tag, group in (("A", fast), ("B", mid), ("C", slow)):
        for r in group:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            out.append((tag, r))
    return out


def main():
    rows = load(AUDIT_SEL)     # 按归一前的语速挑句子，否则 A 类永远挑不到
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in io.open(os.path.join(ROOT, "_narr_plan_for_pause.jsonl"),
                             encoding="utf-8") if l.strip()}
    items = pick(rows)
    tr = []
    stat = []
    for tag, r in items:
        sid = r["id"]
        text = (plan.get(sid) or {}).get("text") or ""
        pn = os.path.join(NEW, sid + ".wav")
        if not os.path.exists(pn):
            continue
        w_old = _speedlib.wpm_in(os.path.join(OLD, sid + ".wav"), r["words"]) if \
            os.path.exists(os.path.join(OLD, sid + ".wav")) else None
        w_mid = _speedlib.wpm_in(os.path.join(MID, sid + ".wav"), r["words"]) if \
            os.path.exists(os.path.join(MID, sid + ".wav")) else None
        w_new = _speedlib.wpm_in(pn, r["words"])
        stat.append((w_old, w_mid, w_new))
        tr.append(
            '<tr><td class="id">%s<div class="sub">%s 类 · %d 词 · rate %.2f</div></td>'
            '<td class="txt">%s</td>'
            '<td class="au"><div class="lab">旧 0.80 · %s</div>'
            '<audio controls preload="none" src="_audio_ch123/out/%s.wav"></audio></td>'
            '<td class="au"><div class="lab">新 1.00 · %s</div>'
            '<audio controls preload="none" src="_regen_1123_paused/%s.wav"></audio></td>'
            '<td class="au"><div class="lab">归一后 · %s</div>'
            '<audio controls preload="none" src="_regen_final/%s.wav"></audio></td>'
            '</tr>' % (
                sid, tag, r["words"], r["rate"],
                text.replace("<", "&lt;")[:150],
                ("%.0f wpm" % w_old) if w_old else "—", sid,
                ("%.0f wpm" % w_mid) if w_mid else "—", sid,
                ("%.0f wpm" % w_new) if w_new else "—", sid))

    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>语速校准对照 — 旧 0.80 / 新 1.00 / 归一后</title>
<style>
:root{--bg:#faf9f7;--fg:#1b1a18;--mut:#6d6a64;--line:#e3e0da;--card:#fff;--acc:#8a5a2b}
@media(prefers-color-scheme:dark){:root{--bg:#161514;--fg:#ece9e4;--mut:#9b968d;--line:#2e2c29;--card:#1e1d1b;--acc:#d9a06a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"Segoe UI","Noto Sans SC",sans-serif}
header{padding:24px 26px 14px;border-bottom:1px solid var(--line)}
h1{margin:0 0 6px;font-size:19px}
.meta{color:var(--mut);font-size:13px}
table{border-collapse:collapse;width:100%}
th{position:sticky;top:0;background:var(--bg);text-align:left;font-size:12px;color:var(--mut);
   font-weight:600;padding:10px 10px;border-bottom:1px solid var(--line);z-index:2}
td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:hover td{background:var(--card)}
.id{font:600 13px ui-monospace,monospace;white-space:nowrap}
.sub{font:400 11px ui-monospace,monospace;color:var(--mut);margin-top:3px}
.txt{max-width:330px;font-size:13.5px}
.au{min-width:180px}
.lab{font-size:11px;color:var(--mut);margin:0 0 2px}
audio{width:175px;height:30px;display:block}
footer{padding:18px 26px 40px;color:var(--mut);font-size:12.5px;line-height:1.75}
code{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:12px}
</style></head><body>
<header>
<h1>语速校准对照 — 旧 0.80 / 新 1.00 / 归一后</h1>
<div class="meta">A 类=新库最快的那批（归一前 240+ wpm）；B 类=中位附近；C 类=0.84 慢读档。
数字都是<b>句中语速</b>（词数 ÷ 去掉逗号句号停顿后的发声时长），目标 175 wpm（真人母带 p50）。</div>
</header>
<table>
<thead><tr><th>句子</th><th>文本</th><th>旧</th><th>新</th><th>归一后</th></tr></thead>
<tbody>__ROWS__</tbody></table>
<footer>
三列同句同文本，唯一变量是 tempo：旧库整体 0.80；新库 1.00（模型原速）；归一后按每句压缩到 175±10%。<br>
A 类如果听起来「归一后变拖了」，说明该句本来就不该压那么狠，告诉我我把压缩强度从 0.85 调到 0.7；<br>
C 类如果听不出慢读对比，说明 0.84 档需要重新定。<br>
播放需在 <code>G:/_setup</code> 起服务：<code>python -m http.server 8811</code>。
</footer></body></html>""".replace("__ROWS__", "".join(tr))

    io.open(DST, "w", encoding="utf-8").write(html)
    print("写入 %s（%d 行）" % (DST, len(tr)))
    for (tag, r), (a, b, c) in zip(items, stat):
        print("  %s %-9s %2d词 旧 %s / 新 %s / 归一 %s"
              % (tag, r["id"], r["words"],
                 ("%.0f" % a) if a else "—", ("%.0f" % b) if b else "—",
                 ("%.0f" % c) if c else "—"))


if __name__ == "__main__":
    main()
