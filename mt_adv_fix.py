# -*- coding: utf-8 -*-
"""副词「该慢没慢」→ 重生修复流水线。

链路：
  1. 读 LLM 双票共识（ds1 + ds2），得到每个单元「该慢的那一个副词」
  2. 用现有 prom 测它到底慢了没有（_adv_check.analyse → sps = dur/音节数）
  3. sps < SPS_SLOW 的单元：在文本里用破折号包住该词 → 重新生成（新 seed）
  4. 新音频再走 ASR → TextGrid → wpt → analyse，比较 before/after
  5. 写 _mt_adv_state.json；仍是 FAIL 的移交人工

为什么用破折号而不是 <rate>：
  实测（同 seed 只改一处，3 单元 × 5 条件）：
    原文               sps 0.140 / 0.112 / 0.160
    rate 0.50          0.220 / 0.208 / 0.260   ← 全部不达标
    破折号              0.320 / 0.288 / 0.340   ← 3/3 达标
  单词级 <rate> 在 dots.tts 上响应被衰减（factor 0.7 只出 +14%），
  破折号是让模型自己产生韵律边界，效果稳定。

用法：
  python mt_adv_fix.py --report                 # 只看现状
  python mt_adv_fix.py --run --limit 10         # 修复最差的 10 个
  python mt_adv_fix.py --run --units N0794,N0528 --seed 2024
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, "G:/_setup")
import mt_gen
import mt_loop
import _adv_check as AC
import _adv_align
import _adv_tts
import _f0_accent
import _guard
import _proso_batch

ROOT = "G:/_setup"
PLAN = "B:/mt-tts/data/plan/mt_plan3b.json"
VDIR = os.path.join(ROOT, "_adv_vote")
STATE = os.path.join(ROOT, "_mt_adv_state.json")
ASRPY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")
WPTPY = os.path.join(ROOT, "wpt_venv", "Scripts", "python.exe")
CFG = os.path.join(ROOT, "_wpt", "mt.yaml")
PROM_DIR = os.path.join(ROOT, "_wpt_out")

SPS_SLOW = 0.280      # ≥ 此值：确实慢了（时长路线）
SPS_FLAT = 0.180      # < 此值：被压扁
F0_PCT = 0.65         # ≥ 此值：句内内容词的 F0 分位，算真有音高重音
PY310 = "G:/Python310/python.exe"   # parselmouth 只装在这里

# ---- 回环判据（2026-10-27 改：loc 轴停用，只留时长轴 rel_z + 硬缺陷）----
# loc 是幅度型标量（词内 F0 p75 减本地上下文）。ProsodyEval(2025) 实测
# `logF0 RMSE` 这类指标与人耳 PMOS 的相关只有 r=0.30，是这一整类指标的上限，
# 不是公式挑错。Prosogram 又证明 <pitch> 抬的是寄存器不是轮廓
# （同 seed 配对副词滑幅 Δ+0.00，McNemar 全 50/50）。
# ⇒ 已从判定链移除。下面两个常量保留，只为兼容旧 state 里的字段名。
LOC_OK = 2.0
LOC_DELTA_MIN = 2.0
# 声纹：**只作记录，不作否决**（2026-10-26 21:40 重新标定后改）
# `_spk_calib.py` 实测 CAM++ 在 7 秒级短句上的噪声底：
#   同一条音频前半 vs 后半   中位 0.881  最低 0.346  p5 0.436
#   同一人不同句子 之间      中位 0.536  最低 -0.139 p5 -0.060
# ⇒ 裸余弦 0.29/0.34 完全落在「同一个人」的正常范围内，拿 0.55 当红线等于随机淘汰。
# 现在只在 **< SPK_VETO**（明显崩坏，连不同句子都算不上）时才拦；其余一律记录。
SPK_OK = 0.65
SPK_VETO = 0.15


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def load_votes(tags=("ds1", "ds2")):
    """返回 {aid: pick}，每 tag 合并该 tag 的全部分片。"""
    out = {}
    for t in tags:
        cur = {}
        for f in sorted(os.listdir(VDIR)):
            if not re.match(r"out_%s_p\d+\.json$" % re.escape(t), f):
                continue
            txt = open(os.path.join(VDIR, f), encoding="utf-8").read()
            m = re.search(r"\[.*\]", txt, re.S)
            if not m:
                continue
            for r in json.loads(m.group(0)):
                if "id" in r:
                    p = str(r.get("pick", "")).strip()
                    cur[str(r["id"])] = "none" if p.lower() == "none" else p
        out[t] = cur
    return out


def consensus(tags=("ds1", "ds2")):
    """双票一致才算数。返回 {uid: adverb}。"""
    v = load_votes(tags)
    aid2uid = {r["aid"]: r["uid"] for r in json.load(open(os.path.join(ROOT, "_adv_final.json"), encoding="utf-8"))}
    res = {}
    agree = dis = 0
    for aid, uid in aid2uid.items():
        ps = [v[t].get(aid) for t in tags]
        if any(p is None for p in ps):
            continue
        if len(set(p.lower() for p in ps)) != 1:
            dis += 1
            continue
        agree += 1
        if ps[0].lower() != "none":
            res[uid] = ps[0]
    return res, agree, dis


def load_plan():
    d = json.load(open(PLAN, encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("items", [])
    return {str(it["id"]): it for it in items}


def prom_for(uid, prefer=None):
    """找该单元的一个 prom（优先 prefer 指定的 seed）。返回 (path, seed) 或 (None, None)。"""
    if not os.path.isdir(PROM_DIR):
        return None, None
    cands = []
    for f in os.listdir(PROM_DIR):
        if not f.endswith(".prom") or "__" not in f:
            continue
        base = f[:-5]
        dpart, u = base.split("__", 1)
        if u != uid:
            continue
        seed = dpart.replace("_mt_raw_s", "")
        cands.append((seed, os.path.join(PROM_DIR, f)))
    if not cands:
        return None, None
    if prefer:
        for s, p in cands:
            if s == prefer:
                return p, s
    return cands[0][1], cands[0][0]


def measure(text, prom_path, uid, seed):
    """返回该单元目标副词的最佳测量（同一句可能多个同形词，取 sps 最大者）。"""
    rows = AC.read_prom(prom_path)
    got = AC.analyse(text, rows, uid, seed)
    if not got:
        return None
    ok = [g for g in got if g.get("sps") is not None]
    return max(ok, key=lambda g: g["sps"]) if ok else got[0]


def verdict_of(sps):
    if sps is None:
        return "MISSING"
    if sps >= SPS_SLOW:
        return "SLOWED"
    if sps >= SPS_FLAT:
        return "WEAK"
    return "FLAT"


def wrap_dash(text, word):
    pat = re.compile(r"(?<![A-Za-z'-])(%s)(?![A-Za-z'-])" % re.escape(word), re.I)
    m = pat.search(text)
    if not m:
        return None
    a, b = m.start(), m.end()
    before, after = text[:a].rstrip(), text[b:].lstrip()
    if before.endswith((",", ";", ":", "—", "–")):
        before = before[:-1].rstrip()
    if after[:1] in (",", ";", ":", "—", "–"):
        after = after[1:].lstrip()
    return before + " — " + m.group(1) + " — " + after


def build_state():
    plan = load_plan()
    targets, agree, dis = consensus()
    units = {}
    for uid, adv in sorted(targets.items()):
        p, seed = prom_for(uid)
        if not p:
            units[uid] = dict(adv=adv, advs=[adv], seed=None, sps=None,
                              verdict="NO_AUDIO", text=plan.get(uid, {}).get("text", ""))
            continue
        text = plan.get(uid, {}).get("text", "")
        g = measure(text, p, uid, seed)
        sps = g.get("sps") if g else None
        units[uid] = dict(adv=adv, advs=[adv], seed=seed,
                          sps=None if sps is None else round(sps, 3),
                          verdict=verdict_of(sps), text=text)
    return dict(created=time.strftime("%Y-%m-%d %H:%M:%S"), consensus=(agree, dis),
                threshold=dict(slow=SPS_SLOW, flat=SPS_FLAT), units=units)


def wav_of_prom(prom_path):
    base = os.path.splitext(os.path.basename(prom_path))[0]
    if "__" not in base:
        return None
    d, uid = base.split("__", 1)
    p = os.path.join(ROOT, d, uid + ".wav")
    return p if os.path.exists(p) else None


def f0_rank(prom_path, wav, word):
    """调 _f0_accent.py 单条接口，返回 dict（rank/loc/lin/rng）。"""
    if not prom_path or not wav:
        return None
    try:
        r = subprocess.run([PY310, os.path.join(ROOT, "_f0_accent.py"),
                            "--prom", prom_path, "--word", word, "--wav", wav],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=240)
        lines = [x for x in (r.stdout or "").strip().splitlines() if x.startswith("{")]
        if not lines:
            return None
        return json.loads(lines[-1])
    except Exception as e:
        log("  !! F0 读取失败 %s: %s" % (word, e))
        return None


# ================= 2026-10-27 回环补全 =================
# 三个断点（见 docs/ADVERB_STRESS.md §19、§20）：
#   ① 生成端不带单词级标签 ⇒ 重生永远等于"无标签重生"，对时长 0% 有效
#   ② 验收只看 loc（F0 轴）⇒ 用 rate 做的正确修复会被判 WATCH 无限重试
#   ③ 没有同 seed 无标签对照 ⇒ 换 take 噪声（voiced 10~38%、loc 1.4~1.8 半音）盖过效应
# 现在：生成两组（对照 + 标签）、三道闸门（音质/音色/韵律）、双轴验收。

RATE_FACTOR = 0.70          # 用户定案：单轴，不叠加
PITCH_SEMI = 9
DUR_GAIN_MIN = 1.25         # 副词 voiced 相对同 seed 无标签对照的增益下限（已降级为展示值）
# ★ 时长轴换 span（2026-10-27 05:50）。纯净零分布（同条目、不同 seed、两条都无标签，
#   n=46 对，ctl vs ctl）：span 比 p50 1.00 / p90 1.35 / **p95 1.44** / max 1.80
#   ⇒ 阈值必须 ≥1.45 才有意义，取 1.50（p95 再留一个刻度）。
#   同期 voiced 比 p50 1.05 / p90 2.20 / **p95 3.00** / max 8.22 —— 整条落在噪声里，
#   旧阈值 1.25 连 p60 都不到，之前那批「时长×1.30 达标」全是抖出来的。
SPAN_GAIN_MIN = 1.50       # ⚠️ 已退役：见下方 REL_OK（比值型，会被分母塌陷骗）
SPAN_GAIN_MAX = 2.00
# ★★★ 时长轴改为「绝对水位」（2026-10-27 17:30，真人母带锚点标定）
# 母带 302 条切片 → wpt 对齐 → 160 句 / 930 内容词。
#   真人「句内最长词」rel（词 sps ÷ 句内内容词 sps 中位）：
#       p5 1.12  p25 1.29  p50 1.71  p90 2.50  p95 2.77
#   真人普通词 rel：p50 1.00（定义），p90 1.71
#   真人「句内最高 loc 词」rel：p50 1.00（说明音高重音不带时长成分）
# 零分布（同 seed 无标签对照的 rel，n=51）：p50 0.86 / p90 1.33 / p95 1.38 / max 1.89
#   ⇒ REL_OK 取 1.40，正落在对照 p95 之上（假阳性 4%）
# 为什么必须是绝对水位而不是「相对同 seed 对照的比值」：
#   N0794 s2041 跨度×1.46 看着达标，但对照自己的 rel 只有 0.34（副词被读成半个音节），
#   标签版 rel 0.50 —— 仍然远低于真人。这是第 7 次「分母塌陷」。
REL_OK = 1.40           # 旧口径（裸 rel，未做音节校正）—— 仅保留展示
# ★★★ 2026-10-27 17:50：时长轴改用 rel_z（音节校正）。
#   裸 rel 的问题是「音节多的副词天生 sps 小」，而 -ly 副词全是 2~5 音节，
#   校正前后有 17/55 条的 nsyl 变化（cmudict 装上之后）。
#   零分布（同 seed 无标签对照，n=51）：rel_z p50 +0.35 / p90 +1.19 / p95 +1.47 / max +2.54
#   阈值取 1.6（p95 上留一格）：对照假阳性 2/51 = 3.9%，标签版命中 9/94 = 9.6%。
#   参照锚点：真人「句内最长词」rel_z p50 +1.19 / p90 +2.41。
#   ⚠️ 噪声上沿（1.47）高于真人目标（1.19）——「单条 take 的时长起伏」比
#      「标签带来的增量」更大，所以时长轴只能当顺带捡，不能当主力。
REL_Z_OK = 1.6
# 整句有声时长不得超对照 15%：rate 标签会同时拖慢整句，整句变慢不是重音。
# 实测 51 对：整句比 p50 0.98 / p90 1.32；真正达标的 5 条整句比 0.68~1.12。
FULL_GAIN_MAX = 1.15
# 抬到气声不是重音：有声帧相对对照的下限 + 绝对下限
VOICED_KEEP_MIN = 0.60
VOICED_ABS_MIN = 0.12       # 秒
# ★ 本轮自动采纳只认 loc（F0）轴（2026-10-27 05:45）。
#   loc 轴：噪声底 1.8 半音（用户口径），实测效应 +5.8/+7.1/+4.2/+5.0/+3.2 —— 可判。
#   span 轴：零分布 p95 1.35 / max 1.80，而实测通过值正好是 1.36~1.80，
#            全落在噪声带上；且 ×1.80 已超 rate 0.70 的理论上限 1.43，
#            无法排除「靠停顿凑时长」⇒ 不自动收，留给试听页人耳裁决。
#   要放开就把它改成 ("F0", "跨度")。
ADOPT_AXIS_PREFIX = ("F0", "副词时长")
SHARE_KEEP = 0.98           # 副词时长份额不许比对照降超 2%
CTL_VOICED_MIN = 0.10       # 对照的副词至少要有 100ms 发声，否则比值是噪声
DUR_GAIN_MAX = 3.0          # 超过 3 倍视为对齐错位（零分布 max 仅 1.59）


def adv_position(text, adv):
    """句中（后面还有实词）→ "mid"；句末/后无实词 → "end"。"""
    try:
        tw = _adv_align.text_words(text)
    except Exception:
        return "mid"
    idx = [i for i, t in enumerate(tw) if t["key"] == adv.lower()]
    if not idx:
        return "mid"
    after = [t for t in tw[idx[-1] + 1:]
             if t["is_word"] and t["key"] not in _f0_accent.FUNC]
    return "end" if not after else "mid"


def tagged_text(text, adv):
    """给副词包单词级标签。返回 (文本, 条件名)。句中 rate 0.70、句末 pitch +9。"""
    pos = adv_position(text, adv)
    if pos == "end":
        return _adv_tts.instruction(text, adv, "p9"), "p9"
    return _adv_tts.instruction(text, adv, "r7"), "r7"


def _span(rec):
    """词的对齐跨度（t1−t0），秒。`_adv_prom.measure_one` 的行自带 t0/t1。"""
    if not rec:
        return None
    t0, t1 = rec.get("t0"), rec.get("t1")
    if t0 is None or t1 is None:
        return None
    d = float(t1) - float(t0)
    return d if d > 0 else None


def _relz_pct(v):
    """rel_z 在真人 931 个内容词中的百分位（拿不到参照就返回 None）。"""
    try:
        import _align_lib as AL
        bl = AL.load_baseline()
        return AL.pct_of(v, bl["ref"]["all"]["relz_sorted"])
    except Exception:
        return None


def judge_cand(rec, ctl, guards):
    """回环候选判定：闸门 → 气声保护 → 音高轴 → 时长轴。

    REJECT  闸门挂了（音质/音色/韵律）—— 数字再好看也不要
    PASS    音高轴 loc ≥ 2.0 且 比对照高 ≥2.0
            或 时长轴 对齐跨度 ≥ 对照 ×1.35（零分布 p95）
    WATCH   两条轴都没达标

    ★ loc 轴必须看差值：绝对 loc ≥2.0 但对照也 ≥2.0 时不算数
      （N0112 候选 2.62 / 对照 3.49；N0794 候选 3.39 / 对照 2.98）——
      这类条目本来就有音高起伏，收下来只是换了个「碰巧更好」的 take。

    ★ 时长轴改用「对齐跨度 t1−t0」而不是 voiced 帧数（2026-10-27 05:40）。
      零分布（两版都无标签、纯换 take，n=52，`_adv_prom` 实测）：
          span  比  p50 1.00  p90 1.25  p95 1.35  max 1.80
          voiced比  p50 0.96  p90 2.05  p95 2.70  max 4.00
      voiced 比整条落在噪声里 —— 之前「×1.30 / ×1.33 达标」全是抖出来的
      （N0226 2041 span×1.00 却 voiced×1.30；N0347 span×0.78 却 voiced×1.40）。
      span 比才看得见真效果，阈值取噪声 p95 = 1.35。

    ★ 「抬到气声」不是重音：F0 抬高但有声帧锐减的 take（N0266 ×0.32 /
      N0718 ×0.35 / N0723 ×0.29，绝对有声 0.145/0.040/0.035s）是气声/破音，
      loc 会被几个尖峰帧顶到 +9，必须拦掉。
    """
    if guards and guards.get("verdict") == "FAIL":
        return "REJECT", "闸门:" + "、".join(
            "%s(%s)" % (k, (guards.get(k) or {}).get("why", ""))
            for k in guards.get("failed") or [])
    if rec is None:
        return "WATCH", "无测量"
    # ---- 气声保护（两条轴共用）----
    if ctl and (ctl.get("voiced") or 0) > 0:
        vg = (rec.get("voiced") or 0) / max(ctl["voiced"], 1e-9)
        if (rec.get("voiced") or 0) < VOICED_ABS_MIN or vg < VOICED_KEEP_MIN:
            return "WATCH", "有声帧×%.2f 仅 %.3fs（抬到气声）" % (
                vg, rec.get("voiced") or 0)
    # ---- loc 判据已于 2026-10-27 停用 ----
    # 幅度型音高指标与人耳相关仅 r=0.30（ProsodyEval 2025），且 Prosogram 证明
    # 它抬的是寄存器不是轮廓（同 seed 配对副词滑幅 Δ+0.00）。音高改由 TTSDS2
    # 的 PROSODY 因子做批次级验收；单条只看时长轴 rel_z。
    if ctl:
        cv = ctl.get("voiced") or 0.0
        # ⚠️ 对照自己要是没发声，比值毫无意义（N0602 对照 0.045s ⇒ 算出 ×10.00）。
        if cv < CTL_VOICED_MIN:
            return "WATCH", "对照副词仅 %.3fs，比值不可信" % cv
        g = (rec.get("voiced") or 0) / max(cv, 1e-9)
        # ---- 时长轴：rel_z（音节校正后的时长水位）----
        rz = rec.get("rel_z")
        fl = rec.get("speech")
        fc = ctl.get("speech")
        fg = (fl / fc) if (fl and fc) else None
        if rz is None:
            return "WATCH", "rel_z 不可测（有声×%.2f）" % g
        if fg is not None and fg > FULL_GAIN_MAX and rz < REL_Z_OK:
            # 整句变慢但副词没相对变长 ⇒ 只是拖慢，不是重音
            return "WATCH", "整句×%.2f 但副词 z=%+.2f（拖慢不是重音）" % (fg, rz)
        if rz >= REL_Z_OK:
            p = _relz_pct(rz)
            return "PASS", "副词时长 z=%+.2f%s%s" % (
                rz, ("（真人 p%.0f）" % p) if p is not None else "",
                ("（整句×%.2f）" % fg) if fg else "")
        return "WATCH", "副词 z=%+.2f 有声×%.2f（对照）" % (rz, g)
    return "WATCH", "F0平淡"


def judge(rec, human=None):
    """判定（2026-10-27 改：loc 判据停用）。

    **loc 为什么停用**：它是幅度型标量（词内 F0 p75 减本地上下文）。
    ProsodyEval(2025) 实测 `logF0 RMSE` 这类指标与人耳 PMOS 的相关只有 **r=0.30**，
    是这一整类指标的上限，不是公式挑错。Prosogram 又证明它抬的是寄存器不是轮廓
    （同 seed 配对副词滑幅 Δ+0.00）。改用 TTSDS2 的 PROSODY 因子做**批次级**验收
    （分布级 Wasserstein，与人耳平均 Spearman 0.67）。

    单条判据只剩**时长轴** rel_z —— 它是句内归一 + 音节校正过的，
    真人被强调的词落在 p90 附近，对照 p95 只有 +1.47。

        LOCKED  人耳已确认合格           → 永不重生
        FIX     ABSENT / SWALLOW / 换人  → 物理缺陷，才烧生成
        PASS    rel_z ≥ REL_Z_OK        → 副词真的拖长了
        WATCH   其余                      → 平淡，进送听清单，不烧生成
    """
    if human == "ok":
        return "LOCKED", "人耳已确认"
    if not rec:
        return "FIX", "无测量"
    v = rec.get("verdict")
    if v in ("NO_AUDIO", "UNMEASURED"):
        return "FIX", str(v)
    if (rec.get("voiced") or 0) < 0.06:
        # ⚠️ voiced（有声帧）≠ 有声。气声/清音段有能量但检不到基频，
        # 强度可能完全正常（N0226：区间 0.80 s、中位 57 dB、峰 73 dB，voiced 只有 0.05 s）。
        # 用 rms_x（词内/全句 RMS）区分「真没声」和「有声无基频」。
        if (rec.get("rms_x") if rec.get("rms_x") is not None else 1.0) >= 0.35:
            return "WATCH", "气声(有声无基频)"
        return "FIX", "ABSENT"
    if (rec.get("rms_x") if rec.get("rms_x") is not None else 1) < 0.35 \
            and (rec.get("dur_z") or 0) < -1.0:
        return "FIX", "SWALLOW"
    if rec.get("spk") is not None and rec["spk"] < SPK_VETO:
        return "FIX", "换人%.2f" % rec["spk"]
    rz = rec.get("rel_z")
    if rz is None:
        return "WATCH", "rel_z 不可测"
    if rz >= REL_Z_OK:
        p = _relz_pct(rz)
        return "PASS", "副词时长 z=%+.2f%s" % (
            rz, ("（真人 p%.0f）" % p) if p is not None else "")
    return "WATCH", "副词 z=%+.2f（时长不足）" % rz


def measure_units(pairs, tag="cur"):
    """pairs = [(uid, text, wav, prom, advs)] → {uid: rec}。整批一个子进程。"""
    if not pairs:
        return {}
    man = [dict(uid=u, text=t, wav=w, prom=p, advs=ad) for u, t, w, p, ad in pairs]
    mf = os.path.join(ROOT, "_adv_man_%s.json" % tag)
    of = os.path.join(ROOT, "_adv_res_%s.json" % tag)
    json.dump(man, open(mf, "w", encoding="utf-8"), ensure_ascii=False)
    if os.path.exists(of):
        os.remove(of)
    t0 = time.time()
    r = subprocess.run([PY310, os.path.join(ROOT, "_adv_prom.py"),
                        "--batch", mf, "--out", of],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    if not os.path.exists(of):
        log("!! 测量失败 " + (r.stderr or r.stdout or "")[-300:])
        return {}
    log("测量 %d 条，%.1f 秒" % (len(pairs), time.time() - t0))
    return {str(x["uid"]): x for x in json.load(open(of, encoding="utf-8"))}


def spk_check(pairs, tag="cur"):
    """pairs = [(uid, 原版wav, 候选wav)] → {uid: {spk, verdict}}。"""
    if not pairs:
        return {}
    man = [dict(uid=u, a=a, b=b) for u, a, b in pairs]
    mf = os.path.join(ROOT, "_spk_man_%s.json" % tag)
    of = os.path.join(ROOT, "_spk_res_%s.json" % tag)
    json.dump(man, open(mf, "w", encoding="utf-8"), ensure_ascii=False)
    if os.path.exists(of):
        os.remove(of)
    r = subprocess.run([PY310, os.path.join(ROOT, "_spk_gate.py"),
                        "--manifest", mf, "--out", of],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    if not os.path.exists(of):
        log("!! 声纹检测失败 " + (r.stderr or r.stdout or "")[-300:])
        return {}
    return {str(x["uid"]): x for x in json.load(open(of, encoding="utf-8"))}


def prom_wav(uid):
    """返回 (prom, wav)，**两者必须来自同一个 seed 目录**，s1234 优先。

    坑：`_mt_raw_s1234/N0419.wav` 存在，但 `_mt_raw_s1234__N0419.prom` 不存在
    （该单元的 prom 只在 s42）。若 wav 和 prom 取不同 seed，词区间会整体错位，
    N0419 会被算成 loc −4.58、voiced 0.33（实际是 −0.23 / 正常）。
    """
    if not os.path.isdir(PROM_DIR):
        return None, None
    best = None
    for f in sorted(os.listdir(PROM_DIR)):
        if not f.endswith(".prom") or "__" not in f:
            continue
        pre, u = f[:-5].split("__", 1)
        if u != uid or not (pre.startswith("_mt_raw_s") or pre == "_mt_pick"):
            continue
        w = os.path.join(ROOT, pre, uid + ".wav")
        if not os.path.exists(w):
            continue
        rank = -1 if pre == "_mt_pick" else (0 if pre.endswith("s1234") else 1)
        if best is None or rank < best[0]:
            best = (rank, os.path.join(PROM_DIR, f), w)
    return (best[1], best[2]) if best else (None, None)


def orig_wav(uid):
    """当前交付的那一版（_mt_pick 优先）。声纹闸门就是对它比。"""
    pk = os.path.join(ROOT, "_mt_pick", uid + ".wav")
    if os.path.exists(pk):
        return pk
    _p, w = prom_wav(uid)
    if w:
        return w
    for pre in ("s1234", "s42", "srate"):
        p = os.path.join(ROOT, "_mt_raw_" + pre, uid + ".wav")
        if os.path.exists(p):
            return p
    return None


def advise(x):
    return x.get("advs") or [x["adv"]]


def att_prom(uid, seed):
    """重生 take 对应的 prom（`_mt_adv_prom_<seed>/<uid>.prom`）。"""
    p = os.path.join(ROOT, "_mt_adv_prom_%s" % seed, uid + ".prom")
    return p if os.path.exists(p) else None


def active_pair(uid, x):
    """当前"在用"的 (prom, wav)。已采纳重生版时用采纳版，否则用原版。"""
    act = x.get("active") or {}
    w = act.get("wav")
    p = act.get("prom")
    if w and os.path.exists(w) and p and os.path.exists(p):
        return p, w
    return prom_wav(uid)


def human_ok(x):
    return (x.get("human") or "").lower() == "ok"


def scan_all(st, uids=None):
    """对全部单元按新判据现算（不看旧的 sps verdict）。返回 {uid: rec}。"""
    us = st["units"]
    pairs = []
    for u, x in sorted(us.items()):
        if uids and u not in uids:
            continue
        p, w = active_pair(u, x)
        if not p or not w:
            continue
        pairs.append((u, x["text"], w, p, advise(x)))
    return measure_units(pairs, "scan")


def analyse_existing(st, uids):
    """第一步：先量现有版本，能放过就放过，省掉重生。"""
    us = st["units"]
    got = scan_all(st, set(uids))
    skipped = []
    for u in list(uids):
        x = us[u]
        rec = got.get(u)
        j, by = judge(rec, "ok" if human_ok(x) else None)
        x["m2"] = None if not rec else dict(
            loc=rec.get("loc"), dur_z=rec.get("dur_z"), voiced=rec.get("voiced"),
            rms_x=rec.get("rms_x"), verdict=rec.get("verdict"))
        x["judge"], x["judge_by"] = j, by
        if j in ("PASS", "LOCKED"):
            skipped.append(u)
            uids.remove(u)
    log("第一步分析：%d 个已达标，%d 个需处理" % (len(skipped), len(uids)))
    for u in skipped:
        x = us[u]
        log("  放过 %-8s %-13s loc=%-6s %s"
            % (u, x["adv"], (x.get("m2") or {}).get("loc"), x.get("judge_by")))
    return skipped


def cws_for(wav, prom, text):
    """取全句内容词明细（word_gate 需要逐词 voiced）。"""
    try:
        import _adv_prom
        return _adv_prom.measure_one(wav, prom, text)
    except Exception as e:
        log("  !! 词明细失败 %s: %s" % (os.path.basename(wav), str(e)[:80]))
        return None


def _asr_and_prom(wav_dir, prom_dir, tag, uids):
    """一个目录：ASR → TextGrid → wpt。返回成功的 uid 列表。"""
    stage = os.path.join(ROOT, "_mt_adv_stage_%s" % tag)
    for d in (stage, prom_dir):
        os.makedirs(d, exist_ok=True)
    wavs = [os.path.join(wav_dir, u + ".wav") for u in uids
            if os.path.exists(os.path.join(wav_dir, u + ".wav"))]
    if not wavs:
        log("!! %s 无 wav" % tag)
        return []
    asr_json = os.path.join(ROOT, "_adv_asr_%s.json" % tag)
    t0 = time.time()
    r = subprocess.run([ASRPY, os.path.join(ROOT, "_asr_lib.py"), "--out", asr_json] + wavs,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=3600)
    if r.returncode != 0 or not os.path.exists(asr_json):
        log("!! ASR 失败 %s %s" % (tag, (r.stderr or "")[-200:]))
        return []
    asr = {os.path.normpath(k): v
           for k, v in json.load(open(asr_json, encoding="utf-8")).items()}
    staged = 0
    for p in wavs:
        k = os.path.normpath(p)
        if k not in asr:
            continue
        base = os.path.splitext(os.path.basename(p))[0]
        mt_loop.write_textgrid(os.path.join(stage, base + ".TextGrid"),
                               asr[k]["dur"], asr[k]["words"])
        shutil.copy2(p, os.path.join(stage, base + ".wav"))
        staged += 1
    log("%s ASR %d 条，%.1f 分钟" % (tag, len(asr), (time.time() - t0) / 60))
    t0 = time.time()
    r = subprocess.run([WPTPY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                        "-j", "4", "-c", CFG, "-o", prom_dir, stage],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore", timeout=3600)
    log("%s wpt %d 条，%.1f 分钟 rc=%d" % (tag, staged, (time.time() - t0) / 60, r.returncode))
    return [u for u in uids if os.path.exists(os.path.join(prom_dir, u + ".prom"))
            and os.path.exists(os.path.join(stage, u + ".wav"))]


GEN_CHUNK = 6   # 分块生成：块间检查时限，超时停手，已生成的文件全部保留
MIN_BATCH = 10  # 批次体检的最少条数（2 条实测 59.11，纯样本量假低分）


def _gen_chunked(items, tag, outdir, seed, deadline, label):
    """分块生成。`gen_batch` 是**整批一个 subprocess**，中途超时整批全丢，
    所以按 GEN_CHUNK 切块，块间看 `deadline`（`--minutes` 换算）。

    停下时已完成的那几块照样落盘，下一轮 `run_round` 会按「文件存在」跳过，
    所以断点续跑是免费的。
    """
    if not items:
        return 0
    n_ok, k = 0, 0
    for i in range(0, len(items), GEN_CHUNK):
        if deadline and time.time() > deadline:
            log("  ⏱ 到时限，停止生成（%s）：完成 %d/%d 条，剩下的下轮续跑"
                % (label, n_ok, len(items)))
            break
        chunk = items[i:i + GEN_CHUNK]
        k += 1
        t0 = time.time()
        ok = mt_gen.gen_batch(chunk, "%s_%d" % (tag, k), outdir, seed)
        n_ok += ok
        log("  %s 块%d：%d/%d 条，%.1f 分钟（累计 %d/%d）"
            % (label, k, ok, len(chunk), (time.time() - t0) / 60, n_ok, len(items)))
    return n_ok


def run_round(st, uids, seed, a):
    """一轮：**先体检、后打标签**（2026-10-27 用户要求把韵律环节放到加 pitch/rate 前面）。

    旧顺序是「标签版 + 同 seed 无标签对照」一起生成、再判定 —— 标签已经花掉了，
    体检只能事后否决。新顺序把体检提到打标签之前：

        ① 只生成无标签版（每个单元 1 次生成）
        ② 对这一批跑 TTSDS2 PROSODY（官方分布级口径）
           没过门槛 ⇒ 本轮**不打标签**，直接返回（这批的韵律不是标签能修的）
        ③ 无标签版自己就够长（rel_z ≥ 1.6）的，直接收，**不打标签**
        ④ 剩下的才打 pitch+rate，再判时长轴

    ★ 门控只认**批次分**，不认单条分。单条韵律分的纯换 take 抖动
      （零分布 ctl→ctl：低层 +2.44 / 高层 −2.38）比标签效应（−2.61）还大，
      拿单条当闸门就是拿噪声当判据。见 docs §33。
    """
    us = st["units"]
    cdir = os.path.join(ROOT, "_mt_adv_ctl_%d" % seed)
    cprom = os.path.join(ROOT, "_mt_adv_prom_ctl_%d" % seed)
    tdir = os.path.join(ROOT, "_mt_adv_s%d" % seed)
    tprom = os.path.join(ROOT, "_mt_adv_prom_%d" % seed)
    for d in (cdir, tdir):
        os.makedirs(d, exist_ok=True)

    deadline = getattr(a, "deadline", None)

    # ---------- ① 只生成无标签版 ----------
    todo = [u for u in uids if not os.path.exists(os.path.join(cdir, u + ".wav"))]
    if todo:
        _gen_chunked([(u, us[u]["text"], 1.0) for u in todo],
                     "advc%d" % seed, cdir, seed, deadline, "无标签版")
    else:
        log("seed %d：无标签版都在，直接复用" % seed)

    live_c = _asr_and_prom(cdir, cprom, "c%d" % seed, uids)
    live = [u for u in uids if u in live_c]
    pairs_c = [(u, us[u]["text"], os.path.join(cdir, u + ".wav"),
                os.path.join(cprom, u + ".prom"), advise(us[u])) for u in live]
    gotc = measure_units(pairs_c, "c%d" % seed) if pairs_c else {}

    # ---------- ② 批次韵律体检（在打标签之前）----------
    # ★ 批次分是**分布距离**，样本太少时分布退化成几个点，分数会被压得极低：
    #   实测 2 条音频得 PROSODY 59.11（hubert 19.8），而同样素材 16~19 条是 83~85。
    #   这是口径的边界，不是素材的问题 ⇒ 少于 MIN_BATCH 条就**不判**，放行。
    if getattr(a, "proso_gate", 0) and live and len(live) < MIN_BATCH:
        log("  韵律体检跳过：本批只有 %d 条 < %d，分布距离不可靠（放行，不打标签也照走）"
            % (len(live), MIN_BATCH))
    elif getattr(a, "proso_gate", 0) and live:
        try:
            sc = _proso_batch.score_dir(cdir)
        except Exception as e:
            sc = dict(prosody=None, why=str(e)[:90])
        pv = sc.get("prosody")
        if pv is None:
            log("  韵律体检跳过：%s" % sc.get("why"))
        else:
            det = " ".join("%s=%.1f" % (k, v) for k, v in sc.items()
                           if k in _proso_batch.FACTORS and isinstance(v, float))
            log("  韵律体检（无标签批 %d 条）：PROSODY %.2f  [%s]  门槛 %.1f"
                % (sc.get("n") or len(live), pv, det, a.proso_gate))
            if pv < a.proso_gate:
                log("  ⇒ 未过门槛，本轮**不打标签**（这批的韵律不是标签能修的）")
                for u in live:
                    us[u].setdefault("attempts", []).append(dict(
                        seed=seed, cond="none", judge="WATCH",
                        by="韵律体检 %.2f < %.1f（未打标签）" % (pv, a.proso_gate),
                        voiced=None if not gotc.get(u) else gotc[u].get("voiced"),
                        wav=os.path.join(cdir, u + ".wav"), ctl_wav=None))
                return list(live)

    # ---------- ③ 无标签版已经够长的，直接收 ----------
    need, done = [], []
    for u in live:
        rec = gotc.get(u) or {}
        rz = rec.get("rel_z")
        if rz is not None and rz >= REL_Z_OK:
            us[u]["cand"] = dict(judge="PASS", by="无标签已达标 rel_z=%+.2f" % rz,
                                 seed=str(seed), wav=os.path.join(cdir, u + ".wav"))
            us[u].setdefault("attempts", []).append(dict(
                seed=seed, cond="none", judge="PASS",
                by="无标签已达标 rel_z=%+.2f" % rz,
                voiced=rec.get("voiced"), share=rec.get("share"),
                wav=os.path.join(cdir, u + ".wav"), ctl_wav=None))
            log("  %-8s → PASS（无标签，未烧标签） rel_z=%+.2f" % (u, rz))
            done.append(u)
        else:
            need.append(u)
    if not need:
        return [u for u in uids if u not in done]

    # ---------- ④ 剩下的才打标签 ----------
    todo_t = [u for u in need if not os.path.exists(os.path.join(tdir, u + ".wav"))]
    if todo_t:
        tag_items = []
        for u in todo_t:
            txt, cond = tagged_text(us[u]["text"], us[u]["adv"])
            tag_items.append((u, txt, 1.0))
        _gen_chunked(tag_items, "advt%d" % seed, tdir, seed, deadline, "标签组")
    else:
        log("seed %d：标签版都在，直接复用（%d 个）" % (seed, len(need)))

    live_t = _asr_and_prom(tdir, tprom, "t%d" % seed, need)
    pairs_t = [(u, us[u]["text"], os.path.join(tdir, u + ".wav"),
                os.path.join(tprom, u + ".prom"), advise(us[u])) for u in live_t]
    got = measure_units(pairs_t, "t%d" % seed) if pairs_t else {}

    still = [u for u in uids if u not in done]
    for u in need:
        if u not in live_t:
            log("  !! %-8s 标签版无产出" % u)
            continue
        rec, ctl = got.get(u), gotc.get(u)
        cw_t = cws_for(os.path.join(tdir, u + ".wav"),
                       os.path.join(tprom, u + ".prom"), us[u]["text"])
        cw_c = cws_for(os.path.join(cdir, u + ".wav"),
                       os.path.join(cprom, u + ".prom"), us[u]["text"])
        g = _guard.all_guards(
            os.path.join(tdir, u + ".wav"), os.path.join(tprom, u + ".prom"),
            us[u]["text"],
            ctl=os.path.join(cdir, u + ".wav"),
            ctl_prom=os.path.join(cprom, u + ".prom"),
            delivered=orig_wav(u), exclude_uid=u,
            cand_cws=cw_t, ctl_cws=cw_c, adv=us[u]["adv"].lower())
        j, by = judge_cand(rec, ctl, g)
        att = dict(seed=seed, cond=tagged_text(us[u]["text"], us[u]["adv"])[1],
                   judge=j, by=by,
                   loc=None if not rec else rec.get("loc"),
                   voiced=None if not rec else rec.get("voiced"),
                   share=None if not rec else rec.get("share"),
                   loc_ctl=None if not ctl else ctl.get("loc"),
                   voiced_ctl=None if not ctl else ctl.get("voiced"),
                   share_ctl=None if not ctl else ctl.get("share"),
                   guards=dict(verdict=g.get("verdict"), failed=g.get("failed"),
                               warned=g.get("warned"),
                               words=(g.get("words") or {}).get("why"),
                               audio=g.get("audio", {}).get("why"),
                               speaker=g.get("speaker", {}).get("margin"),
                               prosody=g.get("prosody", {}).get("why")),
                   wav=os.path.join(tdir, u + ".wav"),
                   ctl_wav=os.path.join(cdir, u + ".wav"))
        us[u].setdefault("attempts", []).append(att)
        brief = "rel_z=%s→%s voiced=%s→%s 闸门=%s" % (
            (ctl or {}).get("rel_z"), (rec or {}).get("rel_z"),
            att["voiced_ctl"], att["voiced"], g.get("verdict"))
        if j == "PASS":
            # ⚠️ 只记「候选」状态，**不覆盖** us[u]["judge"] ——
            # 那个字段表示「当前交付版」的状态，由 classify() 维护。
            us[u]["cand"] = dict(judge="PASS", by=by, seed=str(seed),
                                 wav=os.path.join(tdir, u + ".wav"))
            still = [x for x in still if x != u]
            log("  %-8s → PASS  %s" % (u, brief))
        elif j == "REJECT":
            log("  %-8s → REJECT %s | %s" % (u, brief, by))
        else:
            log("  %-8s → 仍弱  %s" % (u, brief))
    return still


def _md5(p):
    import hashlib
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_state(a):
    if os.path.exists(STATE) and not getattr(a, "rebuild", False):
        st = json.load(open(STATE, encoding="utf-8"))
        log("沿用已有状态 %s" % STATE)
    else:
        st = build_state()
    return st


def classify(st, uids=None):
    """全量现算 → 分桶。返回 (buckets, recs)。不看旧的 sps verdict。"""
    us = st["units"]
    recs = scan_all(st, uids)
    b = dict(PASS=[], LOCKED=[], WATCH=[], FIX=[], NO_AUDIO=[])
    for u, x in sorted(us.items()):
        if uids and u not in uids:
            continue
        rec = recs.get(u)
        j, by = judge(rec, "ok" if human_ok(x) else None)
        x["m2"] = None if not rec else dict(
            loc=rec.get("loc"), dur_z=rec.get("dur_z"), voiced=rec.get("voiced"),
            rms_x=rec.get("rms_x"), verdict=rec.get("verdict"))
        x["judge"], x["judge_by"] = j, by
        (b["NO_AUDIO"] if rec is None else b[j]).append(u)
    return b, recs


def cmd_run(a):
    st = load_state(a)
    us = st["units"]
    only = a.units or None

    b, recs = classify(st, only)
    log("全量分类：PASS %d / LOCKED %d / WATCH %d / FIX %d / 无音频 %d"
        % (len(b["PASS"]), len(b["LOCKED"]), len(b["WATCH"]), len(b["FIX"]),
           len(b["NO_AUDIO"])))
    for u in b["FIX"]:
        log("  FIX   %-8s %-13s %s" % (u, us[u]["adv"], us[u].get("judge_by")))
    for u in sorted(b["WATCH"], key=lambda z: ((us[z].get("m2") or {}).get("loc") or -9)):
        x = us[u]
        log("  WATCH %-8s %-13s loc=%s" % (u, x["adv"], (x.get("m2") or {}).get("loc")))

    uids = list(b["FIX"])
    if a.fix_watch:
        uids += [u for u in b["WATCH"] if us[u].get("judge") != "LOCKED"]
    if a.limit:
        uids = uids[:a.limit]
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if not uids:
        log("无需重生。回环结果：达标 %d / 平淡 %d（不烧生成）"
            % (len(b["PASS"]) + len(b["LOCKED"]), len(b["WATCH"])))
        return

    seeds = [int(x) for x in str(a.seeds).split(",") if x.strip()]
    seeds = seeds[:a.max_gen]
    if not seeds:
        log("seeds 为空 ⇒ 只做分析，不重生。待处理 %d 个：%s"
            % (len(uids), ",".join(uids)))
        return
    log("需重生 %d 个，最多 %d 次，seeds=%s，原文不动（只加单词级标签）"
        % (len(uids), len(seeds), seeds))

    for k, seed in enumerate(seeds, 1):
        if not uids:
            break
        log("=== 第 %d/%d 次（seed %d）===" % (k, len(seeds), seed))
        uids = run_round(st, uids, seed, a)
        st["units"] = us
        st["last_run"] = dict(mode="regen", attempt=k, seed=seed,
                              n=len(us), still=len(uids),
                              at=time.strftime("%Y-%m-%d %H:%M:%S"))
        json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if getattr(a, "deadline", None) and time.time() > a.deadline:
            log("⏱ 到时限（%.0f 分钟），本轮提前收工，未完成的留给下一轮"
                % a.minutes)
            break

    ok_n = sum(1 for x in us.values() if x.get("judge") in ("PASS", "LOCKED"))
    log("结束：达标 %d / 仍不合格 %d（%s）"
        % (ok_n, len(uids), ",".join(uids) if uids else "无"))
    if getattr(a, "deadline", None) and time.time() > a.deadline:
        # 时限截断 ⇒ **不**把它们标成 MANUAL（那是「跑完一整轮仍不合格」的语义），
        # 否则下一轮会把它们当成人耳待听清单，掩盖「还没试过」这个事实。
        log("（时限截断，未完成的不标记 MANUAL）")
    else:
        for u in uids:
            us[u]["judge"] = "MANUAL"
    st["units"] = us
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def cmd_report(a):
    st = load_state(a)
    us = st["units"]
    b, recs = classify(st, a.units or None)
    n = sum(len(v) for v in b.values())
    print("=== 回环漏斗（%d 条）===" % n)
    print("  预测（LLM 双票）        %3d" % len(us))
    print("  无音频                  %3d" % len(b["NO_AUDIO"]))
    print("  物理缺陷 FIX            %3d" % len(b["FIX"]))
    print("  F0 达标 PASS            %3d" % len(b["PASS"]))
    print("  人耳已确认 LOCKED       %3d" % len(b["LOCKED"]))
    print("  平淡 WATCH（送听）      %3d" % len(b["WATCH"]))
    print("\n%-8s %-13s %-6s %-6s %-7s %-6s %s"
          % ("uid", "adv", "loc", "dur_z", "voiced", "声纹", "结论"))
    for u in sorted(us, key=lambda z: ((us[z].get("m2") or {}).get("loc") if
                                       (us[z].get("m2") or {}).get("loc") is not None else -99)):
        x = us[u]
        m = x.get("m2") or {}
        spk = (x.get("active") or {}).get("spk")
        print("%-8s %-13s %-6s %-6s %-7s %-6s %s"
              % (u, x["adv"][:13], m.get("loc"), m.get("dur_z"), m.get("voiced"),
                 "-" if spk is None else spk, "%s %s" % (x.get("judge"), x.get("judge_by") or "")))
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.json:
        json.dump(st, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n写出 %s" % a.json)
    write_report(st, b)


def write_report(st, b):
    us = st["units"]
    lines = ["# 副词回环报告", "",
             "生成时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"), "",
             "## 漏斗", "",
             "| 阶段 | 条数 |", "|---|---|",
             "| 预测（LLM 双票） | %d |" % len(us),
             "| 无音频 | %d |" % len(b["NO_AUDIO"]),
             "| 物理缺陷 FIX | %d |" % len(b["FIX"]),
             "| F0 达标 PASS | %d |" % len(b["PASS"]),
             "| 人耳已确认 LOCKED | %d |" % len(b["LOCKED"]),
             "| 平淡 WATCH（送听） | %d |" % len(b["WATCH"]), "",
             "判定口径：`ABSENT/SWALLOW/换人 → FIX`；`rel_z ≥ %.1f → PASS`；其余 WATCH。"
             % REL_Z_OK,
             "loc 判据已停用（幅度型指标与人耳 r=0.30，且抬的是寄存器不是轮廓）；"
             "音高改由 TTSDS2 PROSODY 因子做批次级验收。", "",
             "## 明细（按 loc 升序）", "",
             "| uid | 副词 | loc(半音) | dur_z | voiced | 结论 |", "|---|---|---|---|---|---|"]
    for u in sorted(us, key=lambda z: ((us[z].get("m2") or {}).get("loc") if
                                       (us[z].get("m2") or {}).get("loc") is not None else -99)):
        x = us[u]
        m = x.get("m2") or {}
        lines.append("| %s | %s | %s | %s | %s | %s |"
                     % (u, x["adv"], m.get("loc"), m.get("dur_z"), m.get("voiced"),
                        "%s %s" % (x.get("judge"), x.get("judge_by") or "")))
    p = os.path.join(ROOT, "_adv_loop_report.md")
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n写出 %s" % p)


def cmd_adopt(a):
    """把「PASS 且闸门全过」的候选落进 _mt_pick（默认 dry-run）。"""
    st = load_state(a)
    # 必须现算「当前交付版」的状态：state 里的 judge 可能是上一轮写的，
    # 而 run_round 已不再覆盖它 —— 靠缓存会把候选自己挡在门外。
    classify(st, getattr(a, "units", None) or None)
    us = st["units"]
    rows = []
    nat_skip = []
    only = getattr(a, "units", None) or None
    for u, x in sorted(us.items()):
        if only and u not in only:
            continue
        # 只认闸门没挂的候选。旧候选（guards 为空）一律不收 —— 它们没经过任何检查。
        # ⚠️ 允许 WARN：音色偏低 / 语速跳 / 有声帧偏少 都只提示不否决。
        # ★ 本轮只收 loc（F0）轴（见 ADOPT_AXIS_PREFIX 注释）。
        att = [z for z in (x.get("attempts") or [])
               if z.get("judge") == "PASS"
               and (z.get("guards") or {}).get("verdict") in ("OK", "WARN")
               and (z.get("by") or "").startswith(ADOPT_AXIS_PREFIX)]
        if not att:
            continue
        # 排序：优先双轴达标（duration 轴），再看 loc
        def _score(z):
            g = 1.0
            if z.get("voiced_ctl") and z.get("voiced"):
                g = z["voiced"] / max(z["voiced_ctl"], 1e-9)
            return (max(z.get("loc") or -9, 0), g)
        best = max(att, key=_score)
        if best.get("spk") is not None and best["spk"] < SPK_VETO:
            continue
        # ★★ 自然度下限（2026-10-27）：F0/时长轴过了也可能是个「明显不行」的 take。
        # 用 NISQA-MOS/DIS/COL + SQUIM 的 z 均值，**先回归掉语音时长**（r=0.58），
        # 残差阈值 -2.3（换-take 残差噪声 p95 2.15）；语音 <0.9s 判 UNKNOWN 不拦。
        try:
            import _nat_guard as NG
            nv = NG.verdict(best["wav"], best.get("ctl_wav"))
            best["nat"] = nv.get("res") if nv.get("res") is not None else nv["ens"]
            if nv["verdict"] == "FAIL":
                nat_skip.append((u, nv["why"]))
                continue
        except Exception as e:            # 算不出来不否决，但要留痕
            best["nat"] = None
            nat_skip.append((u, "nat 测量失败: " + str(e)[:50]))
        cur = (x.get("m2") or {}).get("rel_z")
        cur_voiced = (x.get("m2") or {}).get("voiced")
        # 只替换「当前平淡」的条目：抬 F0 不是目的，修缺陷才是
        if x.get("judge") == "LOCKED":
            continue
        # ★ 2026-10-27：loc 判据停用（幅度型指标与人耳 r=0.30，且 Prosogram 证明
        #   它抬的是寄存器不是轮廓）。改用时长轴 rel_z 判断「当前是否已经够好」。
        #   仍需 voiced 达标 —— rel_z 高但几乎没发声的条目不算数（N0226 的教训）。
        cur_ok = (cur is not None and cur >= REL_Z_OK
                  and (cur_voiced is None or cur_voiced >= VOICED_ABS_MIN))
        if x.get("judge") == "PASS" or cur_ok:
            continue
        # 已经就是这一版（交付文件与候选同源）就别再列
        pk = os.path.join(ROOT, "_mt_pick", u + ".wav")
        try:
            if os.path.exists(pk) and _md5(pk) == _md5(best["wav"]):
                continue
        except Exception:
            pass
        rows.append((u, best))
    if not rows:
        print("没有可采纳的重生版")
        return
    print("%-8s %-13s %-10s %-8s %-8s %-6s %s" % ("uid", "adv", "自然度", "原loc", "新loc", "声纹", "文件"))
    for u, z in rows:
        nn = z.get("nat")
        print("%-8s %-13s %-10s %-8s %-8s %-6s %s"
              % (u, us[u]["adv"][:13], ("%+.2fσ" % nn) if nn is not None else "-",
                 (us[u].get("m2") or {}).get("loc"),
                 z["loc"], z.get("spk"), z["wav"]))
    for u, why in nat_skip:
        print("  自然度拦下 %-8s %s" % (u, why))
    if not a.apply:
        print("\n[dry-run] 加 --apply 才会写入 _mt_pick")
        return
    for u, z in rows:
        dst = os.path.join(ROOT, "_mt_pick", u + ".wav")
        if os.path.exists(os.path.dirname(dst)):
            shutil.copy2(z["wav"], dst)
            us[u]["active"] = dict(wav=z["wav"], prom=att_prom(u, z["seed"]),
                                   loc=z.get("loc"), spk=z.get("spk"),
                                   seed=str(z["seed"]))
            print("已写入 %s  (active=%s)" % (dst, z["wav"]))
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("状态已更新 %s" % STATE)

    # ★ wav 换了 prom 必须重建，否则「新音频 + 旧对齐」= 血缘错位（第 4 次教训）
    if rows:
        units = ",".join(u for u, _ in rows)
        print("重建 prom：%s" % units)
        r = subprocess.run([PY310, os.path.join(ROOT, "_prom_build.py"),
                            "--prefix", "_mt_pick", "--dir", "_mt_pick",
                            "--units", units],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=3600)
        print((r.stdout or "")[-400:] or (r.stderr or "")[-300:])
    print("注意：还需同步 mt_post.OVERRIDE，否则 mt_repick/score 重跑会覆盖")


def cmd_proso(a):
    """Prosogram glissando 层：逐单元读数 + 组级进度条。

    ★ 只作展示，**不进判定**。理由见 _proso_report.md §七：
      ctl 组的副词有滑率（+8.4 点）不低于交付版（+1.9 点），
      同 seed 配对的 McNemar 是 9:8 / 10:10 / 7:5 —— 标签在这个通道上没有效果。
      它唯一可靠的用法是**组级进度条**（真人 +20.2 点）。
    """
    import csv as _csv
    import _align_lib as _AL
    pw = _AL.find_data("_proso_words.csv")
    pt = _AL.find_data("_proso_takes.csv")
    if not (pw and os.path.exists(pw) and pt and os.path.exists(pt)):
        print("缺 _proso_words.csv / _proso_takes.csv，先跑 _proso_parse.py")
        return
    W = list(_csv.DictReader(open(pw, encoding="utf-8-sig")))
    T = {r["gid"]: r for r in _csv.DictReader(open(pt, encoding="utf-8-sig"))}
    st = load_state(a)
    us = st["units"]

    def rate(rows):
        return (100.0 * sum(1 for w in rows if int(w["n_move"]) > 0) / len(rows)) if rows else None

    print("=== Prosogram glissando 层（只作展示，不参与判定）===")
    print("%-8s %-13s %-7s %-8s %-8s %s" % ("uid", "adv", "滑幅", "核相对时长", "滑音型", "核数"))
    hit = 0
    for u in sorted(us):
        gid = "n:%s:delivered" % u
        t = T.get(gid)
        if not t:
            continue
        adv = [w for w in W if w["gid"] == gid and w["is_adv"] == "True"]
        if not adv:
            continue
        w = adv[0]
        hit += 1
        print("%-8s %-13s %-7s %-8s %-8s %s" % (
            u, us[u]["adv"][:13], w["max_abs_intra"], w["rel_dur"], w["glide"],
            t.get("n_nucl")))
    print("\n有 Prosogram 读数的单元：%d / %d" % (hit, len(us)))

    # ---- 组级进度条 ----
    print("\n=== 组级：副词有滑率 − 同句其他词有滑率 ===")
    for kind, lab in (("delivered", "交付版"), ("cand", "候选"), ("ctl", "对照"),
                      ("tts", "tts"), ("edit", "edit")):
        g = [w for w in W if w["kind"] == kind]
        adv = [w for w in g if w["is_adv"] == "True"]
        oth = [w for w in g if w["is_adv"] != "True"]
        if not adv:
            continue
        a1, o1 = rate(adv), rate(oth)
        print("  %-6s 副词 %5.1f%% (n=%3d)   其他 %5.1f%% (n=%4d)   **%+5.1f 点**"
              % (lab, a1, len(adv), o1, len(oth), a1 - o1))
    # 真人靶子：句内最长词 vs 其余词（真人没有「副词」这个概念，不能用 adv 行比）
    # 只读 _proso_words.csv，不依赖 3MB 的 _proso.json —— 仓库里只同步 CSV。
    hb = {}
    for w in W:
        if w["side"] == "human":
            hb.setdefault(w["tid"], []).append(w)
    top, rest = [], []
    for tid, ws in hb.items():
        ok = [w for w in ws if w.get("rel_z") and w.get("loc") and int(w["n_nuclei"] or 0)]
        if len(ok) < 4:
            continue
        a = max(ok, key=lambda w: float(w["rel_z"]))
        b = max(ok, key=lambda w: float(w["loc"]))
        top.append(a)
        rest.extend([w for w in ok if w is not a and w is not b])
    if top and rest:
        print("  %-6s 最长词 %5.1f%% (n=%3d)   其余 %5.1f%% (n=%3d)   **%+5.1f 点**  ← 真人靶子"
              % ("真人", rate(top), len(top), rate(rest), len(rest), rate(top) - rate(rest)))
    print("\n★ 真人靶子用「句内最长词 vs 其余词」，不能用副词行比 ——")
    print("  真人的副词不是被强调的那个词，口径不同。见 _proso_report.md §二。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="跑回环漏斗 + 逐条明细")
    ap.add_argument("--proso", action="store_true", help="Prosogram glissando 层（只展示）")
    ap.add_argument("--run", action="store_true", help="跑回环（会重生，除非 seeds 为空）")
    ap.add_argument("--adopt", action="store_true", help="把已通过的 take 落进 _mt_pick")
    ap.add_argument("--apply", action="store_true", help="配合 --adopt 才真写文件")
    ap.add_argument("--units", default=None, help="逗号分隔的 uid")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seeds", default="2025,2027,2029", help="重生 seed 序列；空串=只分析")
    ap.add_argument("--max-gen", type=int, default=3, help="最多重生几次")
    ap.add_argument("--fix-watch", action="store_true",
                    help="对 F0 平淡(WATCH)也重生；默认只修物理缺陷")
    ap.add_argument("--no-f0", action="store_true", help="（保留）跳过预复核")
    ap.add_argument("--proso-gate", type=float, default=80.0,
                    help="打标签前的批次韵律门槛（TTSDS2 PROSODY，默认 80；0=关）")
    ap.add_argument("--no-proso-gate", action="store_true", help="关掉韵律体检前置")
    ap.add_argument("--minutes", type=float, default=0,
                    help="墙钟时限（分钟）。到点停止生成，已生成的照常测完判定；0=不限")
    ap.add_argument("--rebuild", action="store_true", help="丢弃已有状态重建")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    if a.no_proso_gate:
        a.proso_gate = 0.0
    a.deadline = (time.time() + a.minutes * 60) if a.minutes else None
    if a.units:
        a.units = {x.strip() for x in a.units.split(",") if x.strip()}
    if a.adopt:
        cmd_adopt(a)
    elif a.run:
        cmd_run(a)
    elif a.proso:
        cmd_proso(a)
    else:
        cmd_report(a)


if __name__ == "__main__":
    main()
