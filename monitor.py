"""GPU 生成实时看板 —— 本地起 HTTP，浏览器打开 http://127.0.0.1:8899

后台线程每 ~10 秒通过 rcc.py 拉一次云端状态（ntfy 通道，一轮约 8 秒），
页面每 3 秒 fetch /api 取缓存。云端不受影响，不额外占 GPU。
"""
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = {"d": None, "err": None, "ts": 0}
LOCK = threading.Lock()
PORT = 8899

PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPU 生成看板</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1a1d21;--tx2:#6b7280;--line:#e5e7eb;
--ok:#16a34a;--warn:#d97706;--bad:#dc2626;--ac:#2563eb;--gpu:#7c3aed}
html[data-t="dark"]{--bg:#0f1115;--card:#171a20;--tx:#e8eaed;--tx2:#9aa0aa;--line:#262b33;
--ok:#34d399;--warn:#fbbf24;--bad:#f87171;--ac:#60a5fa;--gpu:#a78bfa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:20px}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
h1{font-size:17px;margin:0;font-weight:650;letter-spacing:.2px}
.hd{display:flex;gap:10px;align-items:center;font-size:12px;color:var(--tx2)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);display:inline-block}
.dot.off{background:var(--bad)}
button{background:var(--card);border:1px solid var(--line);color:var(--tx2);
border-radius:7px;padding:5px 10px;font-size:12px;cursor:pointer}
button:hover{color:var(--tx)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.k{font-size:11px;color:var(--tx2);letter-spacing:.4px;text-transform:uppercase;margin-bottom:6px}
.v{font-size:26px;font-weight:680;font-variant-numeric:tabular-nums;line-height:1.1}
.v small{font-size:13px;font-weight:500;color:var(--tx2);margin-left:3px}
.bar{height:6px;background:var(--line);border-radius:4px;overflow:hidden;margin-top:10px}
.bar>i{display:block;height:100%;background:var(--ac);border-radius:4px;transition:width .5s}
.bar.g>i{background:var(--gpu)}
.bar.ok>i{background:var(--ok)}
.row{display:flex;gap:12px;margin-bottom:14px}
.row>.card{flex:1}
.qc{display:flex;gap:18px;font-size:13px}
.qc b{font-size:20px;font-variant-numeric:tabular-nums;display:block;line-height:1.3}
.log{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;
font:12px/1.75 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--tx2);
max-height:230px;overflow:auto;white-space:pre-wrap;word-break:break-all}
.log .P{color:var(--ok)}.log .W{color:var(--warn)}.log .F{color:var(--bad)}
.meta{font-size:12px;color:var(--tx2);margin-top:10px}
@media(max-width:820px){.grid{grid-template-columns:repeat(2,1fr)}.row{flex-direction:column}}
</style></head><body><div class="wrap">
<header><h1>前三章生成 · 实时看板</h1>
<div class="hd"><span class="dot" id="dot"></span><span id="ts">连接中…</span>
<button id="th">深色</button></div></header>

<div class="grid">
  <div class="card"><div class="k">已完成</div><div class="v" id="done">–<small>/955</small></div>
    <div class="bar"><i id="pbar" style="width:0"></i></div></div>
  <div class="card"><div class="k">旁白 A / B</div><div class="v" id="ab">–</div>
    <div class="bar"><i id="abar" style="width:0"></i></div></div>
  <div class="card"><div class="k">GPU 利用率</div><div class="v" id="gu">–<small>%</small></div>
    <div class="bar g"><i id="gbar" style="width:0"></i></div></div>
  <div class="card"><div class="k">显存</div><div class="v" id="gm">–<small>MiB</small></div>
    <div class="bar g"><i id="mbar" style="width:0"></i></div></div>
</div>

<div class="row">
  <div class="card"><div class="k">质检分布</div>
    <div class="qc">
      <div><b id="qp" style="color:var(--ok)">–</b>PASS</div>
      <div><b id="qw" style="color:var(--warn)">–</b>WARN</div>
      <div><b id="qf" style="color:var(--bad)">–</b>FAIL</div>
    </div></div>
  <div class="card"><div class="k">运行中 worker</div><div class="v" id="wk">–</div>
    <div class="meta" id="eta">—</div></div>
