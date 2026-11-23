# -*- coding: utf-8 -*-
"""mt_contour_page.py —— 生成句内轮廓人工复核页（单文件，音频 base64 内嵌）

用法：
  G:/Python310/python.exe mt_contour_page.py --chs ch1,ch2,ch3 --top 30 --rand 10
"""
import argparse
import base64
import json
import os
import random
import shutil
import subprocess
import tempfile
from string import Template

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
FF = "E:/tool/oopz/ffmpeg.exe"
QUESTIONS = ["N0141", "N0153", "N0324", "N0491", "N0888", "N1137"]

CSS = """
*{box-sizing:border-box}
body{margin:0;padding:24px 28px 60px;font:13px/1.6 -apple-system,"Segoe UI",system-ui,sans-serif;
     background:#fafaf9;color:#1c1917}
h1{font-size:17px;font-weight:500;margin:0 0 4px}
.sub{color:#78716c;font-size:12px;margin-bottom:18px}
.cards{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.card{background:#fff;border:1px solid #e7e5e4;border-radius:10px;padding:10px 14px;min-width:110px}
.card b{display:block;font-size:19px;font-weight:500;line-height:1.2}
.card span{color:#78716c;font-size:11px}
h2{font-size:14px;font-weight:500;margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid #e7e5e4}
h2 small{font-weight:400;color:#78716c;font-size:12px;margin-left:8px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e7e5e4;border-radius:10px;overflow:hidden}
th{text-align:left;font-weight:500;font-size:11px;color:#78716c;padding:7px 9px;background:#f5f5f4;border-bottom:1px solid #e7e5e4}
td{padding:7px 9px;border-bottom:1px solid #f5f5f4;vertical-align:middle}
tr:last-child td{border-bottom:none}
tbody tr:hover{background:#f8fafc;cursor:pointer}
.mono{font:11px/1.4 ui-monospace,Consolas,monospace;white-space:nowrap}
.seed{color:#78716c}
.txt{max-width:330px;font-size:12px}
.num{font:11px ui-monospace,Consolas,monospace;text-align:right;white-space:nowrap}
.bad{color:#b91c1c;font-size:11px}
.ok{color:#a8a29e}
.pick{background:#dcfce7;color:#166534;font-size:10px;padding:1px 5px;border-radius:4px;margin-left:4px}
.alt{background:#f1f5f9;color:#475569;font-size:10px;padding:1px 5px;border-radius:4px;margin-left:4px}
.tag{background:#eef2ff;color:#3730a3;font-size:10px;padding:1px 6px;border-radius:4px;margin-left:6px}
.qbox{background:#fff;border:1px solid #e7e5e4;border-radius:10px;margin-bottom:12px;overflow:hidden}
.qhead{padding:9px 12px;background:#fafaf9;border-bottom:1px solid #e7e5e4;font-size:12px}
.qtxt{color:#57534e;margin-left:8px}
.qbox table{border:none;border-radius:0}
.playing{background:#eff6ff!important}
.note{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 12px;font-size:12px;color:#78350f;margin:14px 0}
.warn{background:#fef2f2;border:1px solid #fecaca;color:#7f1d1d}
audio{display:none}
.cell{display:flex;align-items:center;gap:7px}
.pl{width:23px;height:23px;flex:0 0 23px;border-radius:50%;border:1px solid #d6d3d1;background:#fff;
    color:#1c1917;font-size:9px;line-height:1;cursor:pointer;padding:0;font-family:inherit}
.pl:hover{background:#eff6ff;border-color:#93c5fd}
.pl.on{background:#2563eb;border-color:#2563eb;color:#fff}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 16px;
     position:sticky;top:0;z-index:9;background:#fafaf9;padding:9px 0;border-bottom:1px solid #e7e5e4}
.btn{background:#fff;border:1px solid #d6d3d1;border-radius:7px;padding:6px 13px;font-size:12px;
     cursor:pointer;color:#1c1917;font-family:inherit}
.btn:hover{background:#f5f5f4}
.btn.on{background:#2563eb;border-color:#2563eb;color:#fff}
.now{color:#78716c;font-size:12px;margin-left:4px}
"""

