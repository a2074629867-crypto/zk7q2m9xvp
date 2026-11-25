# -*- coding: utf-8 -*-
"""
生成「20 句判定页」—— 用来验证「闸」与用户听感到底有没有相关。

设计（病例-对照，不是随机抽样）：
  按闸分数 score = p1_bad*2 + max(tail,0) 分三层，各抽 8 / 6 / 6 句，打乱顺序。
  页面上**不显示分数、不显示分组**，只有一个播放键和三个主观档（顺 / 有点怪 / 难受）。
  这样 n=20 也能检出大效应（AUC>=0.75）；纯随机 20 句多半检不出来。

产物：_judge20_items.json（含分数与分组，供打分脚本用）、_judge20.html
"""
import json, random

DOC = 'G:/_setup'
random.seed(20261125)

R = json.load(open(f'{DOC}/_gate2.json', encoding='utf-8'))
W = json.load(open(f'{DOC}/_wl_final2.json', encoding='utf-8'))
texts = {k.rsplit('/', 1)[-1]: v['text'] for k, v in W.items()}


def score(r):
    return r['p1_bad'] * 2 + max(r['p2_tail'], 0)


pool = []
for r in R:
    if r['ver'] != 'new':
        continue
    if r['sid'] not in texts:
        continue
    if not (2.5 <= r['dur'] <= 11.0):      # 太短听不出韵律，太长听着累
        continue
    if r['n_peak'] < 2:
        continue
    pool.append(r)

pool.sort(key=score, reverse=True)
clean = [r for r in pool if score(r) == 0]
mid = [r for r in pool if 0 < score(r) <= 4]
high = [r for r in pool if score(r) >= 6]
print(f'池：all={len(pool)}  high(>=6)={len(high)}  mid(1-4)={len(mid)}  clean(0)={len(clean)}')

def take(lst, n, tag):
    out = random.sample(lst, min(n, len(lst)))
    for r in out:
        r['_grp'] = tag
    return out

sel = take(high, 8, 'high') + take(mid, 6, 'mid') + take(clean, 6, 'clean')
random.shuffle(sel)

items = []
for i, r in enumerate(sel, 1):
    items.append(dict(
        n=i, id=r['sid'], text=texts[r['sid']],
        wav=f"_regen_final/{r['sid']}.wav",
        _score=score(r), _grp=r['_grp'], _p1=r['p1_bad'], _tail=r['p2_tail'],
        _npeak=r['n_peak'], _dur=r['dur'], _top=r['top_w'], _last=r['last_pk_w'],
    ))

