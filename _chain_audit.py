# -*- coding: utf-8 -*-
"""链路体检：一条命令看清「哪些环节有输入、哪些断了」。

只读文件与规模，不重跑模型。2026-11-14 02:4x 建，2026-11-15 12:1x 修口径：
  ★ 原来查的是 `pause_llm.json`（34 条 key，L/I 前缀，是早期 pilot 的残留），
    对本项目必然报「缺」→ 误判成「本书几乎无判定」。生产用的是
    `pause_llm_castle.json`（对白 239）与 `pause_llm_narr.json`（旁白 499）。
  同型错误教训（LESSONS #6）：口径换了就不能拿旧文件当判据，得按**当前生产文件**查。

用法：G:/Python310/python.exe _chain_audit.py
"""
import glob
import json
import os
import re
import sys

S = r"G:/_setup"
sys.path.insert(0, S)


def p(*a):
    return os.path.join(S, *a)


def n_wav(d):
    return len(glob.glob(os.path.join(S, d, "*.wav")))


rows = []


def add(name, ok, detail):
    rows.append((name, "OK " if ok else "缺 ", detail))


def nkey(fp):
    if not os.path.exists(fp):
        return 0
    d = json.load(open(fp, encoding="utf-8"))
    return len([k for k in d if not str(k).startswith("_")])


# ── 1 交付音频 ────────────────────────────────────────────────
c = n_wav("_audio_ch123/out")
add("交付音频", c == 955, "%d 条 wav（应 955 = 旁白 716 + 对白 239）" % c)

# ── 2 参考库 ─────────────────────────────────────────────────
lib = json.load(open(p("_emo_refs_all.json"), encoding="utf-8"))
tot = okn = 0
for who, emos in lib.items():
    for emo, items in emos.items():
        for it in items:
            tot += 1
            if os.path.exists(it.get("path", "")):
                okn += 1
add("参考库", tot == okn and tot > 0, "%d/%d 条切片可读" % (okn, tot))

# ── 3 闸缓存 ─────────────────────────────────────────────────
for f, label in [("_mutcache_real", "闸4 sep 缓存"), ("_utt_emb", "r34 声纹缓存"),
                 ("_drift_cache.json", "闸4 drift 缓存"),
                 ("_nat_cache.json", "闸6 自然度缓存"), ("_wt_cache.json", "强制对齐缓存")]:
    q = p(f)
    exists = os.path.exists(q)
    detail = ""
    if os.path.isdir(q):
        detail = "%d 个文件" % len(os.listdir(q))
    elif exists:
        detail = "%.0f KB" % (os.path.getsize(q) / 1024)
    add(label, exists, detail)

# ── 4 停顿判定（生产文件，不是 pilot）────────────────────────
plan = [json.loads(l) for l in open(p("_castle_en_ch123_plan.jsonl"), encoding="utf-8")
        if l.strip()]
n_dlg = len([r for r in plan if r.get("dialog")])
n_narr = len([r for r in plan if not r.get("dialog")])

d_castle = nkey(p("pause_llm_castle.json"))
add("对白停顿判定", d_castle >= n_dlg,
    "pause_llm_castle.json %d / %d 条" % (d_castle, n_dlg))

# 旁白只有「含句内标点」的行才有槽位，分母不是 716
d_narr = nkey(p("pause_llm_narr.json"))
add("旁白停顿判定", d_narr >= 400, "pause_llm_narr.json %d 条（有槽位的行）" % d_narr)

for f, label in [("_punct_expr.json", "标点表达度实测"),
                 ("_pause_plan.jsonl", "停顿兜底计划")]:
    q = p(f)
    ok = os.path.exists(q)
    d = ""
    if ok:
        if q.endswith(".jsonl"):
            d = "%d 行" % sum(1 for _ in open(q, encoding="utf-8"))
        else:
            d = "%d 条 key（本书 c* %d 条）" % (nkey(q),
                                               len([k for k in json.load(open(q, encoding="utf-8"))
                                                    if str(k).startswith("c")]))
    add(label, ok, d)

# ── 5 停顿注入产物 ───────────────────────────────────────────
# 旁白交付是 716 条（speaker=narrator），不是 plan 里非 dialog 的 726 条 ——
# 那 10 条是「叙述里被点名的角色台词」，交付走对白版。`_narr_ids.txt` 当初按
# 「非 dialog」取的 726，所以多注了 10 个副本在这里；不影响交付（对白用 out_paused 的版本）。
n_narr_deliver = 716
add("对白停顿注入", n_wav("_audio_ch123/out_paused") >= n_dlg
    and os.path.exists(p("_audio_ch123/out_paused", "_pause_report.json")),
    "%d / %d 条，报告 %s" % (n_wav("_audio_ch123/out_paused"), n_dlg,
                          "有" if os.path.exists(p("_audio_ch123/out_paused", "_pause_report.json")) else "缺"))
