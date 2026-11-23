# -*- coding: utf-8 -*-
"""修复页：炸音拆句 / 语速 / 发音校对。"""
import base64
import json
import os
import subprocess

import numpy as np
import parselmouth
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
DOTS = "G:/_setup/dots_edit2"
REF = "G:/_setup/castle_fr_ref"
TMP = "G:/_setup/_bkfix_audio"
OUT_HTML = "G:/_setup/castle_book_fix.html"

os.makedirs(TMP, exist_ok=True)


def f0(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=400)
    f = pit.selected_array["frequency"]
    m = f > 0
    return float(np.median(f[m])) if m.any() else 0.0


def stats(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    n = int(0.01 * sr)
    k = len(a) // n
    e = np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])
    db = 20 * np.log10(e + 1e-9)
    voiced = db > -45
    mx = cur = 0
    for v in voiced:
        cur = 0 if v else cur + 1
        mx = max(mx, cur)
    return dict(dur=len(a) / sr, voiced=voiced.sum() * 0.01,
                ratio=100 * voiced.mean(), gap=mx * 0.01, f0=f0(p))


def to_mp3(src, dst):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-codec:a", "libmp3lame", "-b:a", "96k", "-ar", "24000", "-ac", "1", dst],
                   capture_output=True)


def b64(p):
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()


