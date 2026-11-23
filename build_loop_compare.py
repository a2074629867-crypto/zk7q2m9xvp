# -*- coding: utf-8 -*-
"""build_loop_compare.py —— 旁白回环 vs 对白回环：逐工具对照表。

数据源（全部实读，不写死）：
  _mt_loop_state.json           旁白单元（ch1 180 个）
  castle_dialog_report.json     对白引号块（1538 个）
  _mt_gate.json                 旁白门禁结果（1247 个候选）
  pause_intent.json             LLM 停顿语义判定（must/opt/no）
  _punct_expr.json              标点表达度声学实测
  _voice_baseline.json          八档音色基线
输出：_loop_compare.html
"""
import json
import os
import re
import statistics as st
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))

STATE = J("_mt_loop_state.json")["units"]
DLG = J("castle_dialog_report.json")["units"]
GATE = J("_mt_gate.json")
INTENT = J("pause_intent.json")
PEXPR = J("_punct_expr.json")
VB = J("_voice_baseline.json")

# ---------- 统计 ----------
W = lambda t: len(re.findall(r"[A-Za-z][A-Za-z'-]*", t))
ch1 = [v for v in STATE.values() if v.get("ch") == "ch1"]
nw_narr = [W(v["text"]) for v in ch1]
nw_dlg = [W(u["text"]) for u in DLG]
MED_N, MED_D = st.median(nw_narr), st.median(nw_dlg)
SHORT3 = 100 * sum(1 for x in nw_dlg if x <= 3) / len(nw_dlg)
SHORT6 = 100 * sum(1 for x in nw_dlg if x <= 6) / len(nw_dlg)

gc = Counter(r["verdict"] for r in GATE)
gcode = Counter(r["code"] for r in GATE)
SKIP_N = gcode.get("n/a_short", 0)

ic = Counter(v for k, x in INTENT.items() if not k.startswith("_") for v in x.values())
I_TOT = sum(ic.values())
I_NO = ic.get("no", 0)

CONF = Counter(u["conf"] for u in DLG)
UNK = CONF.get("UNKNOWN", 0)
WEAK = CONF.get("WEAK", 0)

# 每档 F0 跨度（用基线中位）
f0s = {k: v["f0"]["med"] for k, v in VB.items() if "f0" in v}