TPL = Template("""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>句内轮廓复核 · 马修旁白</title>
<style>$css</style></head><body>
<h1>句内 F0 / 能量轮廓复核</h1>
<div class="sub">点行首的 <b>&#9654;</b> 按钮播放（点整行也可以） · F0 蓝线 / 能量橙线（各 21 点，时间归一化） · ct 分高的排前面</div>
<div class="bar"><button class="btn" id="autobtn" onclick="autoPlay()">&#9654; 连续播放全部</button><button class="btn" onclick="jump(1)">下一句 &#8594;</button><button class="btn" onclick="stopAll()">&#9632; 停止</button><span class="now" id="now">共 <b>$nplay</b> 条可播</span></div>
<div class="cards">
<div class="card"><b>$n_unit</b><span>单元</span></div>
<div class="card"><b>$n_ok</b><span>可测候选</span></div>
<div class="card"><b>$n_un / $n_single</b><span>不可测 / 仅 1 候选</span></div>
<div class="card"><b>$eout</b><span>能量离群 pen&gt;0.5</span></div>
<div class="card"><b>${pen}</b><span>ct 分中位</span></div>
</div>
<div class="note">验证结论（V2 零假设检验）：能量场 AUC <b>0.921</b>（同文本候选对 vs 异文本对），有条件设阈值；
F0 场 AUC <b>0.660</b>，只用于相对排序、<b>不进分数</b>。V3 合成劣化响应：末段上扬 82% / 压平 100% / 插突跳 100%。</div>
$found
<h2>问句 / 感叹句<small>全库仅 5 问 1 叹，无法统计标定，逐个听</small></h2>
$qhtml
<h2>最可疑 $ntop 条<small>每单元取 ct 分最高的候选</small></h2>
<table>$head$toprows</table>
<h2>随机对照 $nrand 条<small>ct 分 &lt;0.10，用来算误报率</small></h2>
<table>$head$randrows</table>
<h2>完全不可测的 $nnull 条<small>浊音帧不足 0.4 秒，任何轮廓判据都不适用</small></h2>
<table><tr><th>单元</th><th>文本</th><th>原因</th></tr>$nullrows</table>
<script>
var cur=null, queue=[], qi=-1, auto=false;
function allRows(){return [].slice.call(document.querySelectorAll('tr[data-i]'));}
function reset(){ if(cur){cur.textContent='\\u25B6';cur.classList.remove('on');} cur=null;
  document.querySelectorAll('tr.playing').forEach(function(x){x.classList.remove('playing')}); }
function stopAll(){ document.querySelectorAll('audio').forEach(function(x){ if(!x.paused) x.pause(); });
  auto=false; syncAuto(); reset(); }
function syncAuto(){ var b=document.getElementById('autobtn');
  b.innerHTML = auto ? '&#9632; 停止连播' : '&#9654; 连续播放全部'; b.classList.toggle('on',auto); }
function say(s){ var n=document.getElementById('now'); if(n) n.innerHTML=s; }
function hit(e,btn){ e.stopPropagation(); toggle(btn); }
function play(tr){ var b=tr.querySelector('.pl'); if(b) toggle(b); }
function toggle(btn){
  var tr=btn.closest('tr'), a=tr.querySelector('audio');
  if(!a) return;
  if(!a.paused){ a.pause(); return; }
  var prev=cur; if(prev) { prev.textContent='\\u25B6'; prev.classList.remove('on'); }
  document.querySelectorAll('audio').forEach(function(x){ if(x!==a && !x.paused) x.pause(); });
  document.querySelectorAll('tr.playing').forEach(function(x){x.classList.remove('playing')});
  cur=btn; btn.textContent='\\u275A\\u275A'; btn.classList.add('on'); tr.classList.add('playing');
  try{ a.currentTime=0; }catch(e){}
  if(a.readyState===0){ try{ a.load(); }catch(e){} }
  var pr=a.play();
  if(pr && pr.catch) pr.catch(function(){ retry(btn, a); });
  a.onended=function(){ var b=cur; if(b){ b.textContent='\\u25B6'; b.classList.remove('on'); } cur=null;
    document.querySelectorAll('tr.playing').forEach(function(x){x.classList.remove('playing')});
    if(auto) step(1); };
  var rows=allRows(), idx=rows.indexOf(tr);
  // ★ qi 必须在这里更新：onended 里会先把 cur 置空，step() 只能靠 qi 知道播到哪了。
  //   漏掉这行会让"播完自动跳下一条"永远重播第 1 条。
  if(idx>=0){ qi=idx; say('正在播放 <b>'+(idx+1)+'</b> / '+rows.length); }
}
function retry(btn, a){
  var alt=a.getAttribute('data-alt');
  if(alt && !a.getAttribute('data-tried')){
    a.setAttribute('data-tried','1'); a.src=alt; try{ a.load(); }catch(e){}
    var p2=a.play();
    if(p2 && p2.catch){ p2.catch(function(){ fail(btn); }); }
    return;
  }
  fail(btn);
}
function fail(btn){
  btn.textContent='\\u25B6'; btn.classList.remove('on'); cur=null; auto=false; syncAuto();
  say('<span style="color:#b91c1c">播放被拦截 —— 请直接双击打开 _mt_contour_review.html 再试</span>');
}
function step(d){
  var rows=allRows(); if(!rows.length) return;
  var i=cur ? rows.indexOf(cur.closest('tr')) : qi;
  var j=i+d;
  if(j<0) j=0;
  if(j>=rows.length){ auto=false; syncAuto(); say('全部播放完毕'); reset(); return; }
  qi=j; var b=rows[j].querySelector('.pl'); if(b) toggle(b); else step(d);
}
function jump(d){ auto=false; syncAuto(); if(!cur){ qi=-1; } step(d); }
function autoPlay(){
  if(auto){ auto=false; stopAll(); return; }
  var rows=allRows(); if(!rows.length) return;
  auto=true; syncAuto(); qi=-1; reset();
  var b=rows[0].querySelector('.pl'); if(b) toggle(b);
}
</script></body></html>""")


