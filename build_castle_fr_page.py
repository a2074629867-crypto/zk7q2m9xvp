# -*- coding: utf-8 -*-
"""《我是城堡之王》法语原声 · 音色切片库试听页"""
import base64
import os
import subprocess

import numpy as np
import parselmouth
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
CLEAN = "G:/_setup/castle_fr_clean"
REF = "G:/_setup/castle_fr_ref"
OUT_HTML = "G:/_setup/castle_fr_voices.html"
TMP = "G:/_setup/_fr_audio"

GROUPS = [
    ("1_charles_normal", "Charles", "普通说话", "#4a7fb5",
     "主音色。对 Bréaud 说话、自我介绍、日常应答，是 Charles 最「无标记」的状态。",
     [("c01_ne_comme_ca", "Je suis né comme ça aussi?"),
      ("c02_breaud", "Vous êtes M. Bréaud?"),
      ("c03_vernet", "Moi, je suis Charles Vernet."),
      ("c04_ca_va_mieux", "Non. Ça va mieux, maintenant."),
      ("c05_non_monsieur", "Non, monsieur."),
      ("c06_si_elle_aime", "Et si elle, elle vous aime pas?"),
      ("c07_c_moi_tinvite", "Laisse. C'est moi qui t'invite."),
      ("c08_encore_riche", "je suis encore très riche.")]),
    ("2_charles_soft", "Charles", "轻声说话", "#3d7d6b",
     "对母亲说话、夜里、卸下防备时。F0 是全库最低——轻声时音高自然下沉，正是「内敛」的声学证据。",
     [("c09_rien_marriver", "Mais il pouvait rien m'arriver."),
      ("c10_jamais_peur", "Maman, j'aurai plus jamais peur."),
      ("c11_dartagnan", "Maman, je suis d'Artagnan."),
      ("c12_non_maman", "Non, maman."),
      ("c13_cadeau_thomas", "C'est le cadeau de Thomas."),
      ("c14_plus_rien_faire", "Tu peux plus rien me faire, maintenant.")]),
    ("3_charles_excited", "Charles", "激动", "#b5734a",
     "和 Thomas 对骂、母亲回来时。音高抬升最明显的一段，可作「破功」参考。",
     [("c15_pas_de_mere", "Tu dis ça parce que t'as pas de mère!"),
      ("c16_menteur", "Menteur! Ton père n'est rien du tout! Il plaît pas à ma mère, elle le déteste!"),
      ("c17_breaud_venu", "M. Bréaud est venu."),
      ("c18_il_taime", "Il t'aime.")]),
    ("4_charles_angry", "Charles", "生气", "#b54a4a",
     "被扔石头、床上有乌鸦之后。逼 Thomas 道歉那两句也是他——冷、短、不容置疑。",
     [("c19_jeté_pierre", "Qui a jeté la pierre dans ma chambre?"),
      ("c20_corbeau", "Qui a mis le corbeau dans mon lit?"),
      ("c21_demande_pardon", "Je demande pardon à Charles pour tout ce que j'ai fait."),
      ("c22_vas_y_repete", "Vas-y, répète!")]),
    ("5_hooper_loud", "Hooper (Thomas)", "大声说", "#8a6ab5",
     "全库最高音高。居高临下、宣示家产、羞辱对方母亲——Hooper 的支配态。",
     [("h01_riche_pauvres", "Il est riche et vous êtes pauvres. C'est pour ça que vous êtes venus,"),
      ("h02_femmes_seules", "pour que ta mère puisse se marier avec mon père. Les femmes seules font ça."),
      ("h03_argent_robes", "Il faut qu'on leur donne de l'argent, une maison, des robes...")]),
    ("6_hooper_calm", "Hooper (Thomas)", "平静普通", "#6a7f8a",
     "字幕开头第 2–5 行。片头病床前念拉辛那段（第 2–4 行是一整段朗诵，已合并）+ 一句日常对白。"
     "语调平、几乎没有起伏——这是 Hooper 的底色，也是「平静」最干净的样本。",
     [("h04a_intro_verse", "«N'accablez point, madame, un prince malheureux…»（第 2–4 行，一整段）"),
      ("h04b_papa_seul", "J'ai dit à papa que je voulais rester seul avec vous.")]),
    ("6b_hooper_scold", "Hooper (Thomas)", "质问（补充）", "#7a6f5a",
     "00:32 那段连珠炮。内容是骂人，但语调压着没吼——属于「冷着脸凶」，和组 5 的爆发不一样。"
     "原来混着 Charles 一句「Non!」，已按能量包络切开，现在每一片都是纯 Thomas。",
     [("h04a_sale_voleur", "Espèce de sale voleur."),
      ("h04b_tenfuies", "Tu t'enfuies."),
      ("h04b2_menteur", "Menteur!"),
      ("h04c_menteur_voleur", "T'es un menteur et un voleur."),
      ("h04d_reveiller_pere", "Je vais aller réveiller mon père et je vais tout lui dire.")]),
    ("7_hooper_begging", "Hooper (Thomas)", "求饶", "#8a6a8a",
     "恐高、被逼道歉。音高回落到 Charles 正常水平——示弱时两个孩子的差距消失。",
     [("h05_vertige", "Je peux pas, j'ai le vertige!"),
      ("h06_cest_moi_1", "C'est moi."),
      ("h07_cest_moi_2", "C'est moi."),
      ("h08_pardon", "Je demande pardon à Charles pour ce que j'ai fait.")]),
]