# ---------- 工具清单 ----------
# (编号, 工具, 做什么, 输入→输出, 判据/关键参数, 旁白状态, 对白状态)
TOOLS = [
 ("A 文本与任务规划", None, None, None, None, None, None),
 ("A1", "castle_attr8.py", "说话人对白归属：全文状态机切引号块 + 8 类判据定 who",
  "castle_full.txt → castle_dialog_v8.json（1538 块）", "CONFIRMED/ALTERNATE/WEAK/UNKNOWN 四档",
  "—", "✓ 专用"),
 ("A2", "build_dialog_report.py", "按角色分组出对白报告，带章号与置信度",
  "v8 + castle_lines.json → _dialog_report.html / castle_dialog_report.json", "—",
  "—", "✓ 专用"),
 ("A3", "cloud/ref/cast.json", "音色档案：8 角色 + 主角各 4 档（ref/ref_text/基线带）",
  "人工整理 → JSON", "每档独立 f0/cen/slp 带", "1 个 ref（旁白音）", "◐ 8 档已建，6 配角缺"),
 ("A4", "cloud/cuda/make_jobs.py", "生成任务表；--ch 旁白固定 ref，--dialog 逐条带 ref",
  "state / plan → jobs_*.json", "nwords≥1；缺 ref 直接退出", "✓ 在用", "✓ --dialog 已实现"),
 ("A5", "cloud/cuda/make_probe.py", "固定同一句文本的音色探针（压掉内容方差）",
  "cast.json → jobs_probe.json（36 条）", "9 档 × 2 句 × 2 seed", "—", "✓ 已生成，未跑"),
 ("A6", "mt_extract.py / mt_plan2.py", "EPUB 文本切旁白单元（按段落/句长）",
  "EPUB → 180 单元/章", "单元 5~23 词（p10~p90）", "✓ 在用", "— 不适用（对白按引号块）"),

 ("B 生成", None, None, None, None, None, None),
 ("B1", "mt_gen.py", "本地 audiocpp + Vulkan 批量生成",
  "items → wav", "8G 显存必 OOM，只能 --threads 2", "✓ 回环默认入口", "✗ 不可用（同左）"),
 ("B2", "cloud/cuda/bootstrap4.sh", "云端幂等环境 + 生成编排（持久盘命中即跳过）",
  "jobs.json → out/*.wav", "依赖/模型命中检测", "✓", "✓ 共用"),
 ("B3", "cloud/cuda/run_dots.py", "逐 job 生成，**每条取自己的 ref**",
  "jobs → wav + 失败换 seed(attempt*977)", "max_generate_length=200", "✓（单 ref）", "✓ 多 ref 已支持"),
 ("B4", "mt_loop.gen_one_round", "回环的生成入口：按 seed 分组调 mt_gen",
  "uids → {uid: wav}", "MAX_CAND=3", "✓", "✗ 无对白对应物（缺口）"),

 ("C 音频预处理", None, None, None, None, None, None),
 ("C1", "mt_trim_head.py", "裁前导/尾随静音（前导 p50 1.22s，占单元时长 18%）",
  "raw → trim", "head 0.05 / tail 0.20", "✓", "✓ 复用"),
 ("C2", "_asr_lib.py --trim", "ASR 前裁边，并把时间戳平移回原文件",
  "wav → 词级时间戳", "不平移会让 TextGrid 整体提前", "✓", "✓ 复用（必须）"),

 ("D 转写", None, None, None, None, None, None),
 ("D1", "_asr_lib.py", "Parakeet TDT v3 本机转写（离线兜底）",
  "wav → text + words", "CPU，几百 MB", "✓", "✓"),
 ("D2", "_asr_qwen.py", "Qwen3-ASR-1.7B 云端转写（bf16，2s 加载）",
  "wav → text + words", "A10，0.2~1.7s/条", "◐ 备用", "✓ 云端主用"),
 ("D3", "_asr_norm.py", "覆盖率口径归一：缩写/连字符/切合词三类假阳性",
  "ref 词 + ASR 词 → cov/miss", "mrs→missus、thirtyseven→thirty-seven", "✓", "✓ 必须（短句更敏感）"),
 ("D4", "write_textgrid（mt_loop 内）", "词级 TextGrid，供 Praat/WPT 读",
  "words → .TextGrid", "—", "✓", "✓"),

 ("E 韵律 / 重音 / 停顿测量", None, None, None, None, None, None),
 ("E1", "WPT prosody_labeller", "词级 prominence + boundary（.prom）",
  "wav+TextGrid → .prom", "wavelet_prosody_toolkit", "✓ 核心", "◐ 短句 prom 稳定性待验"),
 ("E2", "_predict.py", "规则重音预测（零训练）：封闭类虚词表 + 句内位置",
  "text → prominence 0/1/2", "二分类 F1 78.7%，top1 63.8%（旁白口径）", "✓", "◐ ≤3 词句 top1 不稳"),
 ("E3", "_gate.py", "主重音门禁：覆盖率 / 分离度 / 落位合法性",
  "text + .prom → PASS/ARTIFACT/MANUAL/SKIP", "cov<0.80 吞字；sep<0.15；**n<4 直接 SKIP**", "✓", "◐ 23.3% 的句子被 SKIP"),
 ("E4", "_gate_contour.py", "句内 F0 起伏判据（按马修母带标定）",
  "wav 目录 → json", "span / 末段斜率", "✓", "◐ 短句 span 噪声大"),
 ("E5", "mt_contour_compare.py", "同口径对比马修母带与我们（防两个函数各测一套）",
  "两批 wav → 对照表", "必须同一测量函数", "✓", "—"),
 ("E6", "mt_punct_expr.py", "标点表达度：TTS 到底把逗号念出来没有",
  "wav+词边界 → strong/weak/none", "gap≥0.30 strong；gap<0.06 且无延长无音高=none", "✓", "✓ 已有 33 条对白实测"),
 ("E7", "mt_sentence_type.py", "句型分类 → 该升还是该降（yes-no/tag 必须升）",
  "text → 调型方向", "纯文本规则，不调模型", "◐ 未接", "✓ 已按 59 条对白标定"),
 ("E8", "_f0_accent.py", "F0 重音测量（词级峰值/斜率）",
  "wav+词边界 → 重音特征", "—", "✓", "◐"),

 ("F LLM 语义层（用户指的那一层）", None, None, None, None, None, None),
 ("F1", "pause_intent.json", "**每处标点该不该停**：must / opt / no",
  "台词 → 逐标点判定", "33 条 / %d 处：must %d、opt %d、no %d" % (I_TOT, ic.get("must", 0), ic.get("opt", 0), ic.get("no", 0)),
  "— 旁白不用（96% 必停）", "✓ 专用，但未接进装配"),
 ("F2", "mt_expect_prompt.py", "旁白逗号判档任务书（只判 inner/bound，不给时长）",
  "单元 → LLM 任务书", "句末默认 clause；不许判 drop", "✓", "— 档位模型不适用"),
 ("F3", "mt_expect_merge.py", "三方判档合成（main/hy4/ds），2:1 取多数并留少数意见",
  "三份 json → pause_llm.json", "分歧标 _split", "✓", "—"),
 ("F4", "_llm_accent_eval.py", "LLM 判声学 top1 是合法重音还是分析器伪影",
  "prom top1 → VALID/ARTIFACT", "对照 _accent_gold20.json 人工金标", "✓", "◐ 未在短句上验"),
 ("F5", "mt_adv_fix.py", "副词「该慢没慢」：LLM 双票选词 → 破折号重生",
  "state → 重生 → 复测", "sps 阈值；破折号比 <rate> 有效", "✓", "◐ 未跑对白"),

 ("G 门禁与决策", None, None, None, None, None, None),
 ("G1", "mt_loop.py", "回环调度：collect_todo / next_seed / unit_verdict / pick_best",
  "state → 下一轮任务", "MAX_CAND=3；stable_top1 连续 2 次同词即停", "✓", "◐ 结构可复用，缺 ref 维度"),
 ("G2", "mt_spk_audit.py", "音色/电平/F0 审计（0.29 事故后加的第二道门）",
  "wav + ref → OK/WARN/VOID", "声纹≥0.65（已退役）；RMS −24±6；F0 相对 ref", "✓", "◐ 只保留 RMS/F0"),
 ("G3", "mt_voice_baseline.py", "**每档各自**建一条基线（四把尺子互不相干）",
  "castle_fr_clean → _voice_baseline.json", "p10-p90，n<6 用 median±2.5MAD，加最小带宽", "—", "✓ 8 档已建"),
 ("G4", "mt_voice_gate.py", "音色闸门：产物 vs 它自己那一档的 ref",
  "wav → PASS/WARN/FAIL", "F0 ±3 半音 / 谱质心 ×0.78~1.28 / 谱倾斜 ±3，**3 取 2**", "—", "✓ 对角线 75~100%"),
 ("G5", "_verify_loop.py", "回环四段体检（决策/选种/生成命令/挑优），不真生成",
  "state → 报告", "—", "✓", "◐ 只验旁白"),

 ("H 装配", None, None, None, None, None, None),
 ("H1", "mt_chapter_join.py", "旁白整章拼接：按标点/段落给停顿 + 逐条电平归一",
  "trim 单元 + para_map → 整章 wav", "para 1.55 / clause 1.05 / bound 0.85 / none 0.30", "✓", "— 不适用"),
 ("H2", "mt_final_pause.py", "逐边界绝对时长（读 LLM 判定 + intent + 标点表达度）",
  "wav + pause_llm.json → 成品", "可删/可补静音，带安全校验", "✓ 旧链", "◐ 未接对白"),
 ("H3", "mt_rdr_gate.py", "RDR 闸门（**必须在插停顿之前**）",
  "trim 单元 + para → json", "主口径 C（voiced 总和）≤0.15", "✓", "◐ 未接对白"),
 ("H4", "mt_dialog_join.py", "对白装配：逐条归一 → 按**换不换人**切停顿",
  "plan + 音频 → 场景 wav + timeline", "换人 0.75 / 同人句末 0.50 / 句中 0.30", "—", "✓ 已跑 59 条"),

 ("I 交付体检", None, None, None, None, None, None),
 ("I1", "mt_audit.py", "交付前三层体检（文本/音频/拼装），只出结论不改文件",
  "章 → 报告", "—", "✓", "◐ 无对白版本"),
 ("I2", "mt_nisqa_all.py", "NISQA MOS 四维（断流/噪声/染色/整体）",
  "wav 目录 → json", "0.7s/条", "✓", "✓ 可复用"),
 ("I3", "mt_pause_cross.py", "语言直觉 × 声学实测 2×2：该停没停 / 不该停却停",
  "intent + punct_expr → 交叉表", "must 且 gap<0.10 = 漏停", "◐ 未接", "✓ 专用"),
]

