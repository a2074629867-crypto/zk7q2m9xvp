# -*- coding: utf-8 -*-
"""本轮修复总对照页：L053 / L078 / L083 / L087 + 三条电平校正"""
import base64
import os


def b64(p):
    with open(p, "rb") as f:
        return "data:audio/wav;base64," + base64.b64encode(f.read()).decode()


SEC = []


def sec(title, sub, rows):
    SEC.append((title, sub, rows))


sec("L053　Why have you come here?",
    "根因是 happy 标签把 F0 顶到 300Hz（假声区）。去 emo 后音高正常了，"
    "但 5 词短句原始语速 357wpm，拉到 0.70 会把声纹从 0.69 拖到 0.35。"
    "这次扫了 8 个新 seed，挑原始语速最慢的再拉。",
    [("旧版 · happy + 0.70 拉伸", "ch123_pre_l53/L053.wav",
      "F0 300Hz 破音；拉伸后声纹只剩 0.353（换人了）"),
     ("A · s53 @0.72（推荐）", "ch123_clean/L053.wav",
      "254wpm / 2.21s / F0 193Hz / 声纹 0.581 / ASR 全对"),
     ("B · s51 @0.78", "_l053try/L053_alt.wav",
      "278wpm / 2.66s / F0 226Hz / 声纹 0.627 —— 音色更好但偏快一点")])

sec("L078　No. But...",
    "But 的元音 /ʌ/ 从 0.132s 拉到 0.264s（rubberband，HNR 6.0→6.1dB、抖动 4.0→4.5%），"
    "另外补了 70ms 余弦淡出 —— 之前是 −19dB 直接跳到数字静音，等于话没说完就断。",
    [("旧版 · 结尾硬切", "_l078_A2.wav",
      "But 只有 0.23s，省略号完全没体现；结尾 −19dB → −240dB 只用了 5ms"),
     ("新版 · 元音拉长 + 70ms 淡出", "ch123_clean/L078.wav",
      "But 0.36s；结尾 −26 → −70dB 平滑收尾，之后才是静音")])

sec("L083　Here's the picture. Look, that's my father.",
    "你说「father 没读完就断了」—— 实测确认：旧版 father 的 /ðə/ 只有 0.07s，"
    "结尾 −18dB 在 5ms 内跳到数字静音。这次在 father 后面接一句 \". Yes.\" 一起生成，"
    "让模型把 father 念完整，再按静音把 Yes 切掉。",
    [("旧版 · father 被截断", "ch123_pre_l53/L083_old.wav",
      "/ðə/ 0.07s，结尾硬切"),
     ("新版 · 尾随短语生成后切掉", "ch123_clean/L083.wav",
      "/ðə/ 0.23s，结尾 −27 → −49dB 自然衰减；ASR 完整；264wpm")])

sec("L087　I don't know. Quite old, I suppose. Look, then, there's the photograph.",
    "全库逐段体检检出：p0 184Hz → p1 256Hz 邻段跳 72Hz，且 \"Look, then,\" 比主干响 11dB。"
    "三条都打了 sad 标签。",
    [("旧版 · sad", "ch123_pre_lvl/L087.wav",
      "邻段跳 72Hz + 电平差 11dB"),
     ("新版 · 去 emo 重生成", "_l087pick.wav",
      "见下方指标")])

sec("短促插话段电平校正（\"then?\" / \"Look,\" 比主干响 7-8dB）",
    "这类 0.3s 的短段生成出来电平偏高，听感是「突然吼一下」。"
    "只调短段、不动长段，段首尾各 15ms 余弦过渡。",
    [("L014 旧 · Can I have the key now, then?", "ch123_pre_lvl/L014.wav",
      "p1 \"then?\" −17.2dB，主干 −24.7dB（差 7.5dB）"),
     ("L014 新", "ch123_clean/L014.wav", "已拉到 −24.2dB"),
     ("L069 旧 · Your father should have left you some money, then, shouldn't he?",
      "ch123_pre_lvl/L069.wav", "p1 \"then,\" −17.4dB，主干 −23.9dB"),
     ("L069 新", "ch123_clean/L069.wav", "已拉到 −24.0dB"),
     ("L075 旧 · Oh, yes. Well, a bit. He was a pilot, once...", "ch123_pre_lvl/L075.wav",
      "p1 −18.5dB，主干 −25.8dB（差 7.3dB）"),
     ("L075 新", "ch123_clean/L075.wav", "已拉到 −25.5dB")])

sec("L085　A few years ago. I was about five. Or six.",
    "逐段体检发现末段 \"Or six.\" 有 <b>85% 的能量在 4kHz 以上</b>，HNR −9.4dB —— "
    "那不是说话，是气流噪声（对比前两段是 92%/86% 在 1kHz 以下）。"
    "换了 6 个 seed，<b>6 个全都是这样</b>，说明模型对「独立的两个词短句」固定这么念。"
    "解法：把 \"Or six.\" 并进前一句（\"about five, or six\"），噪声段直接消失。",
    [("旧版 · 末段是气流噪声", "ch123_pre_lvl/L085.wav",
      "\"Or six.\" 85% 能量在 4kHz 以上；声纹 0.642"),
     ("新版 · 并成一句", "ch123_clean/L085.wav",
      "两段都是正常语音（4kHz 以上只占 10%/34%）；262wpm；声纹 0.707；ASR 全对")])

cards = []
for title, sub, rows in SEC:
    inner = []
    for t, p, d in rows:
        if not os.path.exists(p):
            inner.append('<div class="card miss"><div class="t">%s</div>'
                         '<div class="d">文件缺失：%s</div></div>' % (t, p))
            continue
        inner.append("""
<div class="card">
  <div class="t">%s</div>
  <div class="d">%s</div>
  <audio controls preload="none" src="%s"></audio>
</div>""" % (t, d, b64(p)))
    cards.append('<div class="sec"><h2>%s</h2><div class="sub">%s</div>%s</div>'
                 % (title, sub, "".join(inner)))

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>本轮修复 · L053 / L078 / L083 / L087 + 电平</title>
<style>
body{margin:0;padding:26px 20px 60px;background:#14161a;color:#e6e8ec;
     font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:19px;margin:0 0 6px}
h2{font-size:15px;margin:0 0 4px;color:#8fd3ff}
.lead{color:#8b93a1;font-size:13px;margin-bottom:24px;max-width:900px}
.sec{margin-bottom:30px;padding-top:14px;border-top:1px solid #24282f}
.sub{color:#8b93a1;font-size:13px;margin-bottom:12px;max-width:900px}
.card{background:#1c1f25;border:1px solid #2a2f38;border-radius:10px;
      padding:13px 15px;margin-bottom:10px}
.card.miss{border-color:#4a2a2a}
.t{font-weight:600;color:#e6e8ec;margin-bottom:3px;font-size:14px}
.d{color:#8b93a1;font-size:12.5px;margin-bottom:9px}
audio{width:100%;height:34px}
</style></head><body>
<h1>本轮修复 · 6 组对照</h1>
<div class="lead">每条都是「旧 → 新」两个播放器，响度已经过同一套规范（voiced RMS −24dBFS），
所以听到的差别是表演和剪辑本身，不是谁响。</div>
__CARDS__
</body></html>"""

open("castle_round2.html", "w", encoding="utf-8").write(html.replace("__CARDS__", "".join(cards)))
print("ok", os.path.getsize("castle_round2.html"))
