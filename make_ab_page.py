# -*- coding: utf-8 -*-
"""make_ab_page.py —— 对白交付 A/B 对照页（REQUIREMENTS 29）。

为什么要它：239 条里只有 88 条严格通过，其余是「缺档 / 短句 / 边缘」。
交付时如果只报一个 PASS 率，客户会以为 63% 是废品。这一页让人耳直接抽检，
并如实标出每条属于哪一类、为什么。

页面内容：
  - 按类别筛选（A 通过 / E 边缘 / C 缺档 / D 短句 / B 待重生成 / F 待人工）
  - 每条：id · 角色 · 情绪 · 值 · 判决 · 原因 · 文本 · 播放器
  - 顶部统计 + 数据源

用法：
  G:/Python310/python.exe make_ab_page.py --gate _gate_dlg_v12.json \
      --plan _dlg_plan_v2.jsonl --out _dlg_ab.html
"""
import argparse
import collections
import json
import os
import html as H

AUDIO_DIR = "G:/_setup/_audio_ch123/out"

CAT = {
    "A": ("通过", "ok"),
    "E": ("情绪边缘", "warn"),
    "G": ("音色不一致", "err"),
    "H": ("自然度不足", "err"),
    "C": ("缺档未验证", "bad"),
    "D": ("短句未验收", "dim"),
    "B": ("待重生成", "err"),
    "F": ("待人工", "dim"),
}
MEAS = {"too_short", "spk_short", "emo_short", "role_unmeasurable"}
EDGE = {"emo_low", "emo_marginal", "hard_cap", "bimodal"}


def classify(x):
    """★ 2026-11-13 01:59：原来是 `gate_report.classify` 的手抄副本（只认 A–F），
    报表修好 G/H 之后这里还是一份旧的 —— 同一套分层有两份实现必然走偏。
    改为直接复用报表的 classify，页面与报告永远同口径。
    """
    import sys as _sys
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in _sys.path:
        _sys.path.insert(0, _here)
    import gate_report as GR
    return GR.classify(x)


def words(t):
    t = (t or "").replace("\u2018", " ").replace("\u2019", "'")
    return len([k for k in t.split() if any(c.isalpha() for c in k)])


TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>对白交付对照 · {n} 条</title>
<style>
:root{{--bg:#0e1116;--panel:#161b22;--line:#232a33;--tx:#e6edf3;--tx2:#9aa4b2;
--ok:#3fb950;--warn:#d29922;--bad:#f85149;--dim:#6e7681;--brand:#58a6ff}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);font:13px/1.6 -apple-system,"Segoe UI",system-ui,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:22px 20px 60px}}
h1{{font-size:19px;margin:0 0 4px}}
.sub{{color:var(--tx2);font-size:12px;margin-bottom:16px}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}}
.stat{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 13px;font-size:12px}}
.stat b{{font-size:15px;margin-left:5px}}
.bar{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:5;border-bottom:1px solid var(--line)}}
.bar button{{background:var(--panel);border:1px solid var(--line);color:var(--tx2);padding:5px 12px;
border-radius:6px;cursor:pointer;font-size:12px}}
.bar button.on{{background:var(--brand);color:#04121f;border-color:var(--brand);font-weight:600}}
.row{{display:grid;grid-template-columns:78px 62px 1fr 190px;gap:12px;align-items:center;
background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:9px 12px;margin-bottom:7px}}
.row.ok{{border-left:3px solid var(--ok)}}
.row.warn{{border-left:3px solid var(--warn)}}
.row.bad{{border-left:3px solid var(--bad)}}
.row.err{{border-left:3px solid var(--bad);background:#1d1214}}
.row.dim{{border-left:3px solid var(--dim);opacity:.82}}
.id{{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--tx2)}}
.who{{font-size:12px;color:var(--tx)}}
.mid{{min-width:0}}
.txt{{font-size:12.2px;color:var(--tx);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.meta{{font-size:11px;color:var(--tx2);margin-top:2px}}
.tag{{display:inline-block;font-size:10.5px;padding:1px 6px;border-radius:4px;margin-right:5px;
border:1px solid currentColor}}
audio{{width:100%;height:30px}}
.hide{{display:none}}
.note{{color:var(--dim);font-size:11.5px;margin-top:18px;line-height:1.8}}
</style></head><body><div class="wrap">
<h1>对白交付对照 · {n} 条</h1>
<div class="sub">数据源 <code>{src}</code> · 生成于 {ts} · 音频目录 <code>{adir}</code></div>
<div class="stats">{stats}</div>
<div class="bar">{bar}</div>
<div id="list">{rows}</div>
<div class="note">
分类口径（互斥）：<b>A 通过</b>=声学+声纹+情绪全过；<b>E 边缘</b>=情绪值在 p10~p25 或撞生成层数学顶，需人耳；
<b>C 缺档</b>=该角色音色库没有这个情绪档，用替代档生成，情绪未验证（素材问题，不是音频坏）；
<b>D 短句</b>=1–3 词，声纹/F0/情绪在这种时长上不成立，<b>不能判 PASS 也不算坏</b>；
<b>B 待重生成</b>=真缺陷；<b>F 待人工</b>=其余。
</div>
</div>
<script>
const btns=[...document.querySelectorAll('.bar button')];
btns.forEach(b=>b.onclick=()=>{{
  btns.forEach(x=>x.classList.remove('on')); b.classList.add('on');
  const k=b.dataset.c;
  document.querySelectorAll('.row').forEach(r=>{{
    r.classList.toggle('hide', k!=='ALL' && r.dataset.c!==k);
  }});
}});
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", default="_dlg_ab.html")
    a = ap.parse_args()

    rows = json.load(open(a.gate, encoding="utf-8"))
    plan = {}
    for l in open(a.plan, encoding="utf-8"):
        l = l.strip()
        if l:
            r = json.loads(l)
            plan[r["id"]] = r

    buckets = collections.defaultdict(list)
    for x in rows:
        buckets[classify(x)].append(x)

    ORDER = "ABGHCDEF"
    stats = []
    for k in ORDER:
        c = len(buckets[k])
        stats.append('<div class="stat">%s<b>%d</b></div>' % (CAT[k][0], c))

    bar = ['<button class="on" data-c="ALL">全部 %d</button>' % len(rows)]
    for k in ORDER:
        if buckets[k]:
            bar.append('<button data-c="%s">%s %d</button>' % (k, CAT[k][0], len(buckets[k])))

    body = []
    order = "ABGHECDF"
    for k in order:
        for x in sorted(buckets[k], key=lambda y: y["id"]):
            er = x.get("emo_res") or {}
            v = er.get("value")
            codes = sorted({r["code"] for r in x["reasons"]})
            why = "；".join(r["why"] for r in x["reasons"])[:110]
            wav = os.path.join(AUDIO_DIR, x["id"] + ".wav").replace("\\", "/")
            tags = "".join('<span class="tag">%s</span>' % c for c in codes[:3])
            body.append(
                '<div class="row {cls}" data-c="{k}">'
                '<div><div class="id">{id}</div></div>'
                '<div class="who">{who}</div>'
                '<div class="mid"><div class="txt">{txt}</div>'
                '<div class="meta">{tags}{emo}{val} · {why}</div></div>'
                '<div><audio controls preload="none" src="file:///{wav}"></audio></div>'
                "</div>".format(
                    cls=CAT[k][1], k=k, id=H.escape(x["id"]),
                    who=H.escape(x.get("who") or ""),
                    txt=H.escape((x.get("text") or "")[:96]),
                    tags=tags,
                    emo=H.escape(er.get("emo") or ""),
                    val=(" %.3f" % v) if isinstance(v, (int, float)) else "",
                    why=H.escape(why), wav=wav))

    import datetime
    out = TPL.format(
        n=len(rows), src=os.path.basename(a.gate),
        ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        adir=AUDIO_DIR, stats="".join(stats), bar="".join(bar),
        rows="\n".join(body))
    open(a.out, "w", encoding="utf-8").write(out)
    print("写出 %s（%d 条 / %.0f KB）" % (a.out, len(rows), len(out) / 1024))
    for k in "ABGHCDEF":
        print("  %s %-8s %3d" % (k, CAT[k][0], len(buckets[k])))


if __name__ == "__main__":
    main()
