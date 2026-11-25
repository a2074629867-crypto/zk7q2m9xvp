# -*- coding: utf-8 -*-
"""A/B 页：① 紧张档（现役喊 vs 小声重生成）② Hooper 超速（现役 vs 重生成 vs WSOLA）。"""
import base64
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
from _rate import rate  # noqa: E402
import numpy as np
import parselmouth
import soundfile as sf


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


def m(p, text):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    v = f[f > 0]
    r = rate(p, text)
    return "F0 %d · %.2fs · %d wpm · peak %.2f" % (
        int(np.median(v)) if len(v) else 0, len(y) / sr, r["wpm"], float(np.abs(y).max()))


rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}

PAIRS = [
    ("c2_0368", "Charles · 紧张（原作有省略号 → 该小声+停顿）",
     [("现役：nervous 参考（素材 F0 335=喊）", "G:/_setup/_audio_ch123/out/c2_0368.wav"),
      ("重生成：soft 参考（小声）", "G:/_setup/_regen_tense/ts_c2_0368__s42.wav")]),
    ("c2_0327", "Charles · 紧张（原作无停顿标记 → 该平常说话）",
     [("现役：F0 269", "G:/_setup/_audio_ch123/out/c2_0327.wav"),
      ("重生成：soft 参考", "G:/_setup/_regen_tense/ts_c2_0327__s42.wav")]),
    ("c1_0028", "Thomas(Edmund Hooper) · 激动反抗 · 412 wpm",
     [("现役 412 wpm", "G:/_setup/_audio_ch123/out/c1_0028.wav"),
      ("重生成：净化参考，267 wpm", "G:/_setup/_regen_hopper/hl_c1_0028__s42.wav")]),
    ("c2_0302", "Thomas · 警惕 · 414 wpm",
     [("现役 414 wpm", "G:/_setup/_audio_ch123/out/c2_0302.wav"),
      ("重生成：284 wpm", "G:/_setup/_regen_hopper/hl_c2_0302__s42.wav")]),
    ("c2_0461", "Thomas · 激动反抗 · 376 wpm",
     [("现役 376 wpm", "G:/_setup/_audio_ch123/out/c2_0461.wav"),
      ("WSOLA 拉到 0.78（后处理，只到 297）", "G:/_setup/_hooper_slow/c2_0461.wav")]),
]

HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>Hooper / 紧张 A/B</title>
<style>
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#14171a;color:#e6e8ea;margin:0;padding:24px;max-width:980px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:#9aa3ad;font-size:13px;margin-bottom:20px;line-height:1.6}
.card{background:#1b1f23;border:1px solid #2b3036;border-radius:10px;padding:16px;margin-bottom:16px}
.hd{display:flex;align-items:baseline;gap:10px;margin-bottom:6px;flex-wrap:wrap}
.id{font-family:ui-monospace,monospace;font-weight:600;font-size:15px;color:#79c0ff}
.who{color:#e3b341;background:#2d2413;border-radius:4px;padding:1px 7px;font-size:12px}
.txt{color:#b9c0c8;font-size:13px;line-height:1.65;margin:6px 0 14px;padding-left:10px;border-left:3px solid #2b3036}
.row{display:flex;align-items:center;gap:12px;margin:8px 0;flex-wrap:wrap}
.lbl{width:300px;font-size:13px;color:#d5d9dd}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:7px 16px;font-size:13px;cursor:pointer;min-width:64px}
.btn:hover{background:#388bfd}
.btn.on{background:#da3633}
.mono{font-family:ui-monospace,monospace;font-size:12px;color:#8b949e}
</style></head><body>
<h1>Hooper 语速 / 紧张档 A/B</h1>
<div class="sub">三组对照。指标为实测：parselmouth F0、10ms 帧能量去停顿 wpm。</div>
__CARDS__
__JS__
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


def main():
    cards = []
    for cid, who, vers in PAIRS:
        text = rows[cid]["text"]
        rs = []
        for lbl, p in vers:
            if not os.path.exists(p):
                rs.append('<div class="row"><div class="lbl">%s</div>'
                          '<span class="mono">缺文件 %s</span></div>' % (lbl, p))
                continue
            rs.append(ROW.replace("__LBL__", lbl).replace("__SRC__", b64(p))
                      .replace("__INFO__", m(p, text)))
        cards.append(CARD.replace("__ID__", cid).replace("__WHO__", who)
                     .replace("__TEXT__", text).replace("__ROWS__", "\n".join(rs)))
    html = HTML.replace("__CARDS__", "\n".join(cards)).replace("__JS__", JS)
    out = "G:/_setup/_ab_hooper.html"
    open(out, "w", encoding="utf-8").write(html)
    print("%s  %.1f MB" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
