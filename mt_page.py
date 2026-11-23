# -*- coding: utf-8 -*-
"""mt_page.py —— 生成旁白试听/核对页（单文件 HTML，引用相对路径的 wav）。

页面能力：
- 整章播放（_mt_out/chN.wav）
- 逐条表格：文本 / 选中 seed / 语速 / F0 / 声纹 / ASR 相似度 / 停顿
- 点行即播该条（共用 1 个 audio 元素，避免 800+ 个 audio 卡死浏览器）
- 「只看有问题」筛选、按章节切换

用法：python mt_page.py --out mt_review.html
"""
import argparse
import html
import json
import os

ROOT = "G:/_setup"
CHS = ["ch1", "ch2", "ch3", "ch4", "ch5"]


def load():
    p3 = os.path.join(ROOT, "mt_plan3b.json")
    if not os.path.exists(p3):
        p3 = os.path.join(ROOT, "mt_plan3.json")
    plan = {p["id"]: p for p in json.load(open(p3, encoding="utf-8"))}
    data = []
    for ch in CHS:
        f = os.path.join(ROOT, "_mt_score_%s.json" % ch)
        if not os.path.exists(f):
            continue
        rows = json.load(open(f, encoding="utf-8"))
        items = []
        for r in rows:
            sel = [c for c in r["cands"] if str(c["seed"]) == str(r["pick"])]
            c = sel[0] if sel else None
            p = plan.get(r["id"], {})
            items.append({
                "id": r["id"],
                "text": r["text"],
                "gap": p.get("gap", 0),
                "seed": r["pick"],
                "n": len(r["cands"]),
                "flag": r.get("flag", ""),
                "wpm": round(c["wpm"], 0) if c else None,
                "dur": round(c["dur"], 2) if c else None,
                "f0": round(c["f0"], 0) if c else None,
                "spk": round(c["spk"], 3) if c and c["spk"] == c["spk"] else None,
                "ratio": round(c["ratio"], 3) if c else None,
                "tail": bool(c["tail_ok"]) if c else None,
            })
        if items:
            data.append({"ch": ch, "items": items})
    return data


def row_html(it):
    bad = []
    if it["flag"]:
        bad.append(it["flag"])
    if it["ratio"] is not None and it["ratio"] < 0.9:
        bad.append("ASR低")
    if it["tail"] is False:
        bad.append("末词缺")
    if it["spk"] is not None and it["spk"] < 0.65:
        bad.append("声纹低")
    if it["f0"] and (it["f0"] < 65 or it["f0"] > 100):
        bad.append("F0出带")
    cls = "bad" if bad else ""
    return (
        '<tr class="%s" data-src="_mt_pick/%s.wav">'
        '<td class="id">%s</td>'
        '<td class="tx">%s</td>'
        '<td>%s</td><td>%.0f</td><td>%.2f</td><td>%s</td><td>%.1f</td><td>%.2f</td><td>%s</td>'
        '<td class="tag">%s</td></tr>'
        % (cls, it["id"], it["id"], html.escape(it["text"]),
           it["seed"], it["wpm"] or 0, it["dur"] or 0,
           ("%.2f" % it["spk"]) if it["spk"] is not None else "—",
           it["f0"] or 0, it["ratio"] if it["ratio"] is not None else 0,
           "✓" if it["tail"] else "✗",
           " · ".join(bad))
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="mt_review.html")
    a = ap.parse_args()
    data = load()
    if not data:
        print("没有可展示的数据（先跑 mt_score.py）")
        return

    total = sum(len(d["items"]) for d in data)
    nbad = sum(1 for d in data for it in d["items"]
               if it["flag"] or (it["ratio"] is not None and it["ratio"] < 0.9))
    tabs = "".join('<button class="tab%s" data-ch="%s">%s<span>%d</span></button>'
                   % (" on" if i == 0 else "", d["ch"], d["ch"], len(d["items"]))
                   for i, d in enumerate(data))
    outs = "".join(
        '<div class="player" data-ch="%s"%s><div class="pname">%s 整章</div>'
        '<audio controls preload="none" src="_mt_out/%s.wav"></audio></div>'
        % (d["ch"], "" if i == 0 else " hidden", d["ch"], d["ch"])
        for i, d in enumerate(data)
        if os.path.exists(os.path.join(ROOT, "_mt_out", d["ch"] + ".wav")))
    sections = "".join(
        '<section class="sec" data-ch="%s"%s><table><thead><tr>'
        '<th>ID</th><th>文本</th><th>seed</th><th>wpm</th><th>时长</th>'
        '<th>声纹</th><th>F0</th><th>ASR</th><th>末词</th><th>标记</th></tr></thead><tbody>%s'
        '</tbody></table></section>'
        % (d["ch"], "" if i == 0 else " hidden",
           "".join(row_html(it) for it in d["items"]))
        for i, d in enumerate(data))

    page = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>旁白核对 · 城堡之王</title>
