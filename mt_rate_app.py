# -*- coding: utf-8 -*-
"""旁白候选打分台 —— 本地 HTTP 服务，点选即落盘。

用法：
    G:/Python310/python.exe mt_rate_app.py            # 建页 + 起服务（默认 8765）
    G:/Python310/python.exe mt_rate_app.py --build     # 只建页不服务
    G:/Python310/python.exe mt_rate_app.py --rebuild   # 强制重新转码

页面： http://127.0.0.1:8765/
落盘： G:/_setup/_mt_labels_live.json  （每点一次就写，随时可读）
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = "G:/_setup"
FF = "E:/tool/oopz/ffmpeg.exe"
AUD = os.path.join(ROOT, "_mt_rate_audio")
LAB = os.path.join(ROOT, "_mt_labels_live.json")
HTML = os.path.join(ROOT, "_mt_rate.html")

CHS = ["ch1", "ch2", "ch3"]
PER_BUCKET = 20          # 长/中/短各抽多少条
MAX_CAND = 4


def raw_path(uid, seed):
    return os.path.join(ROOT, "_mt_raw_s%s" % seed, uid + ".wav")


def load_contour():
    """(uid, seed) -> (F0 21 点半音, 能量 21 点 dB)。缺失的条目不画曲线。"""
    idx = {}
    for ch in CHS:
        p = os.path.join(ROOT, "_mt_contour_%s.json" % ch)
        if not os.path.exists(p):
            continue
        for uid, u in json.load(open(p, encoding="utf-8"))["units"].items():
            for seed, c in u["cands"].items():
                if c.get("nan_reason") or not c.get("prof"):
                    continue
                idx[(uid, str(seed))] = ([round(float(v), 2) for v in c["prof"]],
                                         [round(float(v), 1) for v in (c.get("e_prof") or [])])
    return idx


def load_units():
    out = []
    for ch in CHS:
        p = os.path.join(ROOT, "_mt_score_%s.json" % ch)
        if not os.path.exists(p):
            continue
        for x in json.load(open(p, encoding="utf-8")):
            cands = [c for c in x["cands"] if not c["bad"]]
            cands = [c for c in cands if os.path.exists(raw_path(x["id"], c["seed"]))]
            if len(cands) < 2:
                continue
            out.append(dict(ch=ch, id=x["id"], text=x["text"],
                            pick=str(x["pick"]), cands=cands))
    return out


def trim_cands(cands, pick, k=MAX_CAND):
    """候选过多时按 centroid 均匀取，保证覆盖「暗—亮」整段，且一定含当前 pick。"""
    if len(cands) <= k:
        return sorted(cands, key=lambda c: c["centroid"])
    cs = sorted(cands, key=lambda c: c["centroid"])
    idx = [round(i * (len(cs) - 1) / (k - 1)) for i in range(k)]
    sel = [cs[i] for i in dict.fromkeys(idx)]
    cur = [c for c in cands if str(c["seed"]) == pick]
    if cur and str(cur[0]["seed"]) not in {str(c["seed"]) for c in sel}:
        sel[-1] = cur[0]
    return sorted(sel, key=lambda c: c["centroid"])


def sample():
    random.seed(7)
    units = load_units()
    buckets = {0: [], 1: [], 2: []}
    for u in units:
        w = len(u["text"].split())
        b = 0 if w > 14 else (1 if w >= 8 else 2)
        buckets[b].append(u)
    out = []
    for b in (0, 1, 2):
        pool = buckets[b][:]
        random.shuffle(pool)
        out += pool[:PER_BUCKET]
    out.sort(key=lambda u: (u["ch"], u["id"]))
    for u in out:
        u["cands"] = trim_cands(u["cands"], u["pick"])
    return out


def mp3(src, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        return True
    try:
        subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                        "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "96k", dst],
                       check=True)
        return True
    except Exception as e:
        print("  !! 转码失败", src, e)
        return False


def build(force=False):
    os.makedirs(AUD, exist_ok=True)
    units = sample()
    print("抽样 %d 条：长 %d / 中 %d / 短 %d" % (
        len(units),
        sum(1 for u in units if len(u["text"].split()) > 14),
        sum(1 for u in units if 8 <= len(u["text"].split()) <= 14),
        sum(1 for u in units if len(u["text"].split()) < 8)))

    items, n_ok = [], 0
    CT = load_contour()
    print("轮廓索引 %d 条候选" % len(CT))
    for i, u in enumerate(units, 1):
        opts = []
        for c in u["cands"]:
            fn = "%s_s%s.mp3" % (u["id"], c["seed"])
            dst = os.path.join(AUD, fn)
            if force and os.path.exists(dst):
                os.remove(dst)
            if not mp3(raw_path(u["id"], c["seed"]), dst):
                continue
            f0c, ec = CT.get((u["id"], str(c["seed"])), ([], []))
            opts.append(dict(seed=str(c["seed"]), file=fn,
                             cen=round(c["centroid"]), f0=round(c["f0"], 1),
                             wpm=round(c["wpm"]), fin=round(c["final_wpm"]),
                             spk=(round(c["spk"], 2) if c["spk"] == c["spk"] else None),
                             mos=(round(c["mos"], 2) if c.get("mos") is not None else None),
                             asr=round(c["ratio"], 2),
                             f0c=f0c, ec=ec))
        if len(opts) < 2:
            continue
        n_ok += 1
        items.append(dict(idx=n_ok, ch=u["ch"], id=u["id"], text=u["text"],
                          pick=u["pick"], opts=opts))
        if i % 10 == 0:
            print("  转码 %d/%d" % (i, len(units)))

    data = json.dumps(items, ensure_ascii=False)
    html = HTML_TMPL.replace("/*__DATA__*/", data)
    open(HTML, "w", encoding="utf-8").write(html)
    total_mp3 = len([f for f in os.listdir(AUD) if f.endswith(".mp3")])
    size = sum(os.path.getsize(os.path.join(AUD, f)) for f in os.listdir(AUD)) / 1e6
    print("页面 %s（%.1f KB） 音频 %d 个 / %.1f MB  单元 %d"
          % (HTML, os.path.getsize(HTML) / 1024, total_mp3, size, n_ok))
    return n_ok


# ---------------------------------------------------------------- HTTP
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            if not os.path.exists(HTML):
                build()
            self._send(200, open(HTML, "rb").read(), "text/html; charset=utf-8")
            return
        if p == "/state":
            d = json.load(open(LAB, encoding="utf-8")) if os.path.exists(LAB) else {}
            self._send(200, json.dumps(d, ensure_ascii=False).encode())
            return
        if p.startswith("/aud/"):
            fn = os.path.basename(p[5:])
            fp = os.path.join(AUD, fn)
            if os.path.exists(fp):
                self._send_audio(fp)
            else:
                self._send(404, b"{}")
            return
        self._send(404, b"{}")

    def _send_audio(self, fp):
        """必须支持 Range：原生 <audio> 拖进度条要靠 206 分段响应。"""
        size = os.path.getsize(fp)
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        partial = False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                elif not m.group(1):
                    start = 0
                end = min(end, size - 1)
                if start > end or start >= size:
                    start, end = 0, size - 1
                else:
                    partial = True
        n = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(n))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "max-age=600")
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        try:
            with open(fp, "rb") as f:
                f.seek(start)
                self.wfile.write(f.read(n))
        except Exception:
            pass

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if p == "/save":
            try:
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                self._send(400, b'{"ok":false}')
                return
            cur = json.load(open(LAB, encoding="utf-8")) if os.path.exists(LAB) else {}
            cur.update(d)
            tmp = LAB + ".tmp"
            json.dump(cur, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            os.replace(tmp, LAB)
            self._send(200, json.dumps({"ok": True, "n": len(cur)}).encode())
            return
        if p == "/clear":
            if os.path.exists(LAB):
                os.remove(LAB)
            self._send(200, b'{"ok":true}')
            return
        self._send(404, b"{}")


HTML_TMPL = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>旁白候选打分台</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#fafaf9;color:#1c1917;
 font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:0 18px 90px}
.top{position:sticky;top:0;z-index:20;background:rgba(250,250,249,.96);
 backdrop-filter:blur(6px);border-bottom:1px solid #e7e5e4;margin:0 -18px 18px;padding:10px 18px}
.t1{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.t1 h1{font-size:15px;margin:0;font-weight:600;letter-spacing:.2px}
.cnt{font-size:13px;color:#78716c}
.cnt b{color:#1c1917;font-size:15px}
.pw{flex:1;min-width:120px;height:6px;background:#e7e5e4;border-radius:3px;overflow:hidden}
.pw i{display:block;height:100%;width:0;background:#16a34a;transition:width .25s}
.t2{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px}
.btn{background:#fff;border:1px solid #d6d3d1;border-radius:7px;padding:5px 12px;
 font-size:12.5px;cursor:pointer;color:#1c1917;font-family:inherit}
.btn:hover{background:#f5f5f4}
.btn.on{background:#2563eb;border-color:#2563eb;color:#fff}
.btn.go{background:#16a34a;border-color:#16a34a;color:#fff}
.chk{font-size:12.5px;color:#57534e;display:flex;align-items:center;gap:5px;cursor:pointer}
.hint{font-size:12px;color:#a8a29e;margin-left:auto}
.card{background:#fff;border:1px solid #e7e5e4;border-radius:12px;padding:15px 17px;
 margin-bottom:14px;scroll-margin-top:120px;transition:border-color .15s,box-shadow .15s}
.card.active{border-color:#93c5fd;box-shadow:0 0 0 3px rgba(147,197,253,.18)}
.card.done{border-color:#bbf7d0;background:#f7fef9}
.hd{display:flex;align-items:baseline;gap:9px;margin-bottom:7px}
.no{font:600 13px/1 ui-monospace,monospace;color:#a8a29e;min-width:22px}
.tagc{font:11px/1 ui-monospace,monospace;background:#f5f5f4;color:#78716c;
 padding:3px 6px;border-radius:4px}
.wc{font-size:11.5px;color:#a8a29e}
.picked{margin-left:auto;font-size:11.5px;color:#15803d;font-weight:600;display:none}
.card.done .picked{display:block}
.tx{font-size:15.5px;line-height:1.62;color:#292524;margin:0 0 11px}
.opt{display:flex;align-items:center;gap:9px;padding:5px 9px;border-radius:8px;
 border:1px solid transparent;margin-bottom:3px;flex-wrap:wrap}
.opt:hover{background:#fafaf9}
.opt.sel{background:#f0fdf4;border-color:#86efac}
.opt .k{font:600 12px/1 ui-monospace,monospace;color:#a8a29e;width:14px}
.opt audio{width:232px;height:32px;flex:0 0 232px}
.sp{flex:0 0 152px;border-radius:5px;display:block}
.opt .meta{font:11.5px/1 ui-monospace,monospace;color:#a8a29e;
 margin-left:auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:none}
body.showm .opt .meta{display:block}
.sel2{background:#fff;border:1px solid #d6d3d1;border-radius:6px;
 padding:4px 13px;font-size:12px;cursor:pointer;color:#57534e;font-family:inherit;flex:0 0 auto}
.sel2:hover{background:#f0fdf4;border-color:#86efac;color:#15803d}
.opt.sel .sel2{background:#16a34a;border-color:#16a34a;color:#fff}
.no2{margin-top:8px;display:flex;gap:9px;align-items:center;
 padding-left:9px}
.no2 .sel2{color:#a8a29e}
.card.none .no2 .sel2{background:#b91c1c;border-color:#b91c1c;color:#fff}
.toast{position:fixed;right:18px;bottom:18px;background:#1c1917;color:#fff;
 padding:9px 15px;border-radius:9px;font-size:13px;opacity:0;transition:opacity .2s;
 pointer-events:none;z-index:50}
.toast.on{opacity:1}
.toast.err{background:#b91c1c}
.legend{background:#fffbeb;border:1px solid #fde68a;border-radius:9px;
 padding:11px 14px;font-size:13px;color:#78350f;margin-bottom:16px;line-height:1.7}
.legend b{color:#92400e}
@media (max-width:600px){.tx{font-size:14.5px}.wrap{padding:0 12px 80px}}
</style></head><body>
<div class="wrap">
<div class="top">
  <div class="t1">
    <h1>旁白候选打分台</h1>
    <span class="cnt">已标 <b id="dn">0</b> / <b id="tt">0</b></span>
    <div class="pw"><i id="pb"></i></div>
  </div>
  <div class="t2">
    <button class="btn go" id="bnext">跳到未标 ↓</button>
    <button class="btn" id="bprev">上一条 ↑</button>
    <button class="btn" id="bm">显示指标</button>
    <button class="btn" id="bx">导出 JSON</button>
    <span class="hint">数字键 1–4 选 · 0 = 都不行 · 空格 播放当前条</span>
  </div>
</div>
<div class="legend" id="lg">
  <b>怎么打：</b>用每行自带的播放器听（能拖进度条、能暂停）→ 点 <b>选它</b> 记下你觉得最自然的那条。
  每条只判<b>听感</b>，不用管技术指标。<br>
  <b>趋势图：</b><span style="color:#2563eb;font-weight:600">蓝线 = 音高走向</span> ·
  <span style="color:#d97706;font-weight:600">橙线 = 能量（重音）</span> ·
  <b>橙点 = 能量峰位</b>。横轴是整句时间，两条线各按自身范围缩放，只看走向。<br>
  <b>判据：</b>韵律起伏、重音落点、句尾走向、有没有「念稿子」的平铺感。
  如果<b>一条都不行</b>，点「都不行」。
</div>
<div id="list"></div>
</div>
<div class="toast" id="toast"></div>
<script>
var DATA = /*__DATA__*/;
var state = {};                 // uid -> {pick:"42"|"none", ts}
var cur = null;                 // 正在播的 audio
var curBtn = null;
var active = 0;
var TOTAL = DATA.length;

function $(s){ return document.querySelector(s); }
function toast(msg, err){
  var t = $('#toast'); t.textContent = msg;
  t.className = 'toast on' + (err ? ' err' : '');
  clearTimeout(t._h); t._h = setTimeout(function(){ t.className = 'toast'; }, 1600);
}

function render(){
  var h = '';
  DATA.forEach(function(u, i){
    h += '<div class="card" id="c-' + u.id + '" data-uid="' + u.id + '" data-i="' + i + '">'
      +  '<div class="hd"><span class="no">' + u.idx + '</span>'
      +  '<span class="tagc">' + u.ch + '</span>'
      +  '<span class="wc">' + u.text.split(/\s+/).length + ' 词</span>'
      +  '<span class="picked" id="p-' + u.id + '"></span></div>'
      +  '<p class="tx">' + esc(u.text) + '</p>';
    u.opts.forEach(function(o, k){
      h += '<div class="opt" data-seed="' + o.seed + '">'
        +  '<span class="k">' + (k + 1) + '</span>'
        +  '<audio controls preload="none" src="/aud/' + o.file + '" data-uid="' + u.id
        +  '" data-seed="' + o.seed + '"></audio>'
        +  '<button class="sel2" data-uid="' + u.id + '" data-seed="' + o.seed + '">选它</button>'
        +  spark(o.f0c, o.ec)
        +  '<span class="meta">重心 ' + o.cen + ' · F0 ' + o.f0 + ' · ' + o.wpm + '→' + o.fin
        +  ' wpm · 声纹 ' + (o.spk === null ? '—' : o.spk) + ' · MOS ' + (o.mos === null ? '—' : o.mos) + '</span>'
        +  '</div>';
    });
    h += '<div class="no2"><button class="sel2" data-uid="' + u.id + '" data-seed="none">都不行</button>'
      +  '<span class="wc">整条读得不对 / 需要重做</span></div>';
    h += '</div>';
  });
  $('#list').innerHTML = h;
  $('#tt').textContent = TOTAL;
  apply();
}

function esc(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// 趋势图：蓝线 = F0 音高走向（半音），橙线 = 能量（重音强弱），橙点 = 能量峰
// 两条线各自按本句 min/max 归一化，只比"走向"不比绝对量（量纲不同）。
function spark(f0, e){
  var W = 152, H = 36, pad = 3;
  if (!f0 || f0.length < 3)
    return '<svg class="sp" width="' + W + '" height="' + H + '"><rect width="' + W +
           '" height="' + H + '" rx="4" fill="#fafaf9"/><text x="8" y="22" font-size="10" ' +
           'fill="#d6d3d1">无曲线</text></svg>';
  function line(arr){
    var lo = Math.min.apply(null, arr), hi = Math.max.apply(null, arr);
    if (hi - lo < 1e-6) hi = lo + 1;
    var s = '';
    for (var i = 0; i < arr.length; i++){
      var x = pad + i * (W - 2 * pad) / (arr.length - 1);
      var y = H - pad - (arr[i] - lo) / (hi - lo) * (H - 2 * pad);
      s += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
    }
    return s;
  }
  var s = '<svg class="sp" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">'
        + '<title>蓝 = F0 音高走向 · 橙 = 能量（重音）· 橙点 = 能量峰位</title>'
        + '<rect width="' + W + '" height="' + H + '" rx="4" fill="#fafaf9"/>';
  if (e && e.length >= 3)
    s += '<path d="' + line(e) + '" fill="none" stroke="#d97706" stroke-width="1.2" opacity=".8"/>';
  s += '<path d="' + line(f0) + '" fill="none" stroke="#2563eb" stroke-width="1.5"/>';
  if (e && e.length >= 3){
    var mi = 0;
    for (var j = 1; j < e.length; j++) if (e[j] > e[mi]) mi = j;
    var lo2 = Math.min.apply(null, e), hi2 = Math.max.apply(null, e);
    var x2 = pad + mi * (W - 2 * pad) / (e.length - 1);
    var y2 = H - pad - (e[mi] - lo2) / ((hi2 - lo2) || 1) * (H - 2 * pad);
    s += '<circle cx="' + x2.toFixed(1) + '" cy="' + y2.toFixed(1) + '" r="2.3" fill="#d97706"/>';
  }
  return s + '</svg>';
}

function apply(){
  var n = 0;
  DATA.forEach(function(u){
    var st = state[u.id];
    var card = document.getElementById('c-' + u.id);
    if (!card) return;
    card.querySelectorAll('.opt').forEach(function(el){
      el.classList.toggle('sel', !!st && st.pick === el.dataset.seed);
    });
    card.classList.toggle('done', !!st);
    card.classList.toggle('none', !!st && st.pick === 'none');
    var lab = document.getElementById('p-' + u.id);
    if (st){
      lab.textContent = st.pick === 'none' ? '判：都不行' : ('已选 s' + st.pick);
      n++;
    } else {
      lab.textContent = '';
    }
  });
  $('#dn').textContent = n;
  $('#pb').style.width = (100 * n / Math.max(TOTAL, 1)) + '%';
}

function save(obj){
  return fetch('/save', {method:'POST', body: JSON.stringify(obj)})
    .then(function(r){ return r.json(); })
    .then(function(j){ toast('已保存（共 ' + j.n + ' 条）'); })
    .catch(function(){ toast('保存失败 —— 服务是否已停止？', true); });
}

function setPick(uid, seed){
  stopAll();                       // 判完就停，别让它继续念干扰下一条
  state[uid] = {pick: seed, ts: new Date().toISOString().slice(0,19)};
  apply();
  var o = {}; o[uid] = state[uid];
  save(o);
  setTimeout(function(){ nextUnlab(uid); }, 220);
}

function nextUnlab(fromUid){
  var i0 = active;
  for (var k = 1; k <= TOTAL; k++){
    var i = (i0 + k) % TOTAL;
    if (!state[DATA[i].id]){ focusCard(i, true); return; }
  }
  toast('全部标完了');
}

function focusCard(i, scroll){
  active = i;
  document.querySelectorAll('.card.active').forEach(function(e){ e.classList.remove('active'); });
  var card = document.getElementById('c-' + DATA[i].id);
  if (!card) return;
  card.classList.add('active');
  if (scroll) card.scrollIntoView({block:'center', behavior:'smooth'});
}

// ---------- 播放（原生控件：可拖进度条 / 可暂停 / 有音量）
function stopAll(){
  document.querySelectorAll('audio').forEach(function(a){ if(!a.paused) a.pause(); });
}
// 同时只让一条在播，并把卡片设为 active
document.addEventListener('play', function(e){
  var a = e.target;
  if (!a || a.tagName !== 'AUDIO') return;
  document.querySelectorAll('audio').forEach(function(x){
    if (x !== a && !x.paused) x.pause();
  });
  var card = a.closest('.card');
  if (card) focusCard(+card.dataset.i, false);
}, true);

// ---------- 事件
document.addEventListener('click', function(e){
  var t = e.target;
  if (t.tagName === 'AUDIO') return;                    // 别抢原生播放器的点击
  if (t.classList.contains('sel2')){
    e.stopPropagation();
    var card = t.closest('.card');
    focusCard(+card.dataset.i, false);
    setPick(t.dataset.uid, t.dataset.seed);
    return;
  }
  var card = t.closest ? t.closest('.card') : null;
  if (card) focusCard(+card.dataset.i, false);
});

document.addEventListener('keydown', function(e){
  if (e.target.tagName === 'INPUT') return;
  if (e.target.tagName === 'AUDIO') return;      // 原生控件自己处理空格
  var u = DATA[active];
  if (!u) return;
  if (e.key >= '1' && e.key <= '4'){
    var k = +e.key - 1;
    if (u.opts[k]) { setPick(u.id, u.opts[k].seed); e.preventDefault(); }
  } else if (e.key === '0'){
    setPick(u.id, 'none'); e.preventDefault();
  } else if (e.key === ' '){
    var a = document.querySelector('#c-' + u.id + ' audio');
    if (a) { if (a.paused) { var p = a.play(); if (p && p.catch) p.catch(function(){}); }
             else a.pause(); e.preventDefault(); }
  } else if (e.key === 'ArrowDown'){
    focusCard(Math.min(active + 1, TOTAL - 1), true); e.preventDefault();
  } else if (e.key === 'ArrowUp'){
    focusCard(Math.max(active - 1, 0), true); e.preventDefault();
  }
});

$('#bnext').onclick = function(){ nextUnlab(null); };
$('#bprev').onclick = function(){ focusCard(Math.max(active - 1, 0), true); };
$('#bm').onclick = function(){
  document.body.classList.toggle('showm');
  this.classList.toggle('on', document.body.classList.contains('showm'));
  this.textContent = document.body.classList.contains('showm') ? '隐藏指标' : '显示指标';
};
$('#bx').onclick = function(){
  var blob = new Blob([JSON.stringify(state, null, 1)], {type:'application/json'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'mt_labels_live.json';
  a.click();
  toast('已导出 ' + Object.keys(state).length + ' 条');
};

// ---------- 启动
fetch('/state').then(function(r){ return r.json(); }).then(function(d){
  state = d || {};
  render();
  focusCard(0, false);
  var firstUn = DATA.findIndex(function(u){ return !state[u.id]; });
  if (firstUn > 0) focusCard(firstUn, true);
}).catch(function(){
  render(); focusCard(0, false);
});
</script></body></html>"""


def serve(port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print("\n打分台已启动：  http://127.0.0.1:%d/" % port)
    print("标注实时写入：  %s" % LAB)
    print("按 Ctrl+C 停止\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        n = len(json.load(open(LAB, encoding="utf-8"))) if os.path.exists(LAB) else 0
        print("累计标注 %d 条 → %s" % (n, LAB))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    # --build 也必须真的重建：否则 HTML 已存在时会静默跳过（踩过一次）
    if a.build or a.rebuild or not os.path.exists(HTML):
        build(force=a.rebuild)
    if not a.build:
        serve(a.port)
