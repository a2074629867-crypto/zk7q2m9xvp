# -*- coding: utf-8 -*-
"""build_cast_page.py —— 《我是城堡之王》人物表（姓氏/名字/称谓/关系/音色/情感）

统计数字来自 castle_characters.json；关系与音色建议为人工整理。
输出 G:/_setup/castle_cast.html + castle_cast.json
"""
import json

D = json.load(open("G:/_setup/castle_characters.json", encoding="utf-8"))

# canon -> (姓, 名, 称谓形式, 中文关系, 音色, 情感弧线, 参考方向)
EXTRA = {
    "Edmund Hooper": (
        "Hooper（书中主要用姓）", "Edmund（父亲叫他）", "Master Hooper（正式场合）",
        "Joseph 与 Ellen 之子 · Warings 继承人 · 11 岁 · 与 Charles 敌对",
        "11 岁男孩，清亮偏冷，中高音区，音色干净无沙，句尾收得利落",
        "礼貌客套 → 阴冷试探 → 得意施虐（几乎不外露情绪，靠停顿施压）",
        "少年男声 · 冷"),
    "Charles Kingshaw": (
        "Kingshaw（书中主要用姓）", "Charles（母亲与 Hooper 先生用）", "—",
        "Helena 之子 · 父亲已故 · 11 岁 · Edmund 的受害者",
        "11 岁男孩，偏软偏低，气息弱，尾音下坠，紧张时气口变浅",
        "紧张 → 恐惧 → 短暂松弛（Fielding 段）→ 绝望（结尾）",
        "少年男声 · 软"),
    "Joseph Hooper": (
        "Mr Hooper（书中主要）", "Joseph", "Mr Hooper / Mr Joseph Hooper",
        "Edmund 之父 · Ellen 的鳏夫 · Warings 主人 · 中年商人",
        "中年男，中低音，平板发干，鼻腔共鸣重，语速均匀无起伏",
        "疏离 → 客套 → 疲惫（对儿子始终隔一层）",
        "中年男声 · 干"),
    "Helena Kingshaw": (
        "Mrs Kingshaw（书中主要）", "Helena", "Mrs Kingshaw / Mrs Helena Kingshaw",
        "Charles 之母 · 寡妇 · Warings 非正式管家 · 后与 Joseph 订婚",
        "中年女，中音偏亮，带讨好和焦虑的轻微颤动，笑的时候音更高",
        "温柔 → 焦虑 → 自顾（把儿子推到一边）→ 盲目（结尾安慰 Edmund）",
        "中年女声 · 亮"),
    "Anthony Fielding": (
        "Fielding（Kingshaw 叫他姓）", "Anthony（母亲与 Helena 用）", "—",
        "本地农家男孩 · 与 Charles 同龄 · Charles 唯一的朋友",
        "11 岁男孩，结实明亮，语速快，尾音上扬，带一点乡音",
        "爽朗 → 稳 → 务实（看小牛出生那段是全书的呼吸口）",
        "少年男声 · 亮"),
    "Alice Boland": (
        "Mrs Boland（书中主要）", "Alice", "Mrs Boland / Mrs Alice Boland",
        "Warings 的管家兼清洁工 · 白天来，晚上不在 · 唯一从头待到尾的人",
        "中老年女，低音、干、务实，语速稳，不带感情色彩",
        "务实 → 冷淡 → 旁观（她最早看出 Edmund 不对劲）",
        "中老年女声 · 干"),
    "Joseph Hooper Sr.": (
        "老 Hooper", "Joseph（同名）", "Mr Hooper（旧称）",
        "Joseph 之父 · Edmund 的祖父 · 开篇病逝 · 白手起家的商人",
        "老年男，气声、沙哑、极弱，句子断续",
        "濒死（全程昏迷，只有呼吸声）",
        "老年男声 · 虚弱"),
    "Ellen Hooper": (
        "Mrs Hooper", "Ellen", "—",
        "Joseph 的亡妻 · Edmund 之母 · 六年前去世 · 仅被提及",
        "无台词（只在回忆里出现）",
        "—",
        "不需要"),
    "Miss Mellitt": (
        "Miss Mellitt", "—", "Miss Mellitt",
        "伦敦私人旅馆的老妇人 · Charles 和母亲住旅馆时遇到 · Charles 怕她",
        "老年女，尖细、压着嗓子，语速慢，句子短",
        "古怪 → 压迫（童年阴影类角色）",
        "老年女声 · 尖"),
    "Enid Tyson": (
        "Tyson", "Enid", "Mrs Enid Tyson",
        "Helena 的朋友 · 离异（不是寡妇）· 只在电话里出现",
        "中年女，热络、语速快、音偏高，话多",
        "热络 → 八卦（给 Helena 提供「另一个世界」的对照）",
        "中年女声 · 热络"),
    "Fenwick": ("Fenwick", "—", "—", "寄宿学校同学 · 嘲笑过 Kingshaw 拔牙后哭",
                "少年男，中音，带嘲弄的上扬", "嘲弄", "少年男声"),
    "Lesage": ("Lesage", "—", "—", "寄宿学校学长（prefect）· 常差遣 Kingshaw · 让他畏惧",
               "少年男，变声期，压低装成熟", "威压 → 居高临下", "少年男声 · 低"),
    "Crawford": ("Crawford", "—", "—", "学校霸王 · 打过 Kingshaw 一次 · 打所有人",
                 "少年男，粗、响、不修饰", "暴力 → 无理由的攻击", "少年男声 · 粗"),
    "Broughton-Smith": ("Broughton-Smith", "—", "—", "同学 · 膝盖长满疣 · 被送去见医生",
                        "少年男，鼻音重，带委屈", "可怜 → 被围观", "少年男声 · 鼻"),
    "Devereux": ("Devereux", "—", "—", "富家同学 · 暑假去 Norfolk 航海 · 给 Kingshaw 寄明信片",
                 "少年男，明亮、优越、松弛", "优越 → 无忧", "少年男声 · 亮"),
    "Casey": ("Casey", "—", "—", "同学 · 说「They inject you」（打针）",
              "少年男，平、快", "吓唬人", "少年男声"),
    "Gough": ("Gough", "—", "—", "同学 · 哥哥懂「黑魔法」能治疣",
              "少年男，神秘兮兮", "故弄玄虚", "少年男声"),
    "Lynch": ("Lynch", "—", "—", "同学 · 仅与 Devereux 并列提及一次",
              "不需要单独音色", "—", "可复用同学声"),
    "Turville": ("Turville", "—", "—", "Kingshaw 五岁时在露天泳池遇到的男孩 · 激他下水",
                 "少年男，挑衅、轻快", "挑衅 → 看笑话", "少年男声"),
    "Mr Gardner": ("Gardner", "—", "Mr Gardner", "仅提及一次的成年人（与 Devereux、Lynch 并列）",
                   "不需要单独音色", "—", "可复用"),
    "Mr Busby": ("Busby", "—", "Mr Busby", "公园里常坐的长者 · 只有一条腿 · 与 Mr Taylor 总坐一起",
                 "老年男，慢、含糊", "沉默 → 背景", "老年男声"),
    "Mr Taylor": ("Taylor", "—", "Mr Taylor", "公园里常坐的长者 · 与 Mr Busby 总坐一起",
                  "老年男，慢", "背景", "老年男声"),
    "Mrs Fielding": ("Fielding", "—", "Mrs Fielding", "Anthony 的母亲 · 仅提及",
                     "中年女，温和", "背景", "可复用"),
    "Mrs Devereux": ("Devereux", "—", "Mrs Devereux", "Devereux 的母亲 · 写信邀请 Kingshaw 同行",
                     "中年女，客套", "背景", "可复用"),
}