_nn = n_wav("_audio_narr_paused")
add("旁白停顿注入", _nn >= n_narr_deliver
    and os.path.exists(p("_audio_narr_paused", "_pause_report.json")),
    "%d 条（交付旁白 %d，另 %d 条是误纳的对白副本，不参与交付）" %
    (_nn, n_narr_deliver, max(0, _nn - n_narr_deliver)))

# ── 6 情绪链路 ───────────────────────────────────────────────
tier_fp = p("_ref_tier2.json")
if os.path.exists(tier_fp):
    t = json.load(open(tier_fp, encoding="utf-8"))
    combos = [(r, e, v) for r, emo in t.items() for e, v in emo.items()]
    two = [x for x in combos if x[2].get("normal") and x[2].get("intense")]
    one = [x for x in combos if x[2].get("normal") and not x[2].get("intense")]
    none_ = [x for x in combos if not x[2].get("normal")]
    add("情绪两档", not none_ and not one,
        "%d 组：双档 %d / 单档 %d / 全缺 %d%s" %
        (len(combos), len(two), len(one), len(none_),
         ("  单档=" + ",".join("%s/%s" % (a, b) for a, b, _ in one)) if one else ""))
else:
    add("情绪两档", False, "缺 _ref_tier2.json")

led = p("_retag_ledger.json")
if os.path.exists(led):
    L = json.load(open(led, encoding="utf-8"))
    okL = [x for x in L if x.get("ok")]
    add("加标签重生成", len(L) > 0,
        "%d 条候选 / 达标 %d（台账 _retag_ledger.json）" % (len(L), len(okL)))
else:
    add("加标签重生成", False, "缺 _retag_ledger.json")

cand = len(glob.glob(p("_sweep", "cand", "*.wav")))
add("多 seed 候选", cand > 0, "%d 条（_sweep/cand）" % cand)

# ── 6b 内容闸（第 9 维）与短句验收 ────────────────────────
wl = p("_wl_flags_all.jsonl")
add("词级内容台账", os.path.exists(wl),
    "%d 行（LEAD_REF/PACE/TRUNC 那一维）" % sum(1 for _ in open(wl, encoding="utf-8"))
    if os.path.exists(wl) else "缺")

sg = p("_short_gate.json")
if os.path.exists(sg):
    import collections
    G = json.load(open(sg, encoding="utf-8"))
    cc = collections.Counter(x["verdict"] for x in G)
    add("短句验收", len(G) >= 50,
        "%d 条：%s" % (len(G), ", ".join("%s %d" % kv for kv in sorted(cc.items()))))
else:
    add("短句验收", False, "缺 _short_gate.json")

# ── 6c 交付电平（out_paused 全量）─────────────────────────
try:
    import numpy as np
    import soundfile as sf
    from narr_gate_phys import voiced_db
    vs = []
    for q in sorted(glob.glob(p("_audio_ch123", "out_paused", "*.wav"))):
        y, sr = sf.read(q, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        lv, _, _ = voiced_db(np.ascontiguousarray(y), sr)
        if lv is not None:
            vs.append(float(lv))
    span = max(vs) - min(vs)
    med = float(np.median(vs))
    add("交付电平", abs(med + 24) < 0.15 and span <= 1.0,
        "中位 %.2f dBFS，跨度 %.2f dB，%d 条" % (med, span, len(vs)))
except Exception as e:
    add("交付电平", False, "算不了：%s" % e)

# ── 7 闸结果 ─────────────────────────────────────────────────
def _vn(f):
    m = re.search(r"_v(\d+)\.json$", f)
    return int(m.group(1)) if m else -1


vers = sorted(glob.glob(p("_gate_dlg_v*.json")), key=_vn)
if vers:
    g = json.load(open(vers[-1], encoding="utf-8"))
    import collections
    cc = collections.Counter(x["verdict"] for x in g)
    add("最新闸结果", True, "%s：%s" % (os.path.basename(vers[-1]),
                                        ", ".join("%s %d" % kv for kv in sorted(cc.items()))))
else:
    add("最新闸结果", False, "无")

noseq = sorted(glob.glob(p("_narr_phys*.json")))
add("旁白物理闸", bool(noseq), os.path.basename(noseq[-1]) if noseq else "无")

print("%-16s %-4s %s" % ("环节", "", "状态"))
print("-" * 78)
for name, st, detail in rows:
    print("%-16s %-4s %s" % (name, st, detail))
bad = [r for r in rows if r[1].strip() != "OK"]
print("-" * 78)
print("结论：%s" % ("全部打通" if not bad else "有 %d 项待补 → %s" %
                 (len(bad), ", ".join(r[0] for r in bad))))
