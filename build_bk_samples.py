# -*- coding: utf-8 -*-
"""当前全部可听示例 + 声纹对照。"""
import base64
import os
import subprocess

import numpy as np
import parselmouth
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
DOTS = "G:/_setup/dots_edit2"
EXP = "G:/_setup/dots_edit2/_exp"
TMP = "G:/_setup/_bkfix_audio"
OUT_HTML = "G:/_setup/castle_book_samples.html"
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
    v = db > -45
    mx = cur = 0
    for x in v:
        cur = 0 if x else cur + 1
        mx = max(mx, cur)
    return dict(dur=len(a) / sr, ratio=100 * v.mean(), gap=mx * 0.01,
                peak=float(np.max(np.abs(a))), f0=f0(p))


def mp3(p):
    m = os.path.join(TMP, os.path.basename(p) + ".mp3")
    if not os.path.exists(m):
        subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                        "-codec:a", "libmp3lame", "-b:a", "80k", "-ar", "22050", "-ac", "1", m],
                       capture_output=True)
    with open(m, "rb") as f:
        return base64.b64encode(f.read()).decode()


def row(path, label, spk, note, color):
    if not os.path.exists(path):
        return ""
    s = stats(path)
    cls = "good" if spk >= 0.78 else ("mid" if spk >= 0.7 else "bad")
    return ('<div class="pv" style="border-left-color:%s">'
            '<div class="ph"><b>%s</b><span class="spk %s">声纹 %.3f</span></div>'
            '<div class="pm">%.2fs · 有声 %.0f%% · 最长静音 %.2fs · F0 %.0f Hz · peak %.2f</div>'
            '<div class="nt">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (color, label, cls, spk, s["dur"], s["ratio"], s["gap"], s["f0"], s["peak"], note, mp3(path)))


GROUPS = [
    ("Charles · 日常", "#4a7fb5",
     "It's called St Vincent's. That's nothing. It's only an old house. I'm all right.",
     [("BK_1.wav", "原版（用 normal 参考）", 0.716, "整块生成，6.24s"),
      (EXP + "/E1_tight.wav", "紧凑参考版", 0.694, "参考去掉 0.35s 拼接静音，反而略降")]),
    ("Charles · 生气", "#b54a4a",
     "But I wouldn't go on whining, like you. Scaredy Hooper. You are scared. You're scared now.",
     [("BK_4.wav", "原版（用 angry 参考）", 0.553, "10.08s 里有 2.05s 空档，有声仅 43% —— 你说的「炸」就是这里"),
      ("BK_4_r.wav", "拆句版（还是 angry 参考）", 0.636, "炸音修好了，但音色没救回来"),
      (EXP + "/E4_whole.wav", "中性参考 · 整块", 0.758, "换 normal 参考、不拆句，声纹 +0.21"),
      ("BK_4_nref.wav", "中性参考 · 拆句", 0.768, "拆句 + 中性参考，两者兼得")]),
    ("Charles · 轻声", "#3d7d6b",
     "I'm all right. I don't want to touch one, that's all. No. I'd rather not.",
     [("BK_2.wav", "原版", 0.692, "3.84s 说 15 词，约 430 wpm；末句 I'd rather not 被吞成 they're run on"),
      ("BK_2_r.wav", "拆句版（吞音修好）", 0.619, "内容全对了，但音色掉 0.07"),
      ("BK_2_slow0.80.wav", "拆句 + 降速 0.80x", 0.582, "rubberband 保音高"),
      ("BK_2_slow0.70.wav", "拆句 + 降速 0.70x", 0.544, "179 wpm，接近正常语速，音色再掉一档")]),
    ("Charles · 激动", "#b5734a",
     "I'm a bowman, I'm the head warrior of this castle. If I shoot an arrow, I can kill you.",
     [("BK_3.wav", "原版", 0.777, "这条本来就稳，ASR 100%")]),
    ("Hooper · 大声", "#8a6ab5",
     "It's because of me. You're scared of me, Kingshaw, you're Mummy's little scaredy-pet. "
     "You don't know what I might do to you, I could do anything at all.",
     [("BK_5.wav", "原版", 0.801, "全库唯一原版就过 0.8 的"),
      ("BK_5_r.wav", "拆句版", 0.828, "拆句反而更高；最后一句换 seed 修了 I could → You can 的主宾颠倒")]),
    ("Hooper · 平静", "#6a7f8a",
     "I'm King of the Castle! You'd better come down, show-off, if you fall you'll split your head open.",
     [("BK_6.wav", "原版", 0.795, "ASR 100%")]),
    ("Hooper · 质问", "#7a6f5a",
     "Open one of the cases, then. I'll let you. Why not? Scaredy-baby, scared of a moth! Pick one up.",
     [("BK_6b.wav", "原版（用 scold 参考）", 0.635, "ASR 95%"),
      (EXP + "/E6b_calmref.wav", "中性参考", 0.797, "换 calm 参考，声纹 +0.16")]),
    ("Hooper · 求饶", "#8a6a8a",
     "I don't like it here, I want to go home. I don't want to be lost. I want to go home.",
     [("BK_7.wav", "原版（用 begging 参考）", 0.352, "ASR 100%，但音色完全不像 —— 参考是尖叫，输出是低落，音高差 59Hz"),
      ("BK_7_r.wav", "拆句版（还是 begging 参考）", 0.431, "修了炸音，音色还是不像"),
      (EXP + "/E7_calmref.wav", "中性参考", 0.755, "换 calm 参考，声纹 +0.40")]),
    ("多情绪长块实验", "#5a6a7a",
     "日常 4 句 + 生气 4 句，一次生成，emo 只包后 4 句",
     [(EXP + "/E14_multi.wav", "12.48s 长块 + emo 局部", 0.718, "想靠长输出锚住音色，结果没提升，而且 peak 冲到 1.00 削波")]),
]

CSS = """*{box-sizing:border-box}
body{margin:0;padding:30px 20px 70px;background:#0f1116;color:#c8cfda;
 font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:23px;font-weight:600;color:#eef2f8;margin:0 0 5px}
.sub{color:#7d8797;font-size:13px;margin-bottom:18px}
.sec{background:#161a21;border:1px solid #232a35;border-radius:11px;padding:14px 16px;margin:12px 0}
.sh{font-size:15px;color:#e6ecf5;margin-bottom:4px}
.en{color:#93a0b2;font-size:12.5px;line-height:1.6;margin-bottom:9px;font-style:italic}
.pv{background:#12161d;border:1px solid #232a35;border-left:3px solid #4a7fb5;
 border-radius:8px;padding:9px 12px;margin:7px 0}
.ph{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.ph b{color:#e6ecf5;font-size:13.5px}
.spk{font-size:11.5px;font-variant-numeric:tabular-nums;border-radius:20px;padding:1px 8px}
.spk.good{background:#173325;color:#6fcf9a}
.spk.mid{background:#332b17;color:#d4b062}
.spk.bad{background:#331b1b;color:#e08a8a}
.pm{color:#6f7c8e;font-size:11.5px;font-variant-numeric:tabular-nums;margin:2px 0 4px}
.nt{color:#8b95a6;font-size:12px;margin-bottom:6px;line-height:1.55}
audio{width:100%;height:30px}
.sum{background:#141821;border:1px solid #232a35;border-radius:10px;padding:13px 16px;
 font-size:13px;color:#a9b3c2;margin:14px 0;line-height:1.8}
.sum b{color:#e6ecf5}
.sum code{background:#1b2129;color:#9fc4e8;padding:1px 5px;border-radius:4px;font-size:11.5px}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:6px 0}
th,td{text-align:left;padding:4px 8px;border-bottom:1px solid #232a35}
th{color:#8b95a6;font-weight:500;font-size:11px}
td{color:#c8cfda;font-variant-numeric:tabular-nums}
"""

secs = []
for title, color, en, items in GROUPS:
    rows = "".join(row(os.path.join(DOTS, f) if not f.startswith("/") else f, lab, spk, nt, color)
                   for f, lab, spk, nt in items)
    if rows:
        secs.append('<div class="sec"><div class="sh" style="color:%s">%s</div>'
                    '<div class="en">%s</div>%s</div>' % (color, title, en, rows))

TBL = """<table><tr><th>条</th><th>情绪参考</th><th>中性参考</th><th>变化</th></tr>
<tr><td>Charles 日常</td><td>0.716</td><td>—</td><td>—</td></tr>
<tr><td>Charles 生气</td><td>0.553</td><td><b>0.758–0.768</b></td><td class="g">+0.21</td></tr>
<tr><td>Charles 轻声</td><td>0.692</td><td>—</td><td>—</td></tr>
<tr><td>Charles 激动</td><td>0.777</td><td>—</td><td>—</td></tr>
<tr><td>Hooper 大声</td><td>0.801</td><td>—</td><td>—</td></tr>
<tr><td>Hooper 平静</td><td>0.795</td><td>—</td><td>—</td></tr>
<tr><td>Hooper 质问</td><td>0.635</td><td><b>0.797</b></td><td class="g">+0.16</td></tr>
<tr><td>Hooper 求饶</td><td>0.352</td><td><b>0.755</b></td><td class="g">+0.40</td></tr>
</table>"""

html = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>城堡之王 · 音色示例（全部可听）</title><style>' + CSS + '</style></head><body><div class="wrap">'
        '<h1>当前所有示例 · 按声纹排序</h1>'
        '<div class="sub">声纹 = CAM++ 余弦相似度，对拼接长参考测 · 0.75 以上为「同一人」档</div>'
        '<div class="sum"><b>一句话结论</b><br>'
        '拼接参考一直在用（每组 8–13.6s）。声纹上不去不是因为参考短，是因为<b>每条用了不同情绪的参考</b>。'
        '愤怒参考里的声道是喊叫状态，生成出来的和日常参考生成的<b>互比只有 0.21</b>，根本不是同一个人。<br>'
        '把每个角色统一到一个<b>中性参考</b>后，生气从 0.553 升到 0.768、求饶从 0.352 升到 0.755。' + TBL + '</div>'
        + "".join(secs) +
        '<div class="sum"><b>还没解决的</b><br>'
        '① Charles 组整体在 0.69–0.77，比 Hooper 组低一档，参考本身（8 片拼接、片间静音 0.35s）还有优化空间。<br>'
        '② 单条输出 3–5s 时声纹波动大（同一参考同一 seed，不同文本能从 0.69 跳到 0.81），长块也压不住，'
        '12.48s 那次反而掉到 0.718 还削波。<br>'
        '③ 降速是纯后期，rubberband 0.70x 会把音色再拉低 0.15，和你「优先保音色」的要求冲突，所以默认不降。</div>'
        '</div></body></html>')

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print("OK", OUT_HTML, round(os.path.getsize(OUT_HTML) / 1024 / 1024, 2), "MB")