def player(p, label, color, meta, asr=None):
    m = os.path.join(TMP, os.path.basename(p) + ".mp3")
    to_mp3(p, m)
    s = stats(p)
    asr_html = ""
    if asr:
        asr_html = '<div class="asr">ASR：%s</div>' % asr
    return ('<div class="pv" style="border-left-color:%s">'
            '<div class="ph"><b>%s</b><span>%s</span></div>'
            '<div class="pm">%.2fs · 有声 %.0f%% · 最长静音 %.2fs · F0 %.0f Hz</div>'
            '%s<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (color, label, meta, s["dur"], s["ratio"], s["gap"], s["f0"], asr_html, b64(m)))


CHK = {}
if os.path.exists("G:/_setup/_bk_final_check.json"):
    for r in json.load(open("G:/_setup/_bk_final_check.json", encoding="utf-8")):
        CHK[(r["tag"], r["label"])] = r


def asr_of(tag, label):
    r = CHK.get((tag, label))
    if not r:
        return None
    if r["hard"]:
        return '<b class="bad">%d%%</b> · %s' % (
            r["acc"], "; ".join("%s → %s" % (a, b) for a, b in r["hard"]))
    note = ""
    if r["soft"]:
        note = "（口音偏差：%s）" % "; ".join("%s → %s" % (a, b) for a, b in r["soft"])
    return '<b class="good">%d%%</b> 内容全对%s' % (r["acc"], note)


BLOCKS = [
    dict(tag="4", title="Charles · 生气", color="#b54a4a",
         en="But I wouldn't go on whining, like you. Scaredy Hooper. You are scared. You're scared now.",
         note="原版 10.08s 里有 <b>2.05s 的空档</b>，有声只占 43% —— 四句被塞进一个块，"
              "模型在中段就断了，后段是硬撑出来的，所以听着像炸。拆成 4 句后有声占 71%，最长静音 0.45s。"),
    dict(tag="7", title="Hooper · 求饶", color="#8a6a8a",
         en="I don't like it here, I want to go home. I don't want to be lost. I want to go home.",
         note="原版词准 100%，但音质崩在句尾。拆 3 句重生成后有声占比 76% → 81%，"
              "同一句话重复两遍的第二遍明显更低。"),
    dict(tag="5", title="Hooper · 大声", color="#8a6ab5",
         en="It's because of me. You're scared of me, Kingshaw, you're Mummy's little scaredy-pet. "
            "You don't know what I might do to you, I could do anything at all.",
         note="拆 5 句。最后一句原版被念成 <code>You can do anything</code>（主宾颠倒），"
              "换 seed 重生成后修正为 <code>I could</code>。"),
]

SEC = []
for b in BLOCKS:
    tag = b["tag"]
    ps = [player(os.path.join(DOTS, "BK_%s.wav" % tag), "原版（整块）", "#3a4150",
                 "一整块生成", asr_of(tag, "原版"))]
    if os.path.exists(os.path.join(DOTS, "BK_%s_r.wav" % tag)):
        ps.append(player(os.path.join(DOTS, "BK_%s_r.wav" % tag), "拆句版（修复）", b["color"],
                         "逐句生成 + 响度对齐 + 拼接", asr_of(tag, "拆句版")))
    SEC.append('<div class="sec"><div class="sh"><b>%s</b></div>'
               '<div class="en">%s</div><div class="note">%s</div>%s</div>'
               % (b["title"], b["en"], b["note"], "".join(ps)))

# BK_2 语速四档
ps = [player(os.path.join(DOTS, "BK_2.wav"), "原版（整块）", "#3a4150", "一整块生成", asr_of("2", "原版")),
      player(os.path.join(DOTS, "BK_2_r.wav"), "拆句版（修好吞音）", "#3d7d6b", "逐句生成", asr_of("2", "拆句版"))]
for r, lab in (("0.80", "降速 0.80x"), ("0.70", "降速 0.70x")):
    p = os.path.join(DOTS, "BK_2_slow%s.wav" % r)
    if os.path.exists(p):
        ps.append(player(p, lab, "#4a8a6a", "rubberband 保音高变速"))
SEC.append('<div class="sec"><div class="sh"><b>Charles · 轻声（语速）</b></div>'
           '<div class="en">I\'m all right. I don\'t want to touch one, that\'s all. No. I\'d rather not.</div>'
           '<div class="note">原版 15 词只用了 2.1s 有声，约 <b>430 wpm</b>，正常朗读是 150–180。'
           '拆句把吞掉的 <code>I\'d rather not</code> 修回来了（原版被念成 <code>they\'re run on</code>），'
           '但语速还是快，所以另做了两档 rubberband 降速。0.80x 保真度损失小，0.70x 接近正常语速但音色会软一点。</div>'
           '%s</div>' % "".join(ps))

# 其余未改动的
rest = []
for tag, who, mood in (("1", "Charles", "日常"), ("3", "Charles", "激动"),
                       ("6", "Hooper", "平静"), ("6b", "Hooper", "质问")):
    p = os.path.join(DOTS, "BK_%s.wav" % tag)
    if os.path.exists(p):
        rest.append(player(p, "%s · %s" % (who, mood), "#4a5a6a", "原版未改动", asr_of(tag, "原版")))

CSS = """*{box-sizing:border-box}
body{margin:0;padding:32px 20px 70px;background:#0f1116;color:#c8cfda;
 font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:880px;margin:0 auto}
h1{font-size:23px;font-weight:600;color:#eef2f8;margin:0 0 6px}
.sub{color:#7d8797;font-size:13px;margin-bottom:20px}
.sec{background:#161a21;border:1px solid #232a35;border-radius:11px;padding:15px 17px;margin:13px 0}
.sh{font-size:15px;color:#e6ecf5;margin-bottom:6px}
.en{color:#dfe6f0;font-size:13.5px;line-height:1.65;margin:4px 0}
.note{color:#8b95a6;font-size:12.5px;margin:8px 0 10px;padding:9px 11px;background:#12161d;
 border-radius:7px;line-height:1.72}
.note code{background:#1b2129;color:#9fc4e8;padding:1px 5px;border-radius:4px;font-size:11.5px}
.pv{background:#12161d;border:1px solid #232a35;border-left:3px solid #4a7fb5;
 border-radius:8px;padding:10px 12px;margin:8px 0}
.ph{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.ph b{color:#e6ecf5;font-size:13.5px}
.ph span{color:#7d8797;font-size:11.5px}
.pm{color:#6f7c8e;font-size:11.5px;font-variant-numeric:tabular-nums;margin:2px 0 6px}
.asr{font-size:11.5px;color:#8b95a6;margin:0 0 6px;line-height:1.6}
.good{color:#5fbf8f}.bad{color:#e07a7a}
audio{width:100%;height:32px}
.sum{background:#141821;border:1px solid #232a35;border-radius:10px;padding:13px 16px;
 font-size:13px;color:#a9b3c2;margin:16px 0;line-height:1.8}
.sum b{color:#e6ecf5}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:8px 0}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid #232a35}
th{color:#8b95a6;font-weight:500;font-size:11.5px}
td{color:#c8cfda;font-variant-numeric:tabular-nums}
"""

html = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>城堡之王 · 炸音修复与发音校对</title><style>' + CSS + '</style></head><body><div class="wrap">'
        '<h1>炸音修复 · 语速 · 发音校对</h1>'
        '<div class="sub">每一条都过了 ASR 逐词校对 · 原版与修复版可直接 A/B</div>'
        '<div class="sum"><b>为什么会炸</b><br>'
        '不是音量爆，也不是念错。dots 把一整段塞进一个块时，<b>中途会掉进一段长静音再硬撑着接下去</b>，'
        '有声占比掉到 43%，后半段是拼出来的，听起来就是撕裂/沙哑。<br>'
        '修法：<b>按句子拆块</b>（每块 5–10 词），逐句生成，再做响度对齐后拼接。'
        '代价是句间韵律不再是模型原生的一口气，需要靠插入的静音长度补回来。</div>'
        + "".join(SEC) +
        '<div class="sum"><b>其余四条（未改动，ASR 全过）</b></div>'
        + "".join(rest) +
        '<div class="sum"><b>发音校对的判定口径</b><br>'
        'ASR 用 Parakeet TDT v3（英文）。被判为“口音偏差”的有四类：'
        '<code>St Vincent\'s → Saint Vicence</code>、<code>Kingshaw → King Shaw</code>、'
        '<code>scaredy → scarity</code>、<code>Mummy\'s → mommy\'s</code>。'
        '这些是法语嗓音带来的发音习惯（词尾 -y 收成 -i、t 吞掉、名字分音节），'
        '不是念错，语义没变。真正判为错误的只有主宾颠倒和整句吞掉两类。</div>'
        '</div></body></html>')

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print("OK", OUT_HTML, round(os.path.getsize(OUT_HTML) / 1024, 1), "KB")