def mp3_b64(path, dst=None):
    """转 96k mp3；给了 dst 就同时落盘（供 data: 被 CSP 拦截时用相对路径兜底）。"""
    try:
        fd, out = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", path,
                        "-codec:a", "libmp3lame", "-b:a", "96k", out], check=True)
        if dst:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(out, dst)
        d = base64.b64encode(open(out, "rb").read()).decode()
        os.remove(out)
        return d
    except Exception:
        return ""


def spark(vals, w=140, h=34, color="#2563eb"):
    v = np.asarray(vals, dtype=float)
    if len(v) < 2 or not np.all(np.isfinite(v)):
        return '<svg width="%d" height="%d"></svg>' % (w, h)
    lo, hi = float(v.min()), float(v.max())
    rng = max(hi - lo, 1e-6)
    pts = [(i / (len(v) - 1) * w, h - (x - lo) / rng * (h - 6) - 3) for i, x in enumerate(v)]
    poly = " ".join("%.1f,%.1f" % p for p in pts)
    base = "%.1f,%.1f %.1f,%.1f" % (0, h - 1, w, h - 1)
    return ('<svg width="%d" height="%d" viewBox="0 0 %d %d">'
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.3"/>'
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="0.4" opacity="0.25"/></svg>'
            % (w, h, w, h, poly, color, base, color))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chs", default="ch1,ch2,ch3")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--rand", type=int, default=10)
    ap.add_argument("--out", default=os.path.join(ROOT, "_mt_contour_review.html"))
    a = ap.parse_args()

    U, score = {}, {}
    for ch in [c.strip() for c in a.chs.split(",") if c.strip()]:
        fp = os.path.join(ROOT, "_mt_contour_%s.json" % ch)
        if os.path.exists(fp):
            for uid, u in json.load(open(fp, encoding="utf-8"))["units"].items():
                u["ch"] = ch
                U[uid] = u
        fq = os.path.join(ROOT, "_mt_score_%s.json" % ch)
        if os.path.exists(fq):
            for x in json.load(open(fq, encoding="utf-8")):
                score[x["id"]] = x

    allc = [(uid, seed, c) for uid, u in U.items() for seed, c in u["cands"].items()
            if c.get("prof")]
    print("单元 %d | 可测候选 %d" % (len(U), len(allc)))

    worst = {}
    for uid, seed, c in allc:
        if uid not in worst or (c.get("ct_pen") or 0) > (worst[uid][2].get("ct_pen") or 0):
            worst[uid] = (uid, seed, c)
    ranked = sorted(worst.values(), key=lambda t: -(t[2].get("ct_pen") or 0))
    top = ranked[:a.top]
    random.seed(11)
    pool = [t for t in ranked[a.top:] if (t[2].get("ct_pen") or 0) < 0.10]
    rand = random.sample(pool, min(a.rand, len(pool)))

    qrows = []
    for uid in QUESTIONS:
        if uid not in U:
            continue
        for seed, c in sorted(U[uid]["cands"].items()):
            if c.get("prof"):
                qrows.append((uid, seed, c, U[uid]))

    need = {}
    for uid, seed, c in top + rand:
        need[c["path"]] = "%s_s%s.mp3" % (uid, seed)
    for uid, seed, c, _u in qrows:
        need[c["path"]] = "%s_s%s.mp3" % (uid, seed)
    ADIR = os.path.join(ROOT, "_mt_contour_audio")
    print("需转码 %d 条音频" % len(need))
    audio, afile = {}, {}
    for i, p in enumerate(sorted(need), 1):
        fn = need[p]
        audio[p] = mp3_b64(p, os.path.join(ADIR, fn))
        afile[p] = "_mt_contour_audio/" + fn
        if i % 10 == 0:
            print("  %d/%d" % (i, len(need)))

    def row(uid, seed, c, u=None, show_pick=False):
        u = u or U[uid]
        pick = score.get(uid, {}).get("pick")
        tag = ""
        if show_pick and pick is not None:
            tag = ('<span class="pick">交付</span>' if str(pick) == str(seed)
                   else '<span class="alt">备选</span>')
        flags = (c.get("ct_flag") or "").replace(";", " ")
        b64 = audio.get(c["path"], "")
        txt = u["text"]
        txt = txt[:76] + ("…" if len(txt) > 76 else "")
        # ★ audio 必须放进 <td> 内：直接放在 <tr> 里是非法结构，HTML 解析器会把它
        #   foster-parent 到 <table> 之前，导致 tr.querySelector('audio') 永远为 null。
        return ('<tr data-i="1" onclick="play(this)"><td class="mono"><div class="cell">'
                '<button class="pl" onclick="hit(event,this)">&#9654;</button><div>%s<br>'
                '<span class="seed">s%s</span>%s</div>'
                '<audio preload="none" data-alt="%s" src="data:audio/mp3;base64,%s"></audio>'
                '</div></td>'
                '<td class="txt">%s</td><td>%s</td><td>%s</td>'
                '<td class="num">%+.1f</td><td class="num">%+.1f</td>'
                '<td class="num">%.2f</td><td>%s</td></tr>'
                % (uid, seed, tag, afile.get(c["path"], ""), b64,
                   txt, spark(c["prof"]), spark(c.get("e_prof") or [], color="#b45309"),
                   c.get("tail25", 0), c.get("end_st", 0), c.get("ct_pen") or 0,
                   ('<span class="bad">%s</span>' % flags) if flags else '<span class="ok">—</span>'))

    head = ('<tr><th>单元 / 种子</th><th>文本</th><th>F0 轮廓</th><th>能量轮廓</th>'
            '<th>末段斜率</th><th>句尾高度</th><th>ct 分</th><th>触发项</th></tr>')

    qhtml = ""
    byq = {}
    for uid, seed, c, u in qrows:
        byq.setdefault(uid, []).append((seed, c, u))
    for uid, items in byq.items():
        u = items[0][2]
        qhtml += ('<div class="qbox"><div class="qhead"><b>%s</b><span class="tag">%s</span>'
                  '<span class="qtxt">%s</span></div><table>%s%s</table></div>'
                  % (uid, u["cls"], u["text"], head,
                     "".join(row(uid, s, c, u2, True) for s, c, u2 in items)))

    # 已知答案的对照：交付版本把问句读成陈述
    found = ""
    bad_q = []
    for uid, items in byq.items():
        pick = str(score.get(uid, {}).get("pick"))
        for s, c, _ in items:
            if s == pick and c.get("tail25", 0) < -6.0:
                alt = [(ss, cc) for ss, cc, _ in items if cc.get("tail25", 0) > 0]
                bad_q.append((uid, c["tail25"], alt[0][0] if alt else None,
                              alt[0][1]["tail25"] if alt else None))
    if bad_q:
        lines = "".join("<li><b>%s</b> 交付版末段斜率 %+.1f（读成陈述）%s</li>"
                        % (u, t, ("；备选 s%s 是 %+.1f（上扬）" % (s, a)) if s else "")
                        for u, t, s, a in bad_q)
        found = ('<div class="note warn"><b>已查出 %d 条交付版本把问句读成陈述句：</b>'
                 '<ul>%s</ul></div>' % (len(bad_q), lines))

    nulls = [(uid, u) for uid, u in sorted(U.items()) if u["n_ok"] == 0]
    nullrows = "".join('<tr><td class="mono">%s</td><td class="txt">%s</td><td>%s</td></tr>'
                       % (uid, u["text"][:70],
                          (list(u["cands"].values())[0].get("nan_reason") or ""))
                       for uid, u in nulls)

    pen = np.array([c.get("ct_pen") or 0 for _, _, c in allc])
    html = TPL.substitute(
        css=CSS,
        n_unit=len(U), n_ok=len(allc),
        n_un=sum(1 for u in U.values() if u["n_ok"] == 0),
        n_single=sum(1 for u in U.values() if u["n_ok"] == 1),
        eout=sum(1 for _, _, c in allc if (c.get("pen_e") or 0) > 0.5),
        pen="%.2f" % float(np.median(pen)),
        found=found,
        qhtml=qhtml or '<div class="note">问句所在章尚未生成候选。</div>',
        ntop=len(top), head=head,
        toprows="".join(row(*t) for t in top),
        nrand=len(rand), randrows="".join(row(*t) for t in rand),
        nnull=len(nulls), nullrows=nullrows or '<tr><td colspan="3">无</td></tr>',
        nplay=len(top) + len(rand) + len(qrows),
    )
    open(a.out, "w", encoding="utf-8").write(html)
    print("→ %s  %.1f MB" % (a.out, os.path.getsize(a.out) / 1048576.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
