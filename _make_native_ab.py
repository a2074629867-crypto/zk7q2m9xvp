# -*- coding: utf-8 -*-
"""_make_native_ab.py —— 生成「后期切停顿 vs edit 原生插停顿」的盲听页。

每句 3 条：源（模型自己给的停顿）/ 原生 edit / 当前交付（后期切）。
顺序按 id 哈希打乱，页面不显示是哪条；选完才揭晓。

用法： G:/Python310/python.exe _make_native_ab.py
"""
import hashlib
import json
import os

ROOT = "G:/_setup"
OUT = os.path.join(ROOT, "_native_ab.html")

# (sid, 文本, 源, 原生, 当前交付, 原生做了什么)
ITEMS = [
    ("c3_0948", "The third week of term, he had been ill.",
     "_regen_1123_norm/c3_0948.wav",
     "_edit_pause/c3_0948_L2_s42.wav",
     "_regen_final/c3_0948.wav",
     "原生 ins level 2（洞 0.30→0.76s，单洞）",
     "后期切：单洞 0.98s"),
    ("c1_0174", "He read some of them out to himself, in a low voice.",
     "_regen_1123_norm/c1_0174.wav",
     "_edit_pause/c1_0174_Lr2_s42.wav",
     "_regen_final/c1_0174.wav",
     "原生 red level 2（1.06→0.58s，单洞）",
     "后期切：双洞 0.52s + 1.06s（叠在一起）"),
]


def order(sid):
    h = int(hashlib.md5(sid.encode()).hexdigest(), 16)
    idx = [0, 1, 2]
    for i in range(2, 0, -1):
        j = (h >> (i * 4)) % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
    return idx


def main():
    items = []
    for sid, text, src, nat, cur, what_nat, what_cur in ITEMS:
        paths = [src, nat, cur]
        if not all(os.path.exists(os.path.join(ROOT, p)) for p in paths):
            print("跳过 %s：文件缺失" % sid)
            continue
        perm = order(sid)
        takes = []
        for slot, k in enumerate(perm):
            takes.append({"label": "ABCD"[slot], "path": paths[k], "kind": k})
        items.append({"id": sid, "text": text, "takes": takes,
                      "what_nat": what_nat, "what_cur": what_cur})
    print("句子 %d 条，音频 %d 个" % (len(items), sum(len(i["takes"]) for i in items)))

    js = json.dumps(items, ensure_ascii=False)
    html = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>原生插停顿 vs 后期切停顿</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1b1d21;--tx2:#666c78;--line:#e3e6ec;--acc:#2f6df6;--ok:#12855b}
@media (prefers-color-scheme:dark){:root{--bg:#15171b;--card:#1d2026;--tx:#e8eaee;--tx2:#9aa1ad;--line:#2b3038;--acc:#5b8cff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:22px 16px 60px}
h1{font-size:19px;margin:0 0 6px}
.sub{color:var(--tx2);font-size:13px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
.txt{font-size:14px;color:var(--tx2);margin-bottom:10px;font-style:italic}
.row{display:flex;align-items:center;gap:10px;padding:7px 0;border-top:1px dashed var(--line)}
.row:first-of-type{border-top:0}
.lab{width:22px;height:22px;border-radius:6px;background:var(--line);display:grid;place-items:center;font-size:12px;font-weight:600}
button.p{flex:0 0 auto;padding:5px 12px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--tx);cursor:pointer;font-size:13px}
button.p:hover{border-color:var(--acc)}
.pick{flex:1;text-align:right}
.pick button{padding:5px 12px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--tx);cursor:pointer;font-size:13px}
.pick button.sel{background:var(--acc);border-color:var(--acc);color:#fff}
.verdict{margin-top:8px;font-size:13px;color:var(--ok);display:none}
.bar{position:sticky;bottom:0;background:var(--bg);padding:10px 0;border-top:1px solid var(--line);display:flex;gap:10px;align-items:center}
.bar button{padding:9px 18px;border-radius:9px;border:0;background:var(--acc);color:#fff;font-size:14px;cursor:pointer}
.bar button[disabled]{opacity:.45;cursor:default}
.note{color:var(--tx2);font-size:12px}
</style></head><body><div class="wrap">
<h1>同一句话，停顿是「模型自己给」还是「后期切进去」</h1>
<div class="sub">每句三条，顺序已打乱、不显示身份。你只需点「这句最自然的是哪条」。全部选完点提交，我这边才算得出结果。</div>
<div id="list"></div>
<div class="bar"><button id="send" disabled>提交</button><span class="note" id="prog">0 / 0</span></div>
</div>
<script>
const ITEMS = __ITEMS__;
const state = {};
const root = document.getElementById('list');
let cur = null;
ITEMS.forEach((it, i) => {
  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = '<div class="txt">' + it.text + '</div>';
  it.takes.forEach((t, k) => {
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = '<span class="lab">' + t.label + '</span>' +
      '<button class="p">播放</button><div class="pick"><button data-k="' + k + '">选它</button></div>';
    row.querySelector('.p').onclick = () => {
      if (cur) { cur.pause(); cur.currentTime = 0; }
      cur = new Audio(encodeURI(t.path));
      cur.play().catch(e => alert('播放失败：' + e.message));
    };
    row.querySelector('.pick button').onclick = (e) => {
      state[it.id] = k;
      card.querySelectorAll('.pick button').forEach(b => b.classList.remove('sel'));
      e.target.classList.add('sel');
      update();
    };
    card.appendChild(row);
  });
  const v = document.createElement('div');
  v.className = 'verdict';
  card.appendChild(v);
  root.appendChild(card);
});
function update(){
  const n = Object.keys(state).length;
  document.getElementById('prog').textContent = n + ' / ' + ITEMS.length;
  document.getElementById('send').disabled = n < ITEMS.length;
  try { localStorage.setItem('native_ab_v1', JSON.stringify(state)); } catch (e) {}
}
document.getElementById('send').onclick = async () => {
  const payload = {test: 'native_ab', ts: Date.now(), items: ITEMS.map(it => {
    const k = state[it.id];
    const t = it.takes[k];
    return {id: it.id, picked: t.label, picked_kind: t.kind};
  })};
  try {
    await fetch('http://127.0.0.1:8812/vote', {method: 'POST', body: JSON.stringify(payload)});
    document.getElementById('send').textContent = '已提交';
    document.getElementById('send').disabled = true;
    // 揭晓
    document.querySelectorAll('.card').forEach((card, i) => {
      const it = ITEMS[i];
      const v = card.querySelector('.verdict');
      v.style.display = 'block';
      v.textContent = '揭晓：源 / ' + it.what_nat + ' / ' + it.what_cur.replace('后期切：', '当前交付（后期切）：');
    });
  } catch (e) {
    alert('提交失败：' + e.message + '\\n可以截图发我。');
  }
};
// 本地暂存，刷新不丢
const KEY = 'native_ab_v1';
try {
  const s = JSON.parse(localStorage.getItem(KEY) || '{}');
  Object.assign(state, s);
  ITEMS.forEach((it, i) => {
    if (s[it.id] === undefined) return;
    const card = root.children[i];
    const btns = card.querySelectorAll('.pick button');
    if (btns[s[it.id]]) btns[s[it.id]].classList.add('sel');
  });
  update();
} catch (e) {}

</script></body></html>"""
    html = html.replace("__ITEMS__", js)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("→", OUT)


if __name__ == "__main__":
    main()
