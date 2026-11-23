# -*- coding: utf-8 -*-
"""build_drop_report.py —— 检测项清账：被摘掉的 30 个检测器，哪些真没用、哪些被我误杀。"""
import json
import os

ROOT = "G:/_setup"
R2 = json.load(open(os.path.join(ROOT, "_drop_report.json"), encoding="utf-8"))
A2 = json.load(open(os.path.join(ROOT, "_drop_audit2.json"), encoding="utf-8"))
import statistics as st

# ---------- 主表 ----------
# (编号, 检测器, 该抓什么, 弃用原因, 证据出处, 现状, 本次复测)
ROWS = [
 ("Ⅰ 真没用（物理或统计上限，捞回来也判不准）", None, None, None, None, None, None),
 ("1", "lookahead limiter", "压峰不抽吸", "maxfilt 6ms + 120ms 释放自造增益起伏",
  "§6 全库波峰因数 23dB 时 peak 恰好 −1dBFS，根本不用限幅", "已删", "—"),
 ("2", "Silero VAD", "语音活动检测", "state 维度不匹配，概率恒 0.001",
  "§12.6 本地模型与输入不兼容", "已删", "—"),
 ("3", "`formant=preserved`", "变速保共振峰", "纯 tempo 不改音高时该参数不参与",
  "§5.5 输出 md5 完全相同", "已删", "—"),
 ("4", "WORLD 时间伸缩", "变速保音色", "音色更差且吞字",
  "§5.5 声纹 0.702；\"In Wales\"→\"In rooms\"", "已删", "—"),
 ("5", "`transients=crisp`", "保瞬态", "毁短句起音",
  "§5.5 \"In Wales.\" → \"And well.\"", "已删", "—"),
 ("6", "`pitchq=consistency`", "音高一致", "无改善", "§5.5", "已删", "—"),
 ("7", "词内断裂 `gap_in_word`", "吞字/断裂", "交付版比对照还多，好坏重叠",
  "§18.12 N0219 交付版 4 处 vs 对照更少", "已删", "—"),
 ("8", "词内斜率反转 `f0_rev_per100ms`", "机械感", "好坏重叠", "§18.12", "已删", "—"),
 ("9", "TTSDS2 / MPM 逐条", "韵律自然度", "坏样本离群率反而更低",
  "§18.12 N0219 base 0.047 vs r7 0.037", "已删", "—"),
 ("10", "UTMOSv2", "整体 MOS", "合成集 AUC 0.755 < 四项组合 0.865，加它无收益",
  "§18.16 混池召回 0.68→0.69，在误差内", "已删", "—"),
 ("11", "单条韵律分（TTSDS2 逐条化）", "单条裁决", "噪声大于效应",
  "§18.21 ctl→ctl 抖动 +2.44~+5.32 > 标签效应 −2.61", "已删", "—"),
 ("12", "句首 / 句尾斜率（单条）", "语调走向", "过一遍声码器就变 7 st/s",
  "§18.30 SNR 1.42 / 1.80", "降级为报告列", "✗ AUC 0.60 / 0.52"),
 ("13", "方向反转率 `rev_rate`（单条）", "念经感", "SNR 1.03，跨 seed 差 7.3 st/s",
  "§18.30 无关变换 2.51 vs 对口 2.59", "降级为报告列", "✗ AUC 0.00（方向反）"),
 ("14", "「末段上扬 = 缺陷」", "语调错误", "会误杀所有 yes-no 疑问句",
  "§18.31 应升组只有 50% 真升，两组声学完全重叠", "已删", "—"),
 ("15", "绝对音区 `[170,305]Hz`", "压嗓 / 喊", "童声整批误报",
  "§18.25 男低音 60% 命中；2026-10-30 童声 13/13 全误报", "改相对 ref", "—"),
 ("16", "线性 Hz 判 F0 跳变", "换人", "50Hz 在 200 与 400Hz 处宽严差一倍",
  "§12.5 改 300 cent", "已改 cent", "—"),
 ("17", "`stretch_segments` 分段拉伸", "控语速", "段边界造伪影",
  "§13 NISQA DIS 4.18→1.81（掉 2.4 分）", "已删", "—"),
 ("18", "SCS 固定 3s 窗 + 循环补长", "音色一致性", "全部余弦饱和到 0.944~0.980",
  "§12.4 分辨力归零", "已删", "—"),
 ("19", "簇中心用逐维中位数", "SCS 实现", "512 维中位数≈0，余弦掉到 0.03",
  "§12.4 看起来像全员换人", "已改均值", "—"),
 ("20", "`loc` 用 max", "音高重音", "单个尖峰撑起达标",
  "§18.8 loc_max ≥2.0 有 52/55，p75 只有 31/55", "改 p75 后仍退役", "—"),
 ("21", "`sps` 用 ASR 边界测变化", "时长重音", "ASR 边界含尾随静音，测不出",
  "§18.8", "已删", "—"),
 ("22", "全段长度回归", "自然度分", "把「短」当解释项，真缺陷一起扣掉",
  "§18.15 AUC 0.70→0.56", "只在 <1.2s 用", "—"),
 ("23", "多指标平均融合", "下限筛", "把尾部磨平",
  "§18.16 AUC 0.865→0.940 但召回 0.68→0.61", "改 min 融合", "—"),
 ("24", "换 seed 改 energy_span", "救「太平」", "0 例可救",
  "§18.29 854 对判定一致 99%", "已删", "—"),
 ("25", "停顿 R3（前后段总长）", "停顿长度", "分层后增益为零",
  "§18.34 β 0.204 / r² 0.048", "已退役", "—"),
 ("26", "停顿 R2（句内位置）", "停顿长度", "子集回归无解释力",
  "§18.32 分桶 1.28 倍是样本构成假象", "已退役", "—"),
 ("27", "`drop` / `beat` / `para` 档", "停顿档位", "马修在每个标点都停；para 未验证",
  "§18.34 drop 实测中位 1.53s，三方各判 0~1 条", "已退役", "—"),
 ("28", "关键词正则判情绪分段", "减速段落", "抓不到语义",
  "§18.27 `dead|afraid|cold` 抓不到「父亲刚拒绝他」", "已换 LLM", "—"),
 ("29", "切片 json 的间隙", "停顿数据源", "时间戳量化到 80ms，标点全缺",
  "§18.32 2127 个间隙只有 30 个唯一值", "改 VAD", "—"),
 ("30", "真 take 池的 audio-FAIL 标签", "选型 ground truth", "标签≈「句子短」",
  "§18.15 OK 语音 2.04s vs FAIL 1.10s", "只用于「不乱报」", "—"),

 ("Ⅱ 口径错被误杀（分母塌陷 / 相对阈值 / 没做不变性）", None, None, None, None, None, None),
 ("31", "峰值因数 / 削波检测", "削波破音", "L053 峰值仅 0.34 却也听着炸 ⇒ 判它没用",
  "§12.6 但那是**内部失真**，不是削波", "已删", "✓ AUC 1.00 / SNR 3.39"),
 ("32", "谱平坦度", "气声 / 噪声化", "好坏片段重叠 ⇒ 判它没用",
  "§12.6 原测的是「噪声段 vs 语音段」，不是整条气声化", "已删", "✓ 0.000→0.108"),
 ("33", "HNR 绝对值", "气声", "6.1dB 看着好实际炸 ⇒ 判它没用",
  "§12.6 绝对值不可比", "只留相对塌陷 ≥15dB", "✓ 4.15→1.53dB（弱但方向对）"),
 ("34", "4kHz 高频占比（绝对 50%）", "气流噪声", "短词被 /s/ 占满会误报",
  "§7.6 须限段长 ≥0.5s", "改成比值（又塌陷）", "✓ 0.001→0.159（×159）"),
 ("35", "高频比 `hf_ratio` 裸比值", "毛刺 / 气声", "分母趋零时全失效",
  "§18.15 12 次触发没有一次是真异常", "已修：加绝对下限", "✓ 加下限后可用"),
 ("36", "`voiced` 比（DUR_GAIN_MIN 1.25）", "副词拉长", "低音男声浊音帧抖 ±3 倍",
  "§18.13 零分布 p90 2.20，阈值 1.25 连 p60 都不到", "已删", "—"),
 ("37", "`span` 比（SPAN_GAIN_MIN 1.50）", "副词拉长", "对照 rel 只有 0.34 时比值虚高",
  "§18.17 第 7 次分母塌陷", "改绝对水位 REL_OK 1.40", "—"),
 ("38", "energy_span（21 段按样本等分）", "太平", "min 由静音落在哪段决定",
  "§18.29 同一 take 跨阶段差 22.6dB", "已改语音帧口径", "✗ **仍未修干净**，见下"),
 ("39", "声纹裸余弦单条否决（<0.55 / <0.65）", "换人", "同一句前半 vs 后半只有 0.346",
  "§18.6 同人不同句 p5 = −0.060", "只记录不否决", "—"),
 ("40", "音色阈值跨档比（CAM++ 跨情绪）", "八档音色", "同 ref 不同句 0.344，内容方差主导",
  "§18.32 AUC 0.491 = 随机", "改「档内基线」三取二", "—"),

 ("Ⅲ 有用但只能组级（被我一刀切掉，应该恢复成监控项）", None, None, None, None, None, None),
 ("41", "`span_st` 音高跨度", "念经感 / 压平", "真人个体差 > 组间差 ⇒ 判「够不够起伏」没靶子",
  "§18.30 真人 p05 4.17 ~ p95 16.99，组间差只有 4.26", "只做报告列", "✓ AUC 1.00 / SNR 2.96（判**压平**）"),
 ("42", "`rev_rate` 组级", "念经感", "单条不可判", "§18.29 真人 15.08 vs 我们 12.61",
  "报告列", "✓ 保留（组级）"),
 ("43", "head / tail 斜率 组级", "句首句尾走向", "单条不可判", "§18.29 真人 −2.36/+0.35 vs 我们 −4.48/−2.52",
  "报告列", "✓ 保留（组级）"),
 ("44", "`loc` 轴（音高提升幅度）", "重音", "与人耳 PMOS 相关只有 r=0.30",
  "§18.19/18.20 ProsodyEval 2025", "从判定链移除", "◐ 组级仍有信号（TTSDS2 Pitch +7.31）"),
 ("45", "Prosogram 滑音选择性", "轮廓而非幅度", "我们的选择性比对照还低，不能当闸门",
  "§18.19 真人 +20.2 点，ctl +8.4 > delivered +1.9", "组级进度条", "✓ 保留（组级）"),
 ("46", "TTSDS2 PROSODY 批次分", "批次自然度", "单条不可判，门槛 80 只是地板",
  "§18.21 两批 83.13 / 84.76", "管线前置体检", "✓ 保留（批次）"),
 ("47", "SCS 尾部排序", "音色漂移", "σ 只有 0.08，κ=2 会让 SCS 塌到 0.001",
  "§12.4 不设验收阈值", "只排尾部", "◐ 与档内基线重复"),

 ("Ⅳ 还在跑（没丢，只是换了位置或换了名字）", None, None, None, None, None, None),
 ("48", "NISQA 四维", "断流 / 噪声 / 染色 / 响度", "—", "mt_item_qa.py",
  "✓ 每单元都跑", "—"),
 ("49", "SQUIM-SUBJ", "纯韵律退化", "—", "_nat_guard.py", "✓ 与 NISQA 组 min 融合", "—"),
 ("50", "声纹余弦", "换人", "—", "mt_spk_audit.py", "✓ 记录 + <0.15 才拦", "—"),
 ("51", "F0 / 谱质心 / 谱倾斜", "音色档", "—", "mt_voice_gate.py", "✓ 8 档 3 取 2", "—"),
 ("52", "句内漂移（0.5s 窗）", "句内音色突变", "—", "mt_seg_drift.py", "✓ 0.5s 窗 / 0.25s 步", "—"),
 ("53", "ASR 覆盖率 / 漏词", "吞字", "—", "_gate.py + _asr_norm.py", "✓ 短句更敏感", "—"),
 ("54", "RDR 语速连续性", "接缝语速", "—", "mt_rdr_gate.py", "✓ 插停顿之前", "—"),
 ("55", "energy_span 双向闸门", "太平 / 太陡", "—", "mt_rhythm_gate.py", "✓ 但口径要修（第 38 项）", "—"),
 ("56", "停顿语义（must/opt/no）", "该不该停", "—", "pause_intent.json + mt_pause_cross.py", "✓ 33 条 / 70 处", "—"),
 ("57", "标点表达度", "逗号念出来没有", "—", "mt_punct_expr.py", "✓ strong/weak/none", "—"),
]