<style>
:root{--bg:#0f1115;--pan:#171a21;--line:#252a34;--fg:#e6e9ef;--dim:#8b93a3;
--acc:#6ea8fe;--bad:#ff7b72;--ok:#4ac26b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:20px 26px 8px}
h1{margin:0 0 4px;font-size:19px;font-weight:600;letter-spacing:.3px}
.sub{color:var(--dim);font-size:12.5px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 4px}
.card{background:var(--pan);border:1px solid var(--line);border-radius:9px;
padding:9px 14px;min-width:104px}
.card b{display:block;font-size:18px;font-weight:600}
.card span{color:var(--dim);font-size:11.5px}
.tabs{display:flex;gap:6px;padding:12px 26px 0;flex-wrap:wrap}
.tab{background:var(--pan);color:var(--dim);border:1px solid var(--line);
border-radius:8px;padding:6px 13px;cursor:pointer;font-size:13px}
.tab.on{color:var(--fg);border-color:var(--acc);background:#1b2230}
.tab span{color:var(--dim);font-size:11px;margin-left:6px}
.bar{display:flex;gap:10px;align-items:center;padding:12px 26px 0}
label{color:var(--dim);font-size:12.5px;cursor:pointer;user-select:none}
.player{margin:14px 26px;background:var(--pan);border:1px solid var(--line);
border-radius:10px;padding:12px 16px}
.pname{color:var(--dim);font-size:12px;margin-bottom:8px;letter-spacing:.5px}
audio{width:100%;height:34px}
.sec{padding:8px 26px 60px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{position:sticky;top:0;background:var(--bg);text-align:left;color:var(--dim);
font-weight:500;padding:8px 7px;border-bottom:1px solid var(--line);font-size:12px;z-index:2}
td{padding:6px 7px;border-bottom:1px solid #1c2029;vertical-align:top}
tbody tr{cursor:pointer}
tbody tr:hover{background:#1b1f28}
tr.bad td{background:#2a1a1c}
tr.bad:hover td{background:#331f22}
.id{color:var(--dim);font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:nowrap}
.tx{max-width:640px}
.tag{color:var(--bad);font-size:12px;white-space:nowrap}
.foot{position:fixed;left:0;right:0;bottom:0;background:#12151b;
border-top:1px solid var(--line);padding:8px 16px;display:flex;gap:12px;
align-items:center;font-size:12.5px;color:var(--dim)}
.foot b{color:var(--fg);font-weight:500}
</style></head><body>
<header>
<h1>旁白核对 · 前三章</h1>
<div class="sub">点任意一行播放该条；红色 = 触发阈值。整章播放见上方播放器。</div>
<div class="stats">
<div class="card"><b>__TOTAL__</b><span>已生成单元</span></div>
<div class="card"><b>__NBAD__</b><span>触发阈值</span></div>
<div class="card"><b>0.80</b><span>统一 tempo</span></div>
<div class="card"><b>baseA</b><span>音色参考</span></div>
</div>
</header>
<div class="tabs">__TABS__</div>
<div class="bar"><label><input type="checkbox" id="onlybad"> 只看有问题的</label></div>
__PLAYERS__
__SECTIONS__
<div class="foot"><span>正在播放：<b id="now">—</b></span>
<audio id="p" controls style="flex:1;height:30px"></audio></div>
<script>
const P=document.getElementById('p'),N=document.getElementById('now');
document.querySelectorAll('tbody tr').forEach(tr=>tr.addEventListener('click',()=>{
  document.querySelectorAll('tbody tr.on').forEach(x=>x.classList.remove('on'));
  tr.classList.add('on');P.src=tr.dataset.src;P.play();
  N.textContent=tr.querySelector('.id').textContent;window.scrollTo({top:0,behavior:'smooth'});
}));
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));t.classList.add('on');
  const ch=t.dataset.ch;
  document.querySelectorAll('.sec').forEach(s=>s.hidden=s.dataset.ch!==ch);
  document.querySelectorAll('.player').forEach(s=>s.hidden=s.dataset.ch!==ch);
}));
document.getElementById('onlybad').addEventListener('change',e=>{
  document.querySelectorAll('tbody tr').forEach(tr=>{
    tr.style.display=(e.target.checked&&!tr.classList.contains('bad'))?'none':'';
  });
});
</script></body></html>"""
    page = (page.replace("__TOTAL__", str(total))
                .replace("__NBAD__", str(nbad))
                .replace("__TABS__", tabs)
                .replace("__PLAYERS__", outs)
                .replace("__SECTIONS__", sections))

    dst = os.path.join(ROOT, a.out)
    open(dst, "w", encoding="utf-8").write(page)
    print("写出 %s（%d 单元，%d 触发阈值）" % (dst, total, nbad))


if __name__ == "__main__":
    main()