</div>

<div class="k" style="margin-bottom:8px">最近日志</div>
<div class="log" id="log">等待数据…</div>
<div class="meta" id="fails"></div>
</div>
<script>
const $=s=>document.querySelector(s);
const th=$('#th');
if(localStorage.t==='dark'){document.documentElement.dataset.t='dark';th.textContent='浅色';}
th.onclick=()=>{const d=document.documentElement.dataset.t==='dark';
  document.documentElement.dataset.t=d?'':'dark';th.textContent=d?'深色':'浅色';
  localStorage.t=d?'':'dark';};

const TOTAL=955, NARR=716;
let first=null;
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;');}
function paint(d){
  const narr=(d.a||0)+(d.b||0);
  const done=d.audio||0;
  $('#done').innerHTML=done+'<small>/'+TOTAL+'</small>';
  $('#pbar').style.width=Math.min(100,done/TOTAL*100)+'%';
  $('#ab').innerHTML=narr+'<small>/'+NARR+'</small>';
  $('#abar').style.width=Math.min(100,narr/NARR*100)+'%';
  if(d.gpu_util>=0){
    $('#gu').innerHTML=d.gpu_util+'<small>%</small>';
    $('#gbar').style.width=d.gpu_util+'%';
    $('#gm').innerHTML=d.gpu_mem+'<small>MiB</small>';
    $('#mbar').style.width=(d.gpu_mem/d.gpu_total*100)+'%';
  }
  $('#qp').textContent=d.pass??'–';
  $('#qw').textContent=d.warn??'–';
  $('#qf').textContent=d.fail??'–';
  $('#wk').textContent=d.workers??'–';
  const now=Date.now();
  if(first===null&&done>0){first={t:now,n:done};}
  if(first&&done>first.n){
    const sp=(done-first.n)/((now-first.t)/60000);
    const left=(TOTAL-done)/sp;
    $('#eta').textContent='速率 '+sp.toFixed(1)+' 条/分 · 剩余约 '+Math.round(left)+' 分钟';
  }
  const L=(d.recent||[]).map(l=>{
    const c=/ FAIL /.test(l)?'F':/ WARN /.test(l)?'W':'P';
    return '<span class="'+c+'">'+esc(l)+'</span>';}).join('\\n');
  $('#log').innerHTML=L||'—';
  $('#fails').textContent=(d.fails&&d.fails.length)?('FAIL 明细：'+d.fails.join(' | ')):'';
  $('#ts').textContent=d.ts+' 更新';
  $('#dot').className='dot';
}
async function tick(){
  try{
    const r=await fetch('/api',{cache:'no-store'});
    const j=await r.json();
    if(j.d) paint(j.d);
    if(j.err){$('#dot').className='dot off';$('#ts').textContent='通道异常';}
  }catch(e){$('#dot').className='dot off';$('#ts').textContent='本地服务断';}
}
tick();setInterval(tick,3000);
</script></body></html>
"""


def poll():
    script = os.path.join(ROOT, "_tmp", "status.sh")
    while True:
        try:
            p = subprocess.run(
                [sys.executable, os.path.join(ROOT, "rcc.py"),
                 "--timeout", "100", "-f", script],
                cwd=ROOT, capture_output=True, text=True, timeout=180,
                encoding="utf-8", errors="replace")
            txt = p.stdout or ""
            i = txt.find("{")
            if i >= 0:
                d = json.loads(txt[i:txt.rfind("}") + 1])
                with LOCK:
                    STATE["d"] = d
                    STATE["ts"] = time.time()
                    STATE["err"] = None
            else:
                with LOCK:
                    STATE["err"] = (p.stderr or txt)[-200:]
        except Exception as e:
            with LOCK:
                STATE["err"] = str(e)[:200]
        time.sleep(4)


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api"):
            with LOCK:
                body = json.dumps({"d": STATE["d"], "err": STATE["err"]},
                                  ensure_ascii=False).encode()
            ct = "application/json; charset=utf-8"
        else:
            body = PAGE.encode()
            ct = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    threading.Thread(target=poll, daemon=True).start()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), H) as s:
        print("看板: http://127.0.0.1:%d" % PORT, flush=True)
        s.serve_forever()