ORDER = {"main": 0, "support": 1, "mentioned": 2, "minor": 3}
KIND_CN = {"main": "主要", "support": "重要配角", "mentioned": "仅提及", "minor": "次要"}

rows = []
for canon, d in D.items():
    ex = EXTRA.get(canon)
    if not ex:
        continue
    rows.append(dict(canon=canon, cn=d["cn"], sex=d["sex"], kind=d["kind"],
                     total=d["total"], nq=d.get("n_quotes", 0), nt=d.get("n_thoughts", 0),
                     chapters=d.get("chapters", []), surname=ex[0], given=ex[1],
                     title=ex[2], rel=ex[3], timbre=ex[4], emo=ex[5], ref=ex[6],
                     quotes=[q["text"] for q in d.get("quotes", [])][:3]))
rows.sort(key=lambda r: (r["sex"] != "M", ORDER[r["kind"]], -r["total"]))

M = [r for r in rows if r["sex"] == "M"]
F = [r for r in rows if r["sex"] == "F"]

json.dump(rows, open("G:/_setup/castle_cast.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)


def card(r):
    q = ""
    if r["quotes"]:
        q = "<div class='q'>" + "<br>".join(
            "“%s”" % x.replace("<", "&lt;")[:110] for x in r["quotes"][:2]) + "</div>"
    kindcls = "k-" + r["kind"]
    return """
<div class="card {sexcls}">
  <div class="hd">
    <div class="nm">{canon}</div>
    <div class="cn">{cn}<span class="tag {kindcls}">{kindcn}</span></div>
  </div>
  <div class="names">
    <div><b>姓</b><span>{surname}</span></div>
    <div><b>名</b><span>{given}</span></div>
    <div><b>称谓</b><span>{title}</span></div>
  </div>
  <div class="rel">{rel}</div>
  <div class="meta">提及 <b>{total}</b> · 台词 <b>{nq}</b> · 内心独白 <b>{nt}</b> · 出场 ch{ch}</div>
  <div class="sec"><b>音色</b>{timbre}<em>{ref}</em></div>
  <div class="sec"><b>情感</b>{emo}</div>
  {q}
</div>""".format(sexcls="male" if r["sex"] == "M" else "female",
                 canon=r["canon"], cn=r["cn"], kindcn=KIND_CN[r["kind"]],
                 kindcls=kindcls, surname=r["surname"], given=r["given"],
                 title=r["title"], rel=r["rel"], total=r["total"], nq=r["nq"],
                 nt=r["nt"], ch=("%d–%d" % (r["chapters"][0], r["chapters"][-1]))
                 if r["chapters"] else "-",
                 timbre=r["timbre"], ref=r["ref"], emo=r["emo"], q=q)


HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>我是城堡之王 · 人物表</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0e1014;color:#e8eaee;font:14.5px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:40px 22px 80px}
h1{font-size:26px;font-weight:650;margin:0 0 6px}
.sub{color:#8b93a1;font-size:13.5px;margin-bottom:26px}
.sub b{color:#e8a33d}
h2{font-size:17px;font-weight:600;margin:38px 0 14px;padding-left:11px;border-left:3px solid #e8a33d}
h2 em{font-style:normal;color:#6f7787;font-size:13px;margin-left:8px;font-weight:400}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-bottom:8px}
.stat{background:#161a21;border:1px solid #232833;border-radius:11px;padding:14px 15px}
.stat .k{font-size:11.5px;color:#7d8593;letter-spacing:.4px}
.stat .v{font-size:24px;font-weight:650;color:#f0b455;margin-top:3px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}
.card{background:#14171d;border:1px solid #222731;border-radius:12px;padding:15px 16px 13px;border-left:3px solid #3a4250}
.card.male{border-left-color:#5f8fa8}
.card.female{border-left-color:#c98b3a}
.hd{margin-bottom:9px}
.nm{font-size:15.5px;font-weight:650;letter-spacing:.2px}
.cn{color:#98a0ae;font-size:13px;margin-top:1px}
.tag{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:20px;margin-left:7px;vertical-align:1px}
.k-main{background:#2b3a48;color:#8fc7e8}
.k-support{background:#3a2f1c;color:#f0b455}
.k-mentioned{background:#262b34;color:#8892a2}
.k-minor{background:#22262e;color:#6f7787}
.names{display:grid;grid-template-columns:1fr;gap:2px;margin:8px 0;font-size:12.8px}
.names div{display:flex;gap:8px}
.names b{color:#6f7787;font-weight:400;min-width:34px;flex:0 0 34px}
.names span{color:#c8d0dc}
.rel{font-size:12.8px;color:#a8b2c0;background:#191d25;border-radius:7px;padding:7px 9px;margin:8px 0}
.meta{font-size:11.8px;color:#6f7787;margin-bottom:8px}
.meta b{color:#c0c8d4;font-weight:600}
.sec{font-size:12.8px;color:#c2cad6;margin:5px 0;line-height:1.55}
.sec b{color:#6f7787;font-weight:400;display:inline-block;min-width:34px}
.sec em{font-style:normal;color:#5f8fa8;font-size:11.5px;margin-left:6px;border:1px solid #2b3a48;border-radius:5px;padding:0 5px}
.card.female .sec em{color:#c98b3a;border-color:#3a2f1c}
.q{margin-top:8px;padding-top:7px;border-top:1px solid #1e232c;font-size:12px;color:#7d8593;font-style:italic;line-height:1.6}
.note{background:#1a1710;border:1px solid #3a2e18;border-left:3px solid #e8a33d;border-radius:9px;padding:12px 15px;margin:14px 0;font-size:13px;color:#c8c0b0}
.note b{color:#f0b455}
table{width:100%;border-collapse:collapse;background:#14171d;border-radius:11px;overflow:hidden;font-size:13px}
th{background:#1b1f27;color:#98a0ae;font-weight:500;font-size:12px;text-align:left;padding:9px 12px}
td{padding:9px 12px;border-top:1px solid #20252e;color:#b8c0cc;vertical-align:top}
tr:hover td{background:#181d25}
.rl{color:#8fc7e8;white-space:nowrap;font-weight:600}
.rl.hot{color:#e07a83}
.rl.good{color:#7fb98a}
.foot{margin-top:46px;padding-top:16px;border-top:1px solid #20252e;color:#5f6775;font-size:12px}
@media(max-width:820px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}}
</style></head><body><div class="wrap">

<h1>我是城堡之王 · 人物表</h1>
<div class="sub">Susan Hill, <i>I'm the King of the Castle</i> (1970) · 全文 18 章 / <b>73,637 词</b> ·
扫描自 <code>reader-app/books/king-of-the-castle.epub</code></div>

<div class="stats">
<div class="stat"><div class="k">角色总数</div><div class="v">{{N}}</div></div>
<div class="stat"><div class="k">男 / 女</div><div class="v">{{MN}} / {{FN}}</div></div>
<div class="stat"><div class="k">主要角色</div><div class="v">{{MAIN}}</div></div>
<div class="stat"><div class="k">有台词</div><div class="v">{{SPK}}</div></div>
</div>

<div class="note"><b>台词数是下限。</b>这本书的对话大量用 <code>he said / she said</code> 归属，
自动统计只能抓住「名字紧邻」的那些；实际开口量远高于表中数字。
<b>提及次数</b>才是可靠的出场权重。</div>

<h2>男 NPC<em>{{MN}} 人</em></h2>
<div class="grid">{{MCARDS}}</div>

<h2>女 NPC<em>{{FN}} 人</em></h2>
<div class="grid">{{FCARDS}}</div>


<h2>人物关系表<em>配音时按「对话对象」分配语气</em></h2>
<table>
<tr><th>关系</th><th>双方</th><th>性质与对配音的影响</th></tr>
<tr><td class="rl">父子</td><td>Joseph ↔ Edmund</td><td>冷淡、客气、互不触碰。Edmund 对父亲几乎不用敬语，Joseph 说话像在办公</td></tr>
<tr><td class="rl">母子</td><td>Helena ↔ Charles</td><td>亲密但母亲自顾。Charles 对母亲说话会突然变软、变小孩</td></tr>
<tr><td class="rl">雇主 → 婚约</td><td>Joseph ↔ Helena</td><td>管家变未婚妻。Helena 对 Joseph 明显抬高音调、加快语速讨好</td></tr>
<tr><td class="rl hot">敌对（主线）</td><td>Edmund ↔ Charles</td><td>全书核心。Edmund 压低声、放慢、留停顿施压；Charles 气口变浅、句子变碎</td></tr>
<tr><td class="rl good">朋友</td><td>Charles ↔ Fielding</td><td>唯一喘口气的关系。两人对话语速最快、最松弛</td></tr>
<tr><td class="rl">雇佣</td><td>Boland → Warings</td><td>白天来晚上走，旁观者。她跟谁都保持距离，语气平</td></tr>
<tr><td class="rl">祖孙</td><td>祖父 ↔ Edmund</td><td>仅开头病床一场，祖父全程昏迷无台词</td></tr>
<tr><td class="rl">夫妻（已故）</td><td>Joseph ↔ Ellen</td><td>六年前去世，只在回忆里被提到，不需要配音</td></tr>
<tr><td class="rl">校园霸凌</td><td>Crawford / Lesage / Broughton-Smith → Charles</td><td>学校线，与 Warings 线平行。Charles 在这条线上更沉默</td></tr>
<tr><td class="rl">母辈朋友</td><td>Helena ↔ Enid Tyson</td><td>只在电话里，Helena 对她会抱怨、会放松</td></tr>
</table>

<h2>配音分配建议</h2>
<div class="note">
<b>必须独立音色的 6 个：</b>Edmund（冷少年）、Kingshaw（软少年）、Joseph Hooper（干中年男）、
Helena（亮中年女）、Fielding（亮少年）、Boland（干中老年女）。<br>
<b>可复用同一少年声的：</b>Fenwick / Lesage / Crawford / Broughton-Smith / Devereux / Casey / Gough / Turville
（同一所寄宿学校，靠语速和语气区分即可）。<br>
<b>可复用同一老年男声的：</b>Mr Busby / Mr Taylor。<br>
<b>不需要配音的：</b>Ellen Hooper（已故）、Joseph Hooper Sr.（昏迷）、Lynch / Mr Gardner（只被提一次）。
</div>

<div class="foot">统计脚本 castle_characters.py · 数据 castle_cast.json · 全文 castle_full.txt</div>
</div></body></html>"""

spk = sum(1 for r in rows if r["nq"] > 0)
HTML = (HTML.replace("{{N}}", str(len(rows)))
            .replace("{{MN}}", str(len(M)))
            .replace("{{FN}}", str(len(F)))
            .replace("{{MAIN}}", str(sum(1 for r in rows if r["kind"] == "main")))
            .replace("{{SPK}}", str(spk))
            .replace("{{MCARDS}}", "".join(card(r) for r in M))
            .replace("{{FCARDS}}", "".join(card(r) for r in F)))

out = "G:/_setup/castle_cast.html"
open(out, "w", encoding="utf-8").write(HTML)
print("写出 %s (%.1f KB) | 角色 %d（男 %d / 女 %d）| 有台词 %d"
      % (out, len(HTML) / 1024, len(rows), len(M), len(F), spk))