json.dump([{k: v for k, v in it.items() if not k.startswith('_') or k in ('_score', '_grp', '_p1', '_tail')}
           for it in items], open(f'{DOC}/_judge20_items.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)

front = [{k: v for k, v in it.items() if not k.startswith('_')} for it in items]
html = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>20 句听感判定</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--tx:#1b1b1a;--dim:#6b6b66;--line:#e3e3de;--acc:#2f6fd0;--warn:#c26a2b;--bad:#c0392b}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--card:#1e1e1c;--tx:#ececea;--dim:#9a9a94;--line:#2e2e2b;--acc:#6aa3f0}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:22px 16px 90px}
h1{font-size:19px;margin:0 0 6px}
.lead{color:var(--dim);font-size:13.5px;margin:0 0 16px}
.bar{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;z-index:5}
.meter{flex:1;height:5px;background:var(--line);border-radius:3px;overflow:hidden}
.meter i{display:block;height:100%;width:0;background:var(--acc);transition:.2s}
.c{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:13px 14px;margin:12px 0}
.c.done{border-color:var(--acc)}
.hd{display:flex;gap:10px;align-items:center;margin-bottom:8px}
.no{color:var(--dim);font-size:12.5px;min-width:26px}
button{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--tx);padding:7px 13px}
button:hover{border-color:var(--acc)}
.play{background:var(--acc);color:#fff;border-color:var(--acc);min-width:64px}
.tx{font-size:14.5px;line-height:1.75;margin:6px 0 10px;color:var(--tx)}
.tx b{color:var(--acc);font-weight:600}
.opts{display:flex;gap:8px;flex-wrap:wrap}
.opts button{padding:6px 12px;font-size:13.5px}
.opts button.on[data-v="0"]{background:#2e7d4f;border-color:#2e7d4f;color:#fff}
.opts button.on[data-v="1"]{background:var(--warn);border-color:var(--warn);color:#fff}
.opts button.on[data-v="2"]{background:var(--bad);border-color:var(--bad);color:#fff}
.note{margin-top:8px}
.note input{width:100%;font:inherit;font-size:13px;padding:6px 9px;border:1px solid var(--line);border-radius:7px;background:transparent;color:var(--tx)}
.fin{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:11px 16px;display:flex;gap:10px;align-items:center;justify-content:center}
.fin span{color:var(--dim);font-size:13px}
.fin button{background:var(--acc);color:#fff;border-color:var(--acc)}
.ok{color:#2e7d4f;font-size:13px}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:12px;overflow:auto;max-height:220px}
</style></head><body>
<div class="wrap">
<h1>20 句听感判定</h1>
<p class="lead">每句只听一遍，凭第一感觉点一个档。<b>不比较、不打分、没有正确答案</b>——这里只有你的耳朵是标准。<br>
「有点怪」= 你能指出哪里别扭但还能听；「难受」= 想重听或想跳过。</p>
<div class="bar"><span id="prog" style="font-size:13px;color:var(--dim)">0 / 20</span><div class="meter"><i id="mt"></i></div></div>
<div id="list"></div>
<div class="fin"><span id="st">已评 0 / 20</span><button id="sub">提交</button></div>
</div>
<script>
const ITEMS = __DATA__;
const state = {};
const list = document.getElementById('list');
const esc = s => s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
ITEMS.forEach(it => {
  const d = document.createElement('div');
  d.className = 'c'; d.id = 'c_' + it.id;
  d.innerHTML = `<div class="hd"><span class="no">${it.n}</span>
      <button class="play" data-id="${it.id}">播放</button></div>
    <div class="tx">${esc(it.text)}</div>
    <div class="opts">
      <button data-id="${it.id}" data-v="0">顺</button>
      <button data-id="${it.id}" data-v="1">有点怪</button>
      <button data-id="${it.id}" data-v="2">难受</button>
    </div>
    <div class="note"><input data-id="${it.id}" placeholder="想补一句就写（可不填）"></div>`;
  list.appendChild(d);
});
let cur = null;
list.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  const id = b.dataset.id;
  if (b.classList.contains('play')) {
    if (cur) { cur.pause(); cur.currentTime = 0; }
    const it = ITEMS.find(x => x.id === id);
    cur = new Audio(encodeURI(it.wav));
    cur.play().catch(err => alert('播放失败：' + err.message));
    return;
  }
  const v = +b.dataset.v;
  state[id] = { v, note: (document.querySelector(`input[data-id="${id}"]`).value || '').trim() };
  document.querySelectorAll(`button[data-id="${id}"][data-v]`).forEach(x => x.classList.toggle('on', +x.dataset.v === v));
  document.getElementById('c_' + id).classList.add('done');
  upd();
});
document.querySelectorAll('input[data-id]').forEach(inp => inp.addEventListener('change', () => {
  const id = inp.dataset.id; if (state[id]) state[id].note = inp.value.trim();
}));
function upd() {
  const n = Object.keys(state).length;
  document.getElementById('prog').textContent = n + ' / ' + ITEMS.length;
  document.getElementById('mt').style.width = (n / ITEMS.length * 100) + '%';
  document.getElementById('st').textContent = '已评 ' + n + ' / ' + ITEMS.length;
}
document.getElementById('sub').onclick = () => {
  const n = Object.keys(state).length;
  if (n < ITEMS.length && !confirm(`还有 ${ITEMS.length - n} 句没评，确定提交？`)) return;
  const payload = {test: 'judge20', ts: new Date().toISOString(),
    items: ITEMS.map(it => ({id: it.id, v: state[it.id] ? state[it.id].v : null,
                             note: state[it.id] ? state[it.id].note : ''}))};
  const body = JSON.stringify(payload);
  try { navigator.sendBeacon('http://127.0.0.1:8812/vote', new Blob([body], {type: 'text/plain'})); } catch (e) {}
  const box = document.createElement('pre'); box.textContent = body;
  document.querySelector('.wrap').appendChild(box);
  document.getElementById('st').innerHTML = '<i class="ok">已提交</i>（若没自动回传，把下面 JSON 贴给 AI）';
};
upd();
</script></body></html>"""
html = html.replace('__DATA__', json.dumps(front, ensure_ascii=False))
open(f'{DOC}/_judge20.html', 'w', encoding='utf-8').write(html)

print('\n抽中：')
for it in items:
    print(f"  {it['n']:>2} {it['id']:<9} [{it['_grp']:<5}] score={it['_score']:<2} "
          f"功能词峰={it['_p1']:<2} tail={it['_tail']:<2} 峰={it['_npeak']:<2} {it['_dur']:>5.1f}s")
print('\n分组：', {g: sum(1 for i in items if i['_grp'] == g) for g in ('high', 'mid', 'clean')})
print('页面：http://127.0.0.1:8811/_judge20.html')