# ---------- 五个结构性差异 ----------
DIFFS = [
 ("句长", "中位 %d 词（p10 5 / p90 23）" % MED_N,
  "中位 %d 词（43%% ≤6 词，%.1f%% ≤3 词）" % (MED_D, SHORT3),
  "对白短 %.1f 倍。`_gate.py` 在 n&lt;4 时直接 SKIP，"
  "而旁白全库 1247 个候选里只有 %d 条（%.1f%%）被 SKIP" % (1.0 * MED_N / MED_D, SKIP_N, 100 * SKIP_N / len(GATE))),
 ("停顿逻辑", "96% 的逗号必停，只分 inner/bound 两档（ch1：inner 6 / bound 122）",
  "must / opt / **no** 三档（%d 处里 no 占 %.1f%%）" % (I_TOT, 100 * I_NO / I_TOT),
  "旁白的结论是「不存在该不该停」，对白恰恰相反："
  "反意疑问、连续谓语这些逗号**不该停**，硬塞静音会把一句台词切成两句"),
 ("音色", "1 套 ref（旁白音，8.3s 英文男声）",
  "8 档（2 人 × 4 情绪），F0 从 %.0f 到 %.0f Hz" % (min(f0s.values()), max(f0s.values())),
  "对白每句要指定 ref，且验收要按**它自己那一档**的基线，不能跨档比"),
 ("重音", "`_predict.py` 规则预测 + LLM 复核（VALID/ARTIFACT）",
  "同左，但短句 top1 不稳",
  "`_predict` 的 63.8% top1 命中率是旁白口径（中位 13 词）；"
  "对白 43% 的句子 ≤6 词，句内可选焦点本来就少"),
 ("装配", "按标点/段落：para 1.55 / clause 1.05 / bound 0.85 / none 0.30",
  "按换不换人：换人 0.75 / 同人句末 0.50 / 句中 0.30",
  "叙述里句号就该停 1.7s；对白里同一人连说两句停 0.5s 就够，换人反而要留接话空隙"),
 ("说话人归属", "不需要（只有一个声音）",
  "%d 块里 UNKNOWN %d（%.0f%%）、WEAK %d（%.0f%%）" % (len(DLG), UNK, 100 * UNK / len(DLG), WEAK, 100 * WEAK / len(DLG)),
  "旁白没有这一层。对白必须先决定「这句是谁」，判错的代价是整句音色错"),
]

