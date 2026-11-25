# -*- coding: utf-8 -*-
"""_make_final_ab.py —— 生成「交付版 vs 修复版」盲听页（5 条 + 1 对照）。

只有两个变量变了：切点（词尾用字符级强制对齐，不再用 whisper）与停顿是否压到目标。
页面上不显示身份、不显示分数、不显示时长；提交后揭晓。

用法：G:/Python310/python.exe -u _make_final_ab.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# (sid, 交付在前?)  —— 手动交替，避免顺序偏见
SPEC = [
    ("c1_0174", True),
    ("c2_0458", False),
    ("c1_0090", True),
    ("c3_0576", False),
    ("c1_0008", True),
    ("c3_0605", False),      # 对照：两版碎点都是 0、时长也没变
]

CUR = "_regen_final/%s.wav"
FIX = "_fix4_final/%s.wav"


def main():
    P = {}
    for l in open(os.path.join(HERE, "_narr_plan_for_pause.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        P[r["id"]] = r
    items = []
    for sid, cur_first in SPEC:
        if not (os.path.exists(os.path.join(HERE, CUR % sid))
                and os.path.exists(os.path.join(HERE, FIX % sid))):
            print("缺", sid)
            continue
        ps = [CUR % sid, FIX % sid]
        perm = [0, 1] if cur_first else [1, 0]
        items.append(dict(id=sid, text=P.get(sid, {}).get("text", ""),
                          takes=[dict(label="AB"[i], path=ps[perm[i]], kind=perm[i])
                                 for i in range(2)]))
        print(sid, "A =", "交付" if perm[0] == 0 else "修复", " B =", "交付" if perm[1] == 0 else "修复")

    html = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>停顿修好了吗</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1b1d21;--tx2:#666c78;--line:#e3e6ec;--acc:#2f6df6;--ok:#12855b}
@media (prefers-color-scheme:dark){:root{--bg:#15171b;--card:#1d2026;--tx:#e8eaee;--tx2:#9aa1ad;--line:#2b3038;--acc:#5b8cff;--ok:#3ecf8e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:780px;margin:0 auto;padding:22px 16px 80px}
h1{font-size:18px;margin:0 0 6px}
.sub{color:var(--tx2);font-size:13px;margin-bottom:6px}
.tip{color:var(--tx2);font-size:12.5px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 12px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
.txt{font-size:13px;color:var(--tx2);margin-bottom:10px;font-style:italic}
.row{display:flex;align-items:center;gap:10px;padding:7px 0;border-top:1px dashed var(--line)}
.row:first-of-type{border-top:0}
.lab{width:22px;height:22px;border-radius:6px;background:var(--line);display:grid;place-items:center;font-size:12px;font-weight:600}
button.p{padding:5px 14px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--tx);cursor:pointer;font-size:13px}
.pick{flex:1;text-align:right}
.pick button{padding:5px 12px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--tx);cursor:pointer;font-size:13px}
.pick button.sel{background:var(--acc);border-color:var(--acc);color:#fff}
.bar{position:sticky;bottom:0;background:var(--bg);padding:10px 0;border-top:1px solid var(--line);display:flex;gap:10px;align-items:center}
.bar button{padding:9px 18px;border-radius:9px;border:0;background:var(--acc);color:#fff;font-size:14px;cursor:pointer}
.bar button[disabled]{opacity:.45;cursor:default}
.note{color:var(--tx2);font-size:12px}
.verdict{margin-top:8px;font-size:13px;color:var(--ok);display:none}
</style></head><body><div class="wrap">
<h1>同一句话：停顿是后期切进去的，还是模型自己给的</h1>
<div class="sub">每句两条，顺序已打乱。</div>
<div class="tip">两版时长可能略有不同（修复版把过长的停顿压到了目标）。

<b>只判断一件事</b>：停顿处有没有「突然顿一下、又冒出一小截声音」。有就是碎，没有就是正常。</div>
<div id="list"></div>
<div class="bar"><button id="send" disabled>提交</button><span class="note" id="prog">0 / 0</span></div>
</div><script>
const ITEMS=__ITEMS__;
const state={};const root=document.getElementById('list');let cur=null;
ITEMS.forEach((it)=>{
  const card=document.createElement('div');card.className='card';
  card.innerHTML='<div class="txt">'+it.text+'</div>';
  it.takes.forEach((t,k)=>{
    const row=document.createElement('div');row.className='row';
    row.innerHTML='<span class="lab">'+t.label+'</span><button class="p">播放</button><div class="pick"><button data-k="'+k+'">选它</button></div>';
    row.querySelector('.p').onclick=()=>{if(cur){cur.pause();cur.currentTime=0;}cur=new Audio(encodeURI(t.path));cur.play().catch(e=>alert('播放失败：'+e.message));};
    row.querySelector('.pick button').onclick=(e)=>{state[it.id]=k;card.querySelectorAll('.pick button').forEach(b=>b.classList.remove('sel'));e.target.classList.add('sel');update();};
    card.appendChild(row);
  });
  const v=document.createElement('div');v.className='verdict';card.appendChild(v);
  root.appendChild(card);
});
function update(){const n=Object.keys(state).length;
 document.getElementById('prog').textContent=n+' / '+ITEMS.length;
 document.getElementById('send').disabled=n<ITEMS.length;
 try{localStorage.setItem('final_ab_v1',JSON.stringify(state));}catch(e){}}
document.getElementById('send').onclick=async()=>{
  const payload={test:'final_ab',ts:Date.now(),items:ITEMS.map(it=>{const t=it.takes[state[it.id]];
    return {id:it.id,picked:t.label,picked_kind:t.kind};})};
  try{
    await fetch('http://127.0.0.1:8812/vote',{method:'POST',body:JSON.stringify(payload)});
    document.getElementById('send').textContent='已提交';document.getElementById('send').disabled=true;
    document.querySelectorAll('.card').forEach((c,i)=>{
      const v=c.querySelector('.verdict');v.style.display='block';
      const fixedIdx=ITEMS[i].takes.findIndex(t=>t.kind===1);
      v.textContent='揭晓：第 '+(fixedIdx+1)+' 条是「修复版」（切点用字符级强制对齐 + 停顿压到目标）';});
  }catch(e){alert('提交失败：'+e.message);}
};
try{const s=JSON.parse(localStorage.getItem('final_ab_v1')||'{}');Object.assign(state,s);
 ITEMS.forEach((it,i)=>{if(s[it.id]===undefined)return;const c=root.children[i];
  const b=c.querySelectorAll('.pick button');if(b[s[it.id]])b[s[it.id]].classList.add('sel');});update();}catch(e){}
</script></body></html>"""
    html = html.replace("__ITEMS__", json.dumps(items, ensure_ascii=False))
    out = os.path.join(HERE, "_final_ab.html")
    open(out, "w", encoding="utf-8").write(html)
    print("→", out, len(html))


if __name__ == "__main__":
    main()