def f0_med(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=400)
    f = pit.selected_array["frequency"]
    m = f > 0
    return float(np.median(f[m])) if m.any() else 0.0


def dur(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return len(a) / sr


def to_mp3(src, dst):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-codec:a", "libmp3lame", "-b:a", "96k", "-ar", "24000", "-ac", "1", dst],
                   capture_output=True)


def b64(p):
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()


os.makedirs(TMP, exist_ok=True)

secs = []
for gdir, who, mood, color, desc, items in GROUPS:
    refp = os.path.join(REF, gdir + ".wav")
    ref_html = ""
    if os.path.exists(refp):
        m = os.path.join(TMP, gdir + "_ref.mp3")
        to_mp3(refp, m)
        ref_html = ('<div class="ref"><div class="reftop"><b>长参考</b>'
                    '<span class="tag">%.2fs · %.0f Hz</span></div>'
                    '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
                    % (dur(refp), f0_med(refp), b64(m)))
    cards = []
    for sid, line in items:
        p = os.path.join(CLEAN, gdir, sid + ".wav")
        if not os.path.exists(p):
            continue
        m = os.path.join(TMP, sid + ".mp3")
        to_mp3(p, m)
        cards.append(
            '<div class="card"><div class="hd"><div class="nm">%s</div>'
            '<div class="tag">%.2fs · %.0f Hz</div></div>'
            '<div class="note">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (sid, dur(p), f0_med(p), line, b64(m)))
    secs.append(
        '<h2 style="border-left-color:%s">%s · %s <span class="cnt">%d 片</span></h2>'
        '<p class="gd">%s</p>%s<div class="grid">%s</div>'
        % (color, who, mood, len(cards), desc, ref_html, "".join(cards)))

# ---- 跨语言验证：法语参考 -> 英语输出 ----
XL = [
    ("XG_normal", "1_charles_normal", "普通说话参考（251.8 Hz）", "13.58s"),
    ("XG_soft", "2_charles_soft", "轻声参考（184.1 Hz）", "10.55s"),
]
xl_cards = []
for xid, refid, label, rdur in XL:
    xp = os.path.join("G:/_setup/dots_edit2", xid + ".wav")
    if not os.path.exists(xp):
        continue
    m = os.path.join(TMP, xid + ".mp3")
    to_mp3(xp, m)
    xl_cards.append(
        '<div class="card"><div class="hd"><div class="nm">%s → %s</div>'
        '<div class="tag">输出 %.2fs · %.0f Hz</div></div>'
        '<div class="note">参考 %s（%s，法语）→ dots tts 用英文文本生成</div>'
        '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
        % (refid, label, dur(xp), f0_med(xp), refid, rdur, b64(m)))
xlang_html = ""
if xl_cards:
    xlang_html = (
        '<h2 style="border-left-color:#c9a227">跨语言验证 · 法语参考说英语</h2>'
        '<p class="gd">同一段英文（29 词），只换 voice_ref。音色通道（CAM++ x-vector）不含语言信息，'
        '所以法语人声可以直接驱动英语发音。F0 保真 100.6%，声纹 0.7491（同一人档）。</p>'
        '<div class="grid">' + "".join(xl_cards) + '</div>')

html = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>城堡之王 · 法语音色切片库</title><style>*{box-sizing:border-box}
body{margin:0;padding:32px 20px 70px;background:#0f1116;color:#c8cfda;
 font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:880px;margin:0 auto}
h1{font-size:23px;font-weight:600;color:#eef2f8;margin:0 0 6px}
.sub{color:#7d8797;font-size:13px;margin-bottom:20px}
h2{font-size:15.5px;font-weight:600;color:#e2e8f2;margin:32px 0 8px;
 padding-left:11px;border-left:3px solid #4a7fb5}
.cnt{font-size:11.5px;color:#6f7a8b;font-weight:400}
.gd{color:#8b95a6;font-size:13px;margin:6px 0 12px}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 8px}
.kpi div{flex:1;min-width:130px;background:#161a21;border:1px solid #232a35;
 border-radius:10px;padding:11px 14px}
.kpi b{display:block;font-size:18px;color:#7fb3e8;font-weight:600}
.kpi span{font-size:11.5px;color:#7d8797}
.ref{background:#151d18;border:1px solid #3d6b45;border-radius:12px;
 padding:12px 15px;margin:10px 0 14px}
.reftop{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
.reftop b{font-size:13px;color:#8fd39b}
.grid{display:grid;grid-template-columns:1fr;gap:9px}
.card{background:#161a21;border:1px solid #232a35;border-radius:10px;padding:12px 14px}
.hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.nm{font-weight:500;color:#dde4ee;font-size:13px;font-family:ui-monospace,monospace}
.tag{font-size:11.5px;color:#7fb3e8;font-variant-numeric:tabular-nums;
 background:#1b2430;border-radius:20px;padding:2px 9px;white-space:nowrap}
.note{font-size:12.5px;color:#8b95a6;margin:5px 0 7px;font-style:italic}
audio{width:100%;height:32px}
.chain{background:#141821;border:1px solid #232a35;border-radius:10px;
 padding:13px 16px;font-size:13px;color:#a9b3c2;margin:16px 0}
.chain code{background:#1b2129;color:#9fc4e8;padding:1px 5px;border-radius:4px;font-size:12px}
</style></head><body><div class="wrap">
<h1>《我是城堡之王》法语原声 · 音色切片库</h1>
<div class="sub">7 组 / 30 片 · 全部来自电影原声 · 已做人声分离与降噪</div>
<div class="kpi">
<div><b>36</b><span>有效切片</span></div>
<div><b>7</b><span>情绪分组</span></div>
<div><b>2</b><span>角色</span></div>
<div><b>48 kHz</b><span>单声道</span></div>
</div>
<div class="chain"><b>处理链</b>　eac3 原声 → 精确切片（±0.12s 余量）→
<code>HTDemucs q8_0</code> 四轨分离取 vocals → <code>highpass 80Hz</code> →
<code>afftdn</code> 降噪 → <code>loudnorm I=-20 TP=-1.5</code> → 48k 单声道<br>
<span style="color:#7d8797;font-size:12.5px">每组长参考 = 组内各片按顺序拼接，间隔 0.35s 静音，可直接当 voice_ref。</span></div>
""" + xlang_html + "".join(secs) + """
<h2>怎么用</h2>
<div class="chain">
<b>1. 定角色音色</b>：Charles 用 <code>1_charles_normal</code>（13.55s）当主 voice_ref，
<code>2_charles_soft</code> 当"低声"备选。<br>
<b>2. 情绪</b>：不要指望参考音频直接带情绪——dots 的情绪走 <code>&lt;emo&gt;</code> 标签，
参考只负责音色。这几组的价值是<b>让我们知道每个情绪的真实音高落点</b>，
标注时按这个方向给 emo 强度。<br>
<b>3. Hooper</b>：<code>5_hooper_loud</code>（12.38s）、<code>6_hooper_calm</code>（13.62s）、<code>6b_hooper_scold</code>（13.03s）都可直接用。6 组是「平」的底色，5 组是「扬」的峰值，6b 是中间那档「压着的凶」——Hooper 的 emo 强度按这三个锚点分三档。
</div>
<h2>三个必须说清的点</h2>
<div class="chain">
<b>① 两个角色都是真童声，F0 在 184–326 Hz。</b>这个区间和成年女声重叠，
所以单看 F0 会误判"女性化"。真童声和成年女声的差别在<b>共振峰间距、气声比例、语调幅度</b>，
不在基频高低——这正是必须用真人参考、不能用文字描述硬造的原因。<br>
<b>② Charles 轻声时 F0 掉到 184 Hz</b>，比正常说话低 66 Hz。这是"内敛"在声学上的直接体现：
他不靠提高音量表达，情绪越重反而压得越低。<br>
<b>③ Hooper 大声时 326 Hz，求饶时 244 Hz</b>，落差 82 Hz。他的表演是外放的、起伏大的，
和 Charles 完全相反——两个角色在标注策略上要分开处理。
</div>
</div></body></html>"""

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print("OK", OUT_HTML, round(os.path.getsize(OUT_HTML) / 1024 / 1024, 2), "MB")