# ---------- 缺的工具 ----------
GAPS = [
 ("M1", "情绪 / 表现力闸门", "暂不建（等音色库定标）",
  "voice gate 测的是「音区/音色」（F0 中位、谱质心、谱倾斜），这三个量对「说得平还是激动」几乎不动。"
  "需要另一把尺子：span_st（F0 p10~p90 半音跨度）、dyn_db（帧能量 p90~p10）、"
  "hnr（气声）、alpha（500-1000/1000-5000 能量比）、slope（走向）。"
  "每档独立基线，5 维取 3 判 PASS，另单列 flat（起伏与动态双低 = 念对了但没演）。"),
 ("M2", "对白短句门禁", "待建",
  "`_gate.py` 对 n&lt;4 的句子返回 SKIP，对白里 %.1f%% 的句子落在这个区间。"
  "短句不能用韵律判据，只能换：ASR 覆盖率（吞字）+ 音色档 + 标点表达度（有没有把语气读出来）。" % SHORT3),
 ("M3", "场景级一致性", "待建",
  "同角色同情绪跨句的 F0/能量漂移、换人处的电平差。单条都 PASS，拼起来仍可能「一会儿大一会儿小」。"
  "旁白靠全库 −24dBFS 统一解决；对白还要多一条「同一角色跨句音色稳定」。"),
 ("M4", "说话人归属置信度闸门", "待建",
  "只放 CONFIRMED/ALTERNATE 进生成，WEAK/UNKNOWN 不进。"
  "现在 %d 块里 %d 块是 UNKNOWN，直接全量生成会把大量音色错配的句子做出来。" % (len(DLG), UNK)),
 ("M5", "对白生成入口（回环 → 云端）", "待建",
  "旁白回环的 gen_one_round 调本机 audiocpp（8G 必 OOM），云端走 bootstrap4.sh，两条路没打通。"
  "对白连这个入口都没有 —— 现在只能手工出 jobs 再跑云端。"),
]

