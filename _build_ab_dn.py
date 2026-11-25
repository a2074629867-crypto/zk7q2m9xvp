# -*- coding: utf-8 -*-
"""生成 A/B 审听页：原版 vs 除噪版，同一句并排，附实测指标。"""
import base64
import json
import os
import sys


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


PAIRS = [
    ("c2_0291", "Charles · 委屈", "Well, my mother can't afford to buy us a house, can she? We can't help that.",
     [("原版（55 段数字零 + 噪声忽有忽无）", "G:/_setup/_audio_ch123/out/c2_0291.wav"),
      ("除噪后：统一底噪 −77dB", "G:/_setup/_dn_fill/c2_0291.wav")]),
    ("c2_0299", "Charles · 紧张（旧：F0 338 像喊）", "Oh, yes. Well – a bit. He was a pilot, once. He was in the Battle of Britain. I've got...",
     [("旧版：neutral 参考，F0 338 / 底噪 −46", "G:/_setup/_audio_ch123/out/c2_0299.wav"),
      ("新版：soft 参考重生成，F0 200 / 底噪 −71", "G:/_setup/_dn_v2/c2_0299_soft.wav")]),
    ("c2_0304", "Thomas · 激动反抗", "I don't believe you, anyway, you're a liar, the Battle of Britain was in the war.",
     [("原版（you→anyway 有 33dB 深谷；尾部有零段）", "G:/_setup/_audio_ch123/out/c2_0304.wav"),
      ("仅统一底噪（逗号断点修不了，需重生成）", "G:/_setup/_dn_fill/c2_0304.wav")]),
]

HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>A/B 除噪对照</title>
<style>
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#f6f7f9;color:#1c1f23;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:#666;font-size:13px;margin-bottom:20px}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:16px;margin-bottom:16px}
.hd{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}
.id{font-family:ui-monospace,monospace;font-weight:600;font-size:15px}
.who{color:#7a5300;background:#fff5e0;border-radius:4px;padding:1px 7px;font-size:12px}
.txt{color:#444;font-size:13px;line-height:1.6;margin:6px 0 14px;padding-left:10px;border-left:3px solid #e3e6ea}
.row{display:flex;align-items:center;gap:12px;margin:8px 0}
.lbl{width:290px;font-size:13px;color:#333}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:7px 16px;font-size:13px;cursor:pointer;min-width:64px}
.btn:hover{background:#175ac4}
.btn.on{background:#c9302c}
.mono{font-family:ui-monospace,monospace;font-size:12px;color:#666}
table{border-collapse:collapse;font-size:12.5px;margin-top:10px;width:100%}
th,td{border-bottom:1px solid #eceff2;padding:6px 8px;text-align:left}
th{color:#666;font-weight:500;background:#fafbfc}
.bad{color:#c9302c}.good{color:#1a7f37}
</style></head><body>
<h1>A/B 除噪对照</h1>
<div class="sub">点播放键对比。所有指标为实测（parselmouth + 10ms 帧能量）。</div>
__CARDS__
</body></html>"""

CARD = """<div class="card">
<div class="hd"><span class="id">__ID__</span><span class="who">__WHO__</span></div>
<div class="txt">__TEXT__</div>
__ROWS__
</div>"""

ROW = """<div class="row"><div class="lbl">__LBL__</div>
<button class="btn" data-src="__SRC__">▶ 播放</button>
<span class="mono">__INFO__</span></div>"""

JS = """<script>
let cur=null;
document.querySelectorAll('.btn').forEach(b=>{
  b.onclick=()=>{
    if(cur){cur.pause();cur=null;}
    document.querySelectorAll('.btn').forEach(x=>{x.classList.remove('on');x.textContent='▶ 播放';});
    if(b.classList.contains('on')){return;}
    const a=new Audio(b.dataset.src);
    a.play();cur=a;b.classList.add('on');b.textContent='■ 停止';
    a.onended=()=>{b.classList.remove('on');b.textContent='▶ 播放';cur=null;};
  };
});
</script>"""

INFO = {
    "G:/_setup/_audio_ch123/out/c2_0291.wav": "55 段零 · 底噪 −113 · SNR 95.6",
    "G:/_setup/_dn_fill/c2_0291.wav": "6 段零 · 底噪 −77 · SNR 54.8",
    "G:/_setup/_audio_ch123/out/c2_0299.wav": "底噪 −46.1 · SNR 28.2",
    "G:/_setup/_dn_v2/c2_0299_soft.wav": "F0 338→200 · 底噪 −71 · cov 1.000 零 lead",
    "G:/_setup/_audio_ch123/out/c2_0304.wav": "底噪 −39.3 · 尾部 1381 零采样",
    "G:/_setup/_dn_fill/c2_0304.wav": "底噪 −43.7 · 零段仍在（需重生成）",
}


def main():
    cards = []
    for cid, who, text, vers in PAIRS:
        rows = []
        for lbl, p in vers:
            if not os.path.exists(p):
                rows.append('<div class="row"><div class="lbl">%s</div><span class="mono">缺文件</span></div>' % lbl)
                continue
            rows.append(ROW.replace("__LBL__", lbl).replace("__SRC__", b64(p))
                        .replace("__INFO__", INFO.get(p.replace("\\", "/"), "")))
        cards.append(CARD.replace("__ID__", cid).replace("__WHO__", who)
                     .replace("__TEXT__", text).replace("__ROWS__", "\n".join(rows)))
    html = HTML.replace("__CARDS__", "\n".join(cards)).replace("</body>", JS + "</body>")
    out = "G:/_setup/_ab_dn.html"
    open(out, "w", encoding="utf-8").write(html)
    print("%s  %.1f MB" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
