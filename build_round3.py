# -*- coding: utf-8 -*-
"""本轮修复对照页：L078 换 But + L087/L069/L063 段电平拉平。"""
import base64, os

ROWS = [
    ("L078　No. But...", "Charles · 用户两次点名「But 炸音」",
     [("旧版 · But 来自 3.3 倍拉伸", "_trimfix/L078_old.wav",
       "But 段 HNR <b>4.1dB</b>（No 段 11.3），段间电平差 2.4dB，总 1.27s"),
      ("新版 · But 换成干净素材", "ch123_final/L078.wav",
       "But 段 HNR <b>9.8dB</b>，段间电平差 <b>0.3dB</b>，But 0.327s（原 0.35s）；两段声纹互比 0.956")]),
    ("L087　I don't know. Quite old, I suppose. Look, then, there's the photograph.",
     "Charles · 段间电平偏离 11.0dB",
     [("旧版 · Look, 高出主干 11dB", "_trimfix/L087.wav",
       "p2（0.12s「Look,」）−14.9dB，p3（0.28s「then,」）−15.0dB，主干 −25.8dB ⇒ 听感是「突然吼一下」"),
      ("新版 · 拉回主干", "ch123_final/L087.wav",
       "四段偏离 −0.2 / 0.0 / <b>+1.0</b> / +0.1 / +1.8 dB，最大偏离 11.0 → <b>1.8dB</b>")]),
    ("L069　Your father should have left you some money, then, shouldn't he? Didn't he have a house?",
     "Hooper · 段间电平偏离 7.3dB",
     [("旧版 · then, 高出 7.3dB", "_trimfix/L069.wav",
       "p1（0.33s「then,」）−17.4dB，主干 −24.8dB"),
      ("新版 · 拉回主干", "ch123_final/L069.wav",
       "四段偏离 0.0 / <b>+0.2</b> / +0.9 / +0.8 dB，最大偏离 7.3 → <b>0.9dB</b>")]),
    ("L063　Yes. No. Well, it was in somebody's house.",
     "Charles · 段间电平偏离 6.2dB",
     [("旧版 · Yes. 高出 6.2dB", "_trimfix/L063.wav",
       "p0（0.32s「Yes.」）−18.3dB，主干 −24.4dB"),
      ("新版 · 拉回主干", "ch123_final/L063.wav",
       "最大偏离 6.2 → <b>3.4dB</b>（p1 剩 +3.4，低于 5dB 阈值未动）")]),
]


def b64(p):
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()


def card(title, sub, rows):
    h = ['<div class="card"><div class="t">%s</div><div class="s">%s</div>' % (title, sub)]
    for name, path, note in rows:
        h.append('<div class="row"><div class="lbl">%s</div><audio controls preload="none" src="data:audio/wav;base64,%s"></audio>'
                 '<div class="note">%s</div></div>' % (name, b64(path), note))
    h.append("</div>")
    return "\n".join(h)


body = "\n".join(card(t, s, r) for t, s, r in ROWS)

HTML = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>L078 / 段电平 修复对照</title>
<style>
body{margin:0;padding:28px 18px 60px;background:#12141a;color:#e6e8ee;
     font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:20px;margin:0 0 6px}
.sub{color:#9aa3b5;font-size:13px;margin-bottom:22px;line-height:1.8}
.sub b{color:#8fd4ff}
.card{background:#1a1d26;border:1px solid #262a36;border-radius:12px;padding:16px 18px;margin-bottom:16px}
.t{font-size:15px;font-weight:600;margin-bottom:4px}
.s{color:#8b93a7;font-size:12px;margin-bottom:14px}
.row{display:grid;grid-template-columns:190px 1fr;gap:10px 16px;align-items:center;
     padding:10px 0;border-top:1px solid #232733}
.row:first-of-type{border-top:0}
.lbl{font-size:13px;color:#c7cddb}
audio{width:100%;height:34px}
.note{grid-column:1/-1;font-size:12px;color:#8b93a7;margin-top:-4px}
.note b{color:#7ee0a8}
</style></head><body>
<h1>本轮修复：L078 的 But + 三条段电平</h1>
<div class="sub">
这一轮先把「为什么低分」查清了：<b>不是拉伸</b>（原版 vs 现版 DIS 差 &lt;0.3）、
<b>不是段间噪声</b>（静音清零后 DIS 只动 0.1）、<b>不是 emo</b>（calm 组中位 4.46，比无标签的 4.41 还高）、
<b>不是停顿</b>（DIS 与最大停顿相关系数 −0.01）。<br>
真正能改的是<b>段间电平偏离</b>和<b>素材本身的 HNR</b>，这两项都修了。<br>
响度全部对齐 −24dBFS，可以直接比。
</div>
__BODY__
</body></html>"""

out = HTML.replace("__BODY__", body)
open("G:/_setup/castle_round3.html", "w", encoding="utf-8").write(out)
print("OK G:/_setup/castle_round3.html %.2f MB" % (os.path.getsize("G:/_setup/castle_round3.html") / 1e6))