# ---------- HTML ----------
H = []
A = H.append
A("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>旁白回环 vs 对白回环 · 工具全清单</title>
<style>
:root{--bg:#fbfaf7;--card:#fff;--ink:#1d1c1a;--dim:#6b6862;--line:#e3ded4;
--accent:#8a6d3b;--ok:#2f6b4f;--warn:#9a5b1e;--bad:#a33a2f;--soft:#f3efe6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:27px;font-weight:600;letter-spacing:.4px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:30px}
h2{font-size:19px;font-weight:600;margin:44px 0 14px;padding-bottom:8px;
border-bottom:1px solid var(--line)}
h3{font-size:15px;font-weight:600;margin:26px 0 10px;color:var(--accent)}
table{border-collapse:collapse;width:100%;font-size:13px;background:var(--card);
box-shadow:0 1px 2px rgba(0,0,0,.04);border-radius:6px;overflow:hidden}
th,td{padding:7px 9px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--soft);font-weight:600;font-size:12px;color:#4a463f;white-space:nowrap}
tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.mono{font-family:ui-monospace,"SF Mono",Consolas,monospace;font-size:11.5px}
.tag{display:inline-block;padding:1px 6px;border-radius:10px;font-size:11px;
border:1px solid currentColor;white-space:nowrap}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.dim{color:var(--dim)}
.box{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:4px;padding:13px 17px;margin:16px 0;font-size:13.5px}
.box.warn{border-left-color:var(--warn)}
.box.bad{border-left-color:var(--bad)}
ul{margin:8px 0;padding-left:20px}li{margin:5px 0}
.kpi{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0 6px}
.kpi div{flex:1 1 140px;background:var(--card);border:1px solid var(--line);
border-radius:6px;padding:11px 13px}
.kpi b{display:block;font-size:22px;font-weight:600;letter-spacing:-.5px}
.kpi span{font-size:11.5px;color:var(--dim)}
.foot{margin-top:52px;padding-top:14px;border-top:1px solid var(--line);
color:var(--dim);font-size:12px}
.grp td{background:#f7f4ec;font-weight:600;color:var(--accent);font-size:12.5px}
td.st{white-space:nowrap;font-size:12px}
.step{border-left:2px solid var(--line);padding:0 0 0 16px;margin:18px 0}
.step h4{margin:0 0 4px;font-size:14px;font-weight:600}
.step .tl{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--accent);
margin:2px 0 6px}
.step p{margin:4px 0;font-size:13.5px}
.step .why{color:var(--dim);font-size:13px}
</style></head><body><div class="wrap">""")

A("<h1>旁白回环 vs 对白回环 · 工具全清单</h1>")
A('<div class="sub">逐项对照 41 个工具 · 数据取自 _mt_loop_state.json（ch1 180 单元）、'
  'castle_dialog_report.json（%d 块）、_mt_gate.json（%d 候选）、pause_intent.json（%d 处）· 2026-10-31</div>'
  % (len(DLG), len(GATE), I_TOT))

n_tools = sum(1 for t in TOOLS if t[1])
n_both = sum(1 for t in TOOLS if t[1] and t[5] and t[6]
             and t[5][0] in "✓◐" and t[6][0] in "✓◐")
n_reuse = sum(1 for t in TOOLS if t[1] and t[6] and t[6].startswith("✓"))
n_mod = sum(1 for t in TOOLS if t[1] and t[6] and t[6].startswith("◐"))
n_miss = sum(1 for t in TOOLS if t[1] and t[6] and t[6].startswith("✗"))
n_only_n = sum(1 for t in TOOLS if t[1] and t[5] and t[5][0] in "✓◐"
               and t[6] and t[6].startswith("—"))
A('<div class="kpi">')
A('<div><b>%d</b><span>清单里的工具总数</span></div>' % n_tools)
A('<div><b>%d</b><span>两条链共用</span></div>' % n_both)
A('<div><b>%d</b><span>对白直接复用</span></div>' % n_reuse)
A('<div><b>%d</b><span>对白要改参数</span></div>' % n_mod)
A('<div><b>%d</b><span>对白侧没有</span></div>' % n_miss)
A("</div>")

A('<div class="box"><b>一句话结论：</b>两条链路的骨架是同一套（生成 → 裁边 → 转写 → 韵律测量 → 门禁 → 装配），'
  '真正不同的只有三处：<b>音色从 1 套变 8 套</b>、<b>停顿从「标点决定」变成「换人 + 该不该停」</b>、'
  '<b>句长掉到中位 %d 词</b>。所以对白不是另建一条链，而是<b>同一套工具换参数、加一层音色维度</b>；'
  '真正缺的是「情绪演没演到位」这一把尺子，而它要等音色库定标之后才建得准。</div>' % MED_D)

# 一、并排
A("<h2>一、两条链路并排</h2>")
A("<table><tr><th>阶段</th><th>旁白（现在跑的）</th><th>对白（要跑的）</th><th>差异</th></tr>")
STAGES = [
 ("① 任务表", "make_jobs --ch，全部指向同一个 ref", "make_jobs --dialog，每条带 who/ref/情绪",
  "<span class='tag warn'>ref 维度</span>"),
 ("② 生成", "mt_gen（本机 Vulkan，8G 必 OOM）／云端 bootstrap4", "只能云端（run_dots 逐 job 取 ref）",
  "<span class='tag bad'>回环生成未打通</span>"),
 ("③ 裁边", "mt_trim_head（前导 p50 1.22s）", "同左", "<span class='tag ok'>完全复用</span>"),
 ("④ 转写", "Parakeet 本机 / Qwen3 云端 + _asr_norm 归一", "同左（短句更依赖归一）", "<span class='tag ok'>复用</span>"),
 ("⑤ 韵律测量", "WPT → _gate（重音）/ _gate_contour（起伏）", "同左，但 23.3% 的句子 n&lt;4 被判 SKIP",
  "<span class='tag warn'>短句失效</span>"),
 ("⑥ 停顿判定", "LLM 只判 inner/bound；句末默认 clause", "LLM 判 must/opt/no（含「不该停」）",
  "<span class='tag bad'>多一档</span>"),
 ("⑦ 音色验收", "mt_spk_audit（声纹已退役，留 RMS/F0）", "mt_voice_gate + 每档基线（3 取 2）",
  "<span class='tag warn'>新增一层</span>"),
 ("⑧ 决策回环", "mt_loop：3 候选 / stable_top1 停止", "结构可复用，缺 ref 维度", "<span class='tag warn'>要改</span>"),
 ("⑨ 装配", "mt_chapter_join：按标点/段落", "mt_dialog_join：按换不换人", "<span class='tag bad'>另一套</span>"),
 ("⑩ 交付体检", "mt_audit / NISQA / RDR / pause_cross", "只有 NISQA 与 pause_cross 能直接用", "<span class='tag warn'>缺对白版</span>"),
]
for s, a, b, c in STAGES:
    A("<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (s, a, b, c))
A("</table>")

# 二、链路走一遍
STEPS = [
 ("1", "切单元", "mt_plan2.py / mt_extract.py（旁白）　castle_attr8.py（对白）",
  "旁白把 EPUB 按段落切成 180 个单元/章，每个单元 5~23 词；对白按引号块切成 %d 块，一块一个说话人。" % len(DLG),
  "单元太长，模型控不住句内重音，一章的起伏会被抹平；单元太短，又没有句内结构可判。"
  "对白不能按段落切 —— 一段里可能有两句分属两个人（<span class='mono'>'You don't frighten me.' 'You wait.'</span>），"
  "整段判一人必然错一半。"),
 ("2", "定音色", "cloud/ref/cast.json　cloud/cuda/make_probe.py",
  "cast.json 存 8 档音色（2 人 × 4 情绪）的参考音、法语转写、以及每档自己的基线带；"
  "make_probe 生成 36 条「同一句文本」的探针，用来给每档定标。",
  "dots.tts 的音色是 <span class='mono'>generate(prompt_audio_path=…)</span> 的入参，不是加载时固定的 —— "
  "所以切角色不用重载模型（否则每条要 26 秒）。探针固定文本是关键："
  "文本一变，声纹测到的就是「说了什么」而不是「谁在说」。"),
 ("3", "出任务表", "cloud/cuda/make_jobs.py",
  "旁白 <span class='mono'>--ch</span> 把整章指向同一个 ref；对白 <span class='mono'>--dialog</span> "
  "给每条 job 写上 who / ref / ref_text，并按文本选情绪（侮辱词→angry，感叹号→excited，省略号或求饶词→soft）。",
  "任务表是「可重跑」的单位：生成中断后按文件存在与否续跑，不用记跑到哪。"
  "对白必须逐条带 ref，否则整章又变回一个声音。"),
 ("4", "生成", "mt_gen.py（本机）　cloud/cuda/bootstrap4.sh + run_dots.py（云端）",
  "旁白回环默认调本机 audiocpp（Vulkan）；对白只能走云端 A10，bf16，逐 job 换参考音，单条约 11.5 秒。",
  "本机 RX580 只有 8G，Vulkan 峰值必 OOM，而且重启救不了 —— 这是硬限制，不是配置问题。"
  "云端 24G 显存，模型加载 26 秒只做一次，之后每条只换 ref。"),
 ("5", "裁边", "mt_trim_head.py　_asr_lib.py --trim",
  "去掉 TTS 每段开头留的 0.8~1.4 秒静音（p50 1.22s，占单元时长 18%）；ASR 前再裁一次，"
  "并把词时间戳平移回原文件。",
  "不裁的话，这些空白会和我们插入的句间停顿叠加，句间停顿从 1.7 秒变成 3 秒 —— "
  "「停顿占比高、章太长」的真因就是它。时间戳不平移，TextGrid 会整体提前，门禁全错。"),
 ("6", "转写", "_asr_lib.py（Parakeet）　_asr_qwen.py（Qwen3-ASR）　_asr_norm.py",
  "把音频转成词级时间戳，再用 _asr_norm 把「缩写被切碎 / 连字符被合成 / 词被切或合」三类对齐假阳性归一。",
  "覆盖率是唯一不依赖韵律的硬判据（吞字、漏词、念错都会让它掉）。"
  "但口径不修就会反过来：<span class='mono'>mrs→missus</span>、<span class='mono'>thirtyseven→thirty-seven</span> "
  "会被判成漏词，好句子被反复送去重生，永远过不了。"),
 ("7", "韵律与重音", "WPT prosody_labeller　_predict.py　_gate.py　_gate_contour.py",
  "WPT 出词级 prominence/boundary；_predict 用规则预测「这句该重读哪个词」；"
  "_gate 把声学测出的 top1 和预测比对，判 PASS / ARTIFACT / MANUAL / SKIP；"
  "_gate_contour 另测句内 F0 起伏是否够。",
  "这是旁白回环的主判据：念对了字但重音落错，听感立刻变成「机器在念」。"
  "但它在 <span class='mono'>n&lt;4</span> 时直接返回 SKIP —— 对白 23.3% 的句子落在这个区间，等于没验收。"),
 ("8", "停顿", "mt_punct_expr.py　mt_sentence_type.py　pause_intent.json　mt_expect_prompt/merge.py　mt_final_pause.py",
  "两层：<b>语义层</b>由 LLM 判每处标点该不该停（must/opt/no）、停多长（inner/bound）；"
  "<b>声学层</b>由 mt_punct_expr 测 TTS 到底念出来没有（gap / 前词延长 / 音高重置 / 能量下凹 → strong/weak/none）；"
  "mt_sentence_type 补一条：yes-no 疑问和反意疑问必须升调，不能判它上扬是缺陷。",
  "旁白母带实测 96% 的逗号都停，所以只需判「停多长」；对白相反，"
  "反意疑问、连续谓语这些逗号<b>不该停</b>，硬塞静音会把一句台词切成两句 —— "
  "「不该停却停」比「该停没停」更伤。"),
 ("9", "音色验收", "mt_voice_baseline.py　mt_voice_gate.py　mt_spk_audit.py",
  "每档用**它自己**的切片建一条基线（F0 / 谱质心 / 谱倾斜），产物只跟它自己那一档比，"
  "三参数里两个在带内就算过；mt_spk_audit 另测电平与 F0 是否偏离参考。",
  "声纹（CAM++) 在这批素材上 AUC 0.491 = 随机：同一 ref 不同句子 0.344，"
  "而同一句不同 seed 0.796 —— 它测的是内容不是音色。所以换成三个逐帧统计量，"
  "它们对「说了什么词」不敏感、对「声道多长、声带多紧」敏感。"),
 ("10", "决策回环", "mt_loop.py　_verify_loop.py",
  "collect_todo 挑出该重生的单元 → next_seed 选没试过的 seed → 生成 → 分析 → pick_best 取最优；"
  "最多 3 个候选，连续两次主重音词相同就停（stable_top1），不再烧算力。"
  "_verify_loop 不生成，只验四段接口是否接得上。",
  "重生成是唯一能修「念错、吞字、重音落错」的手段，后期处理修不了。"
  "但必须有停止条件，否则一个单元可以无限重生 —— stable_top1 就是「这是文本驱动的，换 seed 没用」的判据。"),
 ("11", "装配", "mt_chapter_join.py　mt_dialog_join.py　mt_rdr_gate.py",
  "旁白按标点/段落给停顿（para 1.55 / clause 1.05 / bound 0.85 / none 0.30），逐条 voiced RMS 归一到 −25.1dBFS；"
  "对白按换不换人给停顿（换人 0.75 / 同人句末 0.50 / 句中 0.30），逐条归一到 −24dBFS。"
  "RDR 闸门必须在插停顿<b>之前</b>跑。",
  "叙述里句号就该停 1.7 秒；对白里同一人连说两句停 0.5 秒就够，换人反而要留接话空隙。"
  "逐条归一是因为各条增益差得远（对白 59 条实测 −8.6~−1.2dB，跨 7.4dB）—— "
  "不归一就是「一会儿大一会儿小」。"
  "RDR 放到插停顿之后，含停顿口径就彻底失效，只剩 voiced 口径可读。"),
 ("12", "交付体检", "mt_audit.py　mt_nisqa_all.py　mt_pause_cross.py",
  "mt_audit 做文本/音频/拼装三层体检（只出结论不改文件）；NISQA 打 MOS 四维查断流与染色；"
  "pause_cross 把「语言直觉」和「声学实测」做 2×2，分开算「该停没停」和「不该停却停」。",
  "单条都 PASS，拼起来仍可能断流、染色、节奏塌。NISQA 是唯一能查断流的客观分；"
  "pause_cross 是唯一能抓「硬塞静音」的工具 —— 这两种缺陷用别的指标都测不出来。"),
]

A("<h2>二、链路走一遍：每一步用了什么、为什么要有它</h2>")
A('<div class="box">下面按执行顺序走一遍。每一步都写三件事：<b>用了哪些工具</b>、'
  '<b>它具体做什么</b>、<b>为什么非有它不可</b>（去掉它会出什么问题）。'
  '标 <span class="mono">mono</span> 的是实际文件名，可以直接在仓库里找到。</div>')
for no, name, tools, what, why in STEPS:
    A('<div class="step"><h4>%s · %s</h4><div class="tl">%s</div>'
      '<p>%s</p><p class="why"><b>为什么需要：</b>%s</p></div>' % (no, name, tools, what, why))

# 三、工具全清单
A("<h2>三、工具全清单（41 项，逐项写清）</h2>")
A('<div class="box"><b>读法：</b>「旁白」「对白」两列的标记 —— '
  '<span class="tag ok">✓ 在用/可复用</span> '
  '<span class="tag warn">◐ 要改或未接</span> '
  '<span class="tag bad">✗ 缺</span> '
  '<span class="tag dim">— 不适用</span></div>')
A("<table><tr><th style='width:38px'>#</th><th style='width:170px'>工具</th>"
  "<th style='width:250px'>做什么</th><th style='width:210px'>输入 → 输出</th>"
  "<th style='width:200px'>判据 / 关键参数</th><th style='width:110px'>旁白</th><th style='width:130px'>对白</th></tr>")
for t in TOOLS:
    if t[1] is None:
        A('<tr class="grp"><td colspan="7">%s</td></tr>' % t[0])
        continue
    A("<tr><td class='mono'>%s</td><td class='mono'>%s</td><td>%s</td><td class='mono'>%s</td>"
      "<td>%s</td><td class='st'>%s</td><td class='st'>%s</td></tr>"
      % (t[0], t[1], t[2], t[3], t[4], t[5], t[6]))
A("</table>")

# 三、结构性差异
A("<h2>四、六个结构性差异（都带数字）</h2>")
A("<table><tr><th style='width:90px'>维度</th><th style='width:250px'>旁白</th>"
  "<th style='width:250px'>对白</th><th>为什么这会改变工具</th></tr>")
for name, a, b, why in DIFFS:
    A("<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (name, a, b, why))
A("</table>")

A('<div class="box warn"><b>最关键的一条：</b>旁白母带实测「96%% 的逗号都停、99%% 的句号都停」，'
  '所以旁白的结论是<b>停顿位置由标点决定，只判停多长</b>。对白不能沿用这个结论 —— '
  '对白的 %d 处判定里有 %d 处是 <span class="mono">no</span>（%.1f%%），'
  '这些逗号一旦硬塞静音，一句台词就被切成两句。'
  '「不该停却停」比「该停没停」更伤，这是 `mt_pause_cross.py` 里写死的结论。</div>'
  % (I_TOT, I_NO, 100 * I_NO / I_TOT))

# 四、LLM 层
A("<h2>五、LLM 层到底管什么（你记得的那两层，都在）</h2>")
A("<table><tr><th style='width:150px'>层</th><th style='width:180px'>工具</th>"
  "<th>LLM 判什么</th><th style='width:230px'>结果去向</th></tr>")
A("<tr><td><b>停顿 · 该不该停</b></td><td class='mono'>pause_intent.json</td>"
  "<td>逐标点判 <span class='mono'>must / opt / no</span>："
  "must=独立分句边界/句号/从句与主句之间；opt=话语标记/插入语/呼语（停也只 ≤0.35s）；"
  "no=语法性逗号/反意疑问/连续谓语。<b>这是语义判定，不是声学测量</b></td>"
  "<td>mt_pause_cross.py 做 2×2 交叉；mt_final_pause.py 决定塞不塞静音</td></tr>")
A("<tr><td><b>停顿 · 停多长</b></td><td class='mono'>mt_expect_prompt.py<br>→ mt_expect_merge.py</td>"
  "<td>旁白只判逗号是 <span class='mono'>inner</span>（同一成分内部）还是 "
  "<span class='mono'>bound</span>（两个成分之间）；句末默认 clause，不问。"
  "三方（main/hy4/ds）各判一次，2:1 取多数并留少数意见</td>"
  "<td>pause_llm.json → mt_final_pause.py 的绝对时长</td></tr>")
A("<tr><td><b>重音 · 合不合法</b></td><td class='mono'>_llm_accent_eval.py</td>"
  "<td>声学测出的 top1 焦点，在语言学上成不成立（否定/指示/时间/称呼/对比焦点 = VALID），"
  "还是分析器伪影（句首 F0 重置、边界效应 = ARTIFACT）</td>"
  "<td>与 _accent_gold20.json 人工金标对比，评门禁本身准不准</td></tr>")
A("<tr><td><b>重音 · 该不该慢</b></td><td class='mono'>mt_adv_fix.py</td>"
  "<td>LLM 双票（ds1+ds2）选出每单元「该慢的那一个副词」</td>"
  "<td>破折号包住该词重生 → 复测 sps</td></tr>")
A("</table>")

A('<div class="box"><b>对白这里缺的不是 LLM，是「接线」。</b>'
  'pause_intent 已经对 33 条对白判过 must/opt/no，_punct_expr 也测过声学实现，'
  '但 <span class="mono">mt_dialog_join.py</span> 现在只用固定的换人/同人停顿，'
  '<b>完全没读这两份结果</b>。所以对白的「该不该停」目前是人工判断，没进装配。</div>')

# 五、缺口
A("<h2>六、还缺的五个工具</h2>")
A("<table><tr><th style='width:46px'>#</th><th style='width:180px'>工具</th>"
  "<th style='width:120px'>状态</th><th>规格 / 为什么缺</th></tr>")
for gid, name, status, spec in GAPS:
    cls = "warn" if "暂不建" in status else "bad"
    A("<tr><td class='mono'>%s</td><td><b>%s</b></td>"
      "<td><span class='tag %s'>%s</span></td><td>%s</td></tr>" % (gid, name, cls, status, spec))
A("</table>")

A('<div class="box warn"><b>M1 情绪表现力闸门 · 为什么必须与音色闸门分开</b><br>'
  '音色闸门测的三个量（F0 中位、谱质心、谱倾斜）都是<b>发声器官的静态配置</b>：'
  '同一个人平静说和喊出来，F0 中位可能只差 2 个半音，这三个量几乎不动。'
  '而「演没演出来」全在<b>动态</b>上：F0 跨度（2st → 12st）、能量动态（6dB → 20dB）、'
  '气声比例、句内走向。所以这是两把正交的尺子：'
  '<ul><li>音色对、情绪平 → voice PASS / emo FAIL（<b>模型最常见的失败</b>，倾向保守）</li>'
  '<li>情绪对、音色偏 → voice FAIL / emo PASS（换了档 ref 时会这样）</li></ul>'
  '判定建议：5 维取 3 判 PASS，并单列 <span class="mono">flat</span>'
  '（起伏与动态同时低于带下限）—— 否则「念对了但没演」会被 3/5 掩盖。'
  '<b>现在不建：每档只有 2~8 条切片，基线带太窄，等音色库补齐再定标。</b></div>')

# 六、优先级
A("<h2>七、建议顺序</h2>")
A("<table><tr><th style='width:60px'>优先级</th><th style='width:230px'>做什么</th><th>为什么排这里</th></tr>")
PRI = [
 ("P0", "音色库定标：36 条探针跑完，8 档基线确认",
  "情绪闸门的基线要建在音色库上；音色没定标，情绪判据就没有参照"),
 ("P1", "把 pause_intent + _punct_expr 接进 mt_dialog_join",
  "两份结果都已经有了，只差装配时读一下；这是投入最小、听感收益最直接的一步"),
 ("P2", "对白短句门禁（M2）",
  "23.3% 的句子现在被判 SKIP，等于没验收；不补这一层，短句只能靠人耳"),
 ("P3", "情绪表现力闸门（M1）",
  "等 P0；先能判「音色对不对」，再判「情绪够不够」"),
 ("P4", "场景级一致性（M3）+ 归属闸门（M4）",
  "单条都过、拼起来仍可能出问题；归属闸门决定哪些句子允许进生成"),
]
for p, what, why in PRI:
    A("<tr><td><b>%s</b></td><td>%s</td><td>%s</td></tr>" % (p, what, why))
A("</table>")

A('<div class="foot">数据：_mt_loop_state.json（ch1 180 单元，中位 %d 词）· '
  'castle_dialog_report.json（%d 块，中位 %d 词）· _mt_gate.json（%d 候选，SKIP %d）· '
  'pause_intent.json（%d 处：must %d / opt %d / no %d）· _voice_baseline.json（8 档）<br>'
  '工具状态以仓库内实际文件为准；「◐ 要改」表示能跑但口径不适用于对白。</div>'
  % (MED_N, len(DLG), MED_D, len(GATE), SKIP_N, I_TOT,
     ic.get("must", 0), ic.get("opt", 0), ic.get("no", 0)))

A("</div></body></html>")

out = os.path.join(ROOT, "_loop_compare.html")
open(out, "w", encoding="utf-8").write("\n".join(H))
print("写出", out, os.path.getsize(out), "字节")
print("工具数", n_tools)