# ---------- 复测表 ----------
AUC = {r["key"]: r for r in R2}


def fmt(v, nd=2):
    return "—" if v is None else ("%.*f" % (nd, v))


VERD = {
 "span_st": ("✓ 单条可用", "ok"),
 "crest": ("✓ 单条可用", "ok"),
 "hf": ("◐ 加绝对下限后可用", "warn"),
 "cent": ("✗ 对低通无响应", "bad"),
 "tilt": ("✗ 对低通无响应", "bad"),
 "rev": ("✗ 方向反了", "bad"),
 "head": ("✗ 无响应", "bad"),
 "tail": ("✗ 无响应", "bad"),
 "espan": ("✗ 口径缺陷（见第 38 项）", "bad"),
 "hnr": ("✗ 对变速无响应", "dim"),
 "voiced": ("✗ 挖 80ms 只占 1% 帧", "bad"),
 "octskip": ("✗ 无响应", "bad"),
 "flat": ("✗ 原实现失效", "dim"),
}

H = []
A = H.append
A("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>检测项清账 · 丢掉的东西去哪了</title>
<style>
:root{--bg:#fbfaf7;--card:#fff;--ink:#1d1c1a;--dim:#6b6862;--line:#e3ded4;
--accent:#8a6d3b;--ok:#2f6b4f;--warn:#9a5b1e;--bad:#a33a2f;--soft:#f3efe6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1240px;margin:0 auto;padding:40px 24px 90px}
h1{font-size:27px;font-weight:600;letter-spacing:.4px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:26px}
h2{font-size:19px;font-weight:600;margin:42px 0 12px;padding-bottom:8px;
border-bottom:1px solid var(--line)}
table{border-collapse:collapse;width:100%;font-size:12.5px;background:var(--card);
box-shadow:0 1px 2px rgba(0,0,0,.04);border-radius:6px;overflow:hidden}
th,td{padding:7px 9px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--soft);font-weight:600;font-size:11.5px;color:#4a463f;white-space:nowrap}
tr:last-child td{border-bottom:none}
.mono{font-family:ui-monospace,"SF Mono",Consolas,monospace;font-size:11px}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.dim{color:var(--dim)}
.box{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:4px;padding:13px 17px;margin:16px 0;font-size:13.5px}
.box.bad{border-left-color:var(--bad)}
.box.ok{border-left-color:var(--ok)}
ul{margin:8px 0;padding-left:20px}li{margin:5px 0}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 8px}
.kpi div{flex:1 1 150px;background:var(--card);border:1px solid var(--line);
border-radius:6px;padding:10px 13px}
.kpi b{display:block;font-size:21px;font-weight:600;letter-spacing:-.5px}
.kpi span{font-size:11.5px;color:var(--dim)}
.grp td{background:#f7f4ec;font-weight:600;color:var(--accent);font-size:12px}
.foot{margin-top:50px;padding-top:14px;border-top:1px solid var(--line);
color:var(--dim);font-size:12px}
code{background:#f3efe6;padding:1px 4px;border-radius:3px;font-size:11.5px}
</style></head><body><div class="wrap">""")

A("<h1>检测项清账：丢掉的 57 项去哪了</h1>")
A('<div class="sub">逐项交代弃用原因 + 本次复测实证 · 数据源 SKILL.md 2398 行 / '
  '_drop_audit.json（45 文件）/ _drop_audit2.json（15 文件）· 2026-10-31</div>')

A('<div class="kpi">')
A('<div><b>57</b><span>清账条目</span></div>')
A('<div><b>30</b><span>真没用（不捞）</span></div>')
A('<div><b>10</b><span>口径错被误杀</span></div>')
A('<div><b>7</b><span>只能组级，被一刀切</span></div>')
A('<div><b>10</b><span>其实还在跑</span></div>')
A("</div>")

A('<div class="box ok"><b>先回答你的判断：你说得对。</b>'
  '我确实把三类东西混成了一句「没用」：<br>'
  '① <b>真的没用</b>（无响应 / 判反 / 有物理上限）—— 30 项，别捞；<br>'
  '② <b>用错口径被误杀</b> —— 10 项，其中有 4 项本次复测拿到了强响应（削波、气声、'
  '压平、高频比），属于我判错了；<br>'
  '③ <b>有用但只能组级</b> —— 7 项，我把「不能单条裁决」写成了「没用」，'
  '于是一整条轴从判定链里删掉，其实它可以留在批次面板上；<br>'
  '④ 另有 10 项你以为丢了，其实还在跑，只是换了名字（NISQA / SQUIM / 声纹 / 句内漂移…）。</div>')

A("<h2>一、逐项清账</h2>")
A('<div class="sub" style="margin:0 0 10px">「复测」列只对本次实跑过的项有值；'
  '其余标 —，判定依据是当初的实测记录（列在「依据」里）。</div>')
A("<table><tr><th>#</th><th>检测器</th><th>它该抓什么</th><th>当初为什么弃</th>"
  "<th>依据</th><th>现在</th><th>本次复测</th></tr>")
for r in ROWS:
    if r[1] is None:
        A('<tr class="grp"><td colspan="7">%s</td></tr>' % r[0])
        continue
    n, name, what, why, ev, now, ret = r
    cls = ""
    if ret.startswith("✓"):
        cls = ' class="ok"'
    elif ret.startswith("✗"):
        cls = ' class="bad"'
    elif ret.startswith("◐"):
        cls = ' class="warn"'
    A("<tr><td class='dim'>%s</td><td><b>%s</b></td><td>%s</td><td>%s</td>"
      "<td class='dim mono'>%s</td><td>%s</td><td%s>%s</td></tr>"
      % (n, name, what, why, ev, now, cls, ret))
A("</table>")

A("<h2>二、本次复测：拿已知坏样本重打一遍</h2>")
A('<div class="box">方法：5 条交付版好音 × 8 类注入退化（切碎/削波/等响/挖洞/变速/低通/'
  '压平音高/结巴）+ 2 类补测（气声化、慢包络等响）。<br>'
  '<b>AUC</b> = 好 5 条 vs 坏 5 条的 Mann-Whitney（0.5 = 无响应）；'
  '<b>SNR</b> = 对口劣化幅度 ÷ <b>同一条目跨 10~12 个 seed 的抖动 SD</b>。'
  'SNR ≥2 才有资格做单条判据，1~2 只能组级。<br>'
  '<span class="dim">这套口径是 18.30「不变性测试」的补丁 —— 那次只测了「无关变换该不动」，'
  '没测「对口缺陷该动多少」。这次两边都测。</span></div>')

A("<table><tr><th>指标</th><th>对口退化</th><th>好 p50</th><th>坏 p50</th>"
  "<th>AUC</th><th>跨 seed 抖动 SD</th><th>SNR</th><th>裁决</th></tr>")
for r in R2:
    v, cls = VERD.get(r["key"], ("—", ""))
    A("<tr><td>%s</td><td class='mono'>%s</td><td>%s</td><td>%s</td><td>%s</td>"
      "<td>%s</td><td>%s</td><td class='%s'>%s</td></tr>"
      % (r["name"], r["deg"], fmt(r["good"], 3), fmt(r["bad"], 3), fmt(r["auc"]),
         fmt(r["sd"]), fmt(r["snr"]), cls, v))
A("</table>")

g, b, s = A2["good"], A2["breathy"], A2["flat_slow"]
keys = [("hnr", "HNR (dB)", 2), ("cent", "谱质心 (Hz)", 0), ("tilt", "谱倾斜", 2),
        ("flat", "谱平坦度", 3), ("hf", ">4k 能量比", 3),
        ("espan", "能量跨度·现口径", 2), ("espan_v", "能量跨度·浊音口径", 2)]
A('<div class="sub" style="margin:22px 0 8px">补测：原退化集里没有「气声化」和「干净的等响」，'
  '这两个恰恰是 dots.tts 加 <code>&lt;rate&gt;</code> 标签时的真实副作用。</div>')
A("<table><tr><th>指标</th><th>好 p50</th><th>气声化 p50</th><th>倍数</th>"
  "<th>慢包络等响 p50</th><th>方向</th></tr>")
for k, nm, nd in keys:
    gv = st.median([r[k] for r in g.values() if r.get(k) is not None])
    bv = st.median([r[k] for r in b.values() if r.get(k) is not None])
    sv = st.median([r[k] for r in s.values() if r.get(k) is not None])
    ratio = ("×%.1f" % (bv / gv)) if gv and abs(gv) > 1e-9 else "—"
    if k in ("espan",):
        d = '<span class="bad">反了（应降反升）</span>'
    elif k == "espan_v":
        d = '<span class="ok">对（降 50%）</span>'
    elif k == "hnr":
        d = '<span class="ok">对（降 2.6dB，弱）</span>'
    else:
        d = '<span class="ok">对</span>' if abs(bv - gv) > abs(sv - gv) else '<span class="dim">不敏感</span>'
    A("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
      % (nm, fmt(gv, nd), fmt(bv, nd), ratio, fmt(sv, nd), d))
A("</table>")

A("<h2>三、被我冤枉的三项，以及一个新发现的真 bug</h2>")

A('<div class="box ok"><b>① 峰值因数 —— 我拿「内部失真」否掉了「削波检测」</b><br>'
  '当初的判决是：L053 听着炸，但峰值只有 0.34，所以峰值检测没用。'
  '这句推理是错的 —— L053 是<b>生成时的内部失真</b>（波形没削顶），'
  '峰值因数本来就抓不到它。<br>'
  '本次复测：真削波（×4 增益硬切）<b>AUC 1.00 / SNR 3.39</b>，'
  '好 10.8dB vs 坏 5.4dB，中间隔着 3 个抖动 SD。<br>'
  '<b>动作</b>：接回来，只判削波（crest &lt; 7dB），不当「炸」的判据。</div>')

A('<div class="box ok"><b>② 谱平坦度 / 谱质心 / 谱倾斜 / 高频比 —— 气声化是强响应</b><br>'
  '当初写「谱平坦度好坏重叠」，测的是「一条里某个噪声段 vs 语音段」，'
  '不是「整条被气声化」。<br>'
  '本次复测（气声化 = 混 35% 高通白噪，模仿 <code>&lt;rate&gt;</code> 拉低后的填气）：'
  '谱质心 260 → <b>2520 Hz（×9.7）</b>，谱倾斜 −16.2 → −0.95，'
  '平坦度 0.000 → 0.108，>4k 比 0.001 → 0.159（×159）。<br>'
  '<b>动作</b>：谱质心/倾斜已在音色闸门里（×0.78~1.28 / ±3），气声会被判 FAIL，这条没问题；'
  '平坦度与高频比补进「音质」一栏做参考，不单独否决。</div>')

A('<div class="box bad"><b>③ 真 bug：energy_span 的选帧是相对阈值，对「压平」会反向判</b><br>'
  '现行口径（§18.29 定的）是 <code>db &gt; p90 − 25</code> 剔静音。'
  '问题在于 p90 本身随动态范围移动：<b>整条被压平时，p90 往下掉，'
  '静音帧反而被选进来</b>，极差被静音撑大。<br>'
  '实测（5 条交付版做 200ms 慢包络等响）：好样本 16.9/17.0/13.6/14.0/21.2 dB，'
  '压平后 <b>5.7/25.4/4.7/24.0/24.3</b> —— 3 条降、2 条升，方向乱掉。<br>'
  '加一个条件 <code>f0 &gt; 0</code>（只取浊音帧）后：好 10.1/9.7/8.8/8.5/13.8，'
  '压平后 <b>4.9/8.2/4.7/4.4/12.3</b>，中位降 50%，5 条里 4 条明确下降。<br>'
  '<b>已实现开关</b> <code>mt_rhythm_gate.py --span-voiced</code>，默认仍走旧口径。</div>')

A('<div class="box"><b>③-b 切换影响面（863 条裸生成全量）</b><br>'
  'span 中位 <b>16.1 → 13.6 dB</b>（低 2.5）；FIX_HIGH <b>71 → 7</b>，'
  'WATCH_HIGH 122 → 60；FIX_LOW 1 → 8，WATCH_LOW 54 → 96；UNMEAS 72 → 87。<br>'
  '旧口径那 71 条「太陡」里，<b>37 条直接回 PASS、19 条回 WATCH</b> —— '
  '正是 §18.28 记的「191 条 FIX_HIGH 大量只超 0.1~0.3dB」的同一个病根：'
  '静音被算进起伏，系统性偏高。<br>'
  '<span class="dim">上列是用旧带判新 span 的结果，FIX_LOW 虚增；'
  '真要切换必须先重标 _rhythm_bands.json。</span></div>')

A('<div class="box ok"><b>④ span_st —— 「能不能判起伏」和「能不能判压平」是两件事</b><br>'
  '当初退役的理由是「真人个体差 p05 4.17~p95 16.99，组间差只有 4.26，没有靶子」。'
  '这个理由只对「这句够不够起伏（和真人比）」成立。<br>'
  '本次复测：对<b>音高被压平</b>（整句 F0 压成单音）<b>AUC 1.00 / SNR 2.96</b>，'
  '好 9.65 st vs 坏 2.95 st。<br>'
  '<b>动作</b>：接回来做单条判据（span_st &lt; 4.5 st = 被压平），'
  '但它<b>不能</b>回答「够不够起伏」—— 那一层仍然没有靶子。</div>')

A("<h2>四、为什么我会反复误杀：四个机制</h2>")
A("<table><tr><th>机制</th><th>表现</th><th>栽过几次</th><th>现在的防线</th></tr>")
A("<tr><td><b>分母塌陷</b></td><td>比值型判据，分母趋零时全部失效</td>"
  "<td>6 次（CTL_VOICED_MIN / rms_x / DUR_GAIN_MAX / loc 用 max / "
  "stretch_segments 段长 / HF_ABS_MIN）</td>"
  "<td>分子分母都设绝对下限</td></tr>")
A("<tr><td><b>相对阈值随输入漂移</b></td><td>p90−25 这种阈值会被整体动态压缩骗</td>"
  "<td>本次第 1 次抓到（energy_span）</td>"
  "<td>加绝对条件（浊音帧 / 绝对 dB）</td></tr>")
A("<tr><td><b>没做不变性测试</b></td><td>极差类指标对静音位置、时间伸缩敏感</td>"
  "<td>1 次（18.29，慢 12% 让 span 砍半）</td>"
  "<td>mt_metric_audit.py，SNR ≥3 才准单条</td></tr>")
A("<tr><td><b>按测量值分层比较</b></td><td>同程序只换被检验变量，形状自己就出来了</td>"
  "<td>1 次（18.21，ctl→ctl 抖动 +2.44~+5.32）</td>"
  "<td>先跑零分布对照</td></tr>")
A("<tr><td><b>标签本身是代理</b></td><td>audio-FAIL ≈「句子短」，换任何模型都测不出差别</td>"
  "<td>1 次（18.15，全部 AUC 覆盖 0.5）</td>"
  "<td>选型只用合成 known-answer</td></tr>")
A("</table>")

A("<h2>五、要动手的三件事</h2>")
A("<ul>")
A("<li><b>修 energy_span 选帧</b> —— <span class='ok'>开关已落地</span> "
  "（<code>--span-voiced</code>）。还差重标 159 条真人带与 863 条裸生成带；"
  "不切则起伏闸门对「压平」方向不可信。</li>")
A("<li><b>接回峰值因数</b>：<code>crest &lt; 7dB</code> 判削波，只报 WARN（不当「炸」的判据）。"
  "<span class='dim'>待接</span></li>")
A("<li><b>接回 span_st</b>：<code>&lt; 4.5 st</code> 判「音高被压平」，单条可用；"
  "「够不够起伏」仍不做单条。<span class='dim'>待接</span></li>")
A("</ul>")
A('<div class="box"><b>不动的一批</b>：head/tail 斜率、rev_rate、loc、Prosogram 滑音、'
  'TTSDS2 逐条分 —— 复测确认它们对「对口缺陷」要么无响应、要么方向反，'
  '保持「只做 n≥20 的组级描述」。这不是保守，是 SNR 摆在 1 附近。</div>')

A('<div class="foot">复测脚本 <span class="mono">_drop_audit.py</span> / '
  '<span class="mono">_drop_audit2.py</span> / <span class="mono">_drop_report.py</span> · '
  '产物 <span class="mono">_drop_audit.json</span> / <span class="mono">_drop_report.json</span> · '
  '所有「好样本」= _mt_pick 的 5 条交付版，抖动 = _mt_adv_ctl_*/ 的同 uid 跨 seed</div>')
A("</div></body></html>")

open(os.path.join(ROOT, "_drop_report.html"), "w", encoding="utf-8").write("\n".join(H))
print("wrote _drop_report.html  %d rows" % len(ROWS))
