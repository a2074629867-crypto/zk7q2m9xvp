# -*- coding: utf-8 -*-
"""速度 A/B 对照页：同句「旧 0.80 降速版」vs「新标准版」。

只列 `_regen_1123/` 里已经出好的句子，随时可重跑增量更新。
页面引用相对路径，必须在 G:/_setup 起 http 服务才能播：
    python -m http.server 8811 --directory G:/_setup
"""
import glob
import io
import json
import os
import wave

ROOT = r"G:/_setup"
NEW = os.path.join(ROOT, "_regen_1123")
OLD = os.path.join(ROOT, "_audio_ch123", "out")
PLAN2 = os.path.join(ROOT, "_castle_en_ch123_plan_v2.jsonl")
PLAN1 = os.path.join(ROOT, "_castle_en_ch123_plan.jsonl")
DST = os.path.join(ROOT, "_speed_ab.html")


def dur(p):
    try:
        w = wave.open(p)
        return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


def load(p):
    d = {}
    for l in io.open(p, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            d[r["id"]] = r
    return d


def main():
    p2, p1 = load(PLAN2), load(PLAN1)
    ids = sorted(os.path.basename(x)[:-4] for x in glob.glob(NEW + "/*.wav")
                 if not os.path.basename(x).startswith("_raw_"))
    rows = []
    for sid in ids:
        po = os.path.join(OLD, sid + ".wav")
        pn = os.path.join(NEW, sid + ".wav")
        if not os.path.exists(po):
            continue
        do, dn = dur(po), dur(pn)
        if not do or not dn:
            continue
        r2 = float((p2.get(sid) or {}).get("rate") or 1.0)
        r1 = float((p1.get(sid) or {}).get("rate") or 0.8)
        txt = (p2.get(sid) or {}).get("text") or ""
        nw = len(txt.split())
        rows.append(dict(id=sid, txt=txt, do=do, dn=dn, r1=r1, r2=r2,
                         wo=60 * nw / do, wn=60 * nw / dn, nw=nw))

    tr = "".join(
        """<tr>
  <td class="id">{id}<div class="sub">{nw} 词 · 旧 rate {r1:.2f} → 新 rate {r2:.2f}</div></td>
  <td class="txt">{txt}</td>
  <td class="num">旧 {do:.2f}s<br><b>{wo:.0f} wpm</b></td>
  <td class="num">新 {dn:.2f}s<br><b>{wn:.0f} wpm</b></td>
  <td class="num">{ratio:+.0%}</td>
  <td class="au"><div class="lab">A 旧</div><audio controls preload="none" src="_audio_ch123/out/{id}.wav"></audio>
      <div class="lab">B 新</div><audio controls preload="none" src="_regen_1123/{id}.wav"></audio></td>
</tr>""".format(ratio=(dn / do - 1), **r) for r in rows)

    n = len(rows)
    avg_o = sum(r["wo"] for r in rows) / n if n else 0
    avg_n = sum(r["wn"] for r in rows) / n if n else 0

    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>速度 A/B — 旧降速 vs 新标准</title>
<style>
:root{--bg:#faf9f7;--fg:#1b1a18;--mut:#6d6a64;--line:#e3e0da;--card:#fff;--acc:#8a5a2b}
@media(prefers-color-scheme:dark){:root{--bg:#161514;--fg:#ece9e4;--mut:#9b968d;--line:#2e2c29;--card:#1e1d1b;--acc:#d9a06a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"Segoe UI","Noto Sans SC",sans-serif}
header{padding:26px 28px 14px;border-bottom:1px solid var(--line)}
h1{margin:0 0 6px;font-size:20px;letter-spacing:.2px}
.meta{color:var(--mut);font-size:13px}
.stat{display:flex;gap:22px;flex-wrap:wrap;margin-top:14px}
.stat div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px}
.stat b{display:block;font-size:19px;color:var(--acc)}
.stat span{font-size:12px;color:var(--mut)}
table{border-collapse:collapse;width:100%}
th{position:sticky;top:0;background:var(--bg);text-align:left;font-size:12px;color:var(--mut);
   font-weight:600;padding:10px 12px;border-bottom:1px solid var(--line);z-index:2}
td{padding:12px;border-bottom:1px solid var(--line);vertical-align:top}
tr:hover td{background:var(--card)}
.id{font:600 13px ui-monospace,monospace;white-space:nowrap}
.sub{font:400 11px ui-monospace,monospace;color:var(--mut);margin-top:3px}
.txt{max-width:430px;font-size:14px}
.num{font:12px ui-monospace,monospace;color:var(--mut);white-space:nowrap}
.num b{color:var(--fg);font-size:13px}
.au{min-width:250px}
.lab{font-size:11px;color:var(--mut);margin:2px 0 1px}
audio{width:250px;height:32px;display:block}
footer{padding:20px 28px 40px;color:var(--mut);font-size:12.5px;line-height:1.7}
code{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:12px}
</style></head><body>
<header>
<h1>速度 A/B 对照 — 旧降速版 vs 新标准版</h1>
<div class="meta">同句同 seed，只差 rate：旧库整条按 0.80 拉慢，新库按标注 1.00 / 0.84 出。</div>
<div class="stat">
  <div><b>__N__</b><span>已重生成句数</span></div>
  <div><b>__AO__ → __AN__</b><span>平均 wpm（旧 → 新）</span></div>
  <div><b>__DPP__</b><span>平均提速</span></div>
</div>
</header>
<table>
<thead><tr><th>句子</th><th>文本</th><th>旧</th><th>新</th><th>时长差</th><th>试听</th></tr></thead>
<tbody>__TR__</tbody></table>
<footer>
rate 只是 ffmpeg rubberband 的 tempo 系数，与「基线」无关；0.84 是慢读档的上限（0.70 是断崖，不用）。<br>
播放需在 <code>G:/_setup</code> 起服务：<code>python -m http.server 8811 --directory G:/_setup</code>，然后开 <code>localhost:8811/_speed_ab.html</code>。<br>
本页只列 <code>_regen_1123/</code> 里已完成的句子；全量 716 条仍在跑，重跑本脚本即可增量刷新。
</footer></body></html>"""
    html = (html.replace("__TR__", tr).replace("__N__", str(n))
                .replace("__AO__", "%.0f" % avg_o).replace("__AN__", "%.0f" % avg_n)
                .replace("__DPP__", "%+.0f%%" % (100 * (avg_n / avg_o - 1) if avg_o else 0)))

    io.open(DST, "w", encoding="utf-8").write(html)
    print("写出 %s  %d 行  %.1fKB" % (DST, n, os.path.getsize(DST) / 1024.0))
    print("平均 wpm 旧 %.1f → 新 %.1f" % (avg_o, avg_n))


if __name__ == "__main__":
    main()
