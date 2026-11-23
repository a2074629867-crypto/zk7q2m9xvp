# -*- coding: utf-8 -*-
"""平静句验收闸：不测情绪强度，测「语气与节奏」。

为什么：`A few years ago. I was about five. Or six.` 这种是**普通叙述**，
七闸里的情绪强度项对它不成立（它没有情绪要表达），拿 p10 卡它必然把好句判成 E，
而且会诱导我们挑「更激动」的 take。平静句该看的是：

1. 语速 wpm（含停顿时整体语速 + 不含停顿的吐字语速）
2. 停顿结构：句子有几个断点、每个断点多长（用户要求「慢慢停顿一下」）
3. 亮度 voiced-tilt（平静不该亮/不该像喊）
4. 音高 F0 是否落在该角色区间（高了就是假声/喊）
5. 内容 ASR 覆盖（沿用双 ASR 仲裁结果，可选）

基线取自同角色「平静」且七闸全过的句子，按 p10~p90 给区间，不写死数字。

用法：
  G:/Python310/python.exe _calm_gate.py --ids c2_0312 --cand G:/_setup/_sweep/r48
"""
import argparse
import glob
import io
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf
from numpy.fft import rfft
from parselmouth.praat import call

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as _P

ROOT = _P.ROOT
AUDIO = os.path.join(ROOT, "_audio_ch123", "out_paused")
WIN = np.hanning(1024)


def spoken_words(text):
    """TTS 念的就是 plan.text 全文（含叙述归属），所以按整句词数算，只排除纯标点。"""
    t = (text or "").strip()
    return len([w for w in t.split() if any(c.isalnum() for c in w)])


def load_plan():
    p = {}
    for f in ("_dlg_plan_v2_paused.jsonl", "_dlg_plan_v2.jsonl"):
        fp = os.path.join(ROOT, f)
        if not os.path.exists(fp):
            continue
        for l in io.open(fp, encoding="utf-8"):
            if l.strip():
                x = json.loads(l)
                p.setdefault(x["id"], x)
    return p


def measure(path, nwords, txt=""):
    """返回 dur / 有声时长 / 整体 wpm / 吐字 wpm / 停顿列表 / F0 / voiced-tilt。"""
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y)
    hop = int(0.01 * sr)
    fl = int(0.025 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    db = 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12)
    thr = max(-46.0, float(db.max()) - 45.0)
    voiced = db > thr

    runs, s = [], None
    for k, v in enumerate(voiced):
        if v and s is None:
            s = k
        if not v and s is not None:
            runs.append((s, k))
            s = None
    if s is not None:
        runs.append((s, n))
    runs = [r for r in runs if (r[1] - r[0]) * hop / sr >= 0.05]
    vt = sum(b - a for a, b in runs) * hop / sr
    gaps = []
    for i in range(len(runs) - 1):
        g = (runs[i + 1][0] - runs[i][1]) * hop / sr
        if g >= 0.15:
            gaps.append(round(g, 2))

    pit = call(parselmouth.Sound(y, sr), "To Pitch", 0.0, 75, 600)
    fo = pit.selected_array["frequency"]
    tilts, f0s = [], []
    for k, val in enumerate(fo):
        c = int(k * 0.01 * sr)
        seg = y[max(0, c - 512):max(0, c - 512) + 1024]
        if len(seg) < 1024 or val <= 0:
            continue
        if np.sqrt((seg ** 2).mean()) < 0.01:
            continue
        m = np.abs(rfft(seg * WIN)) + 1e-12
        fr = np.linspace(0, sr / 2, len(m))
        tilts.append(float(m[(fr > 2000) & (fr < 5000)].mean()
                           / m[(fr > 200) & (fr < 1000)].mean()))
        f0s.append(val)

    dur = len(y) / sr
    nb = len([c for c in (txt or "") if c in ",.;:!?"])
    return dict(dur=round(dur, 2), n_break=nb, voiced=round(vt, 2),
                wpm_all=round(nwords / dur * 60) if dur > 0 else 0,
                wpm_voiced=round(nwords / vt * 60) if vt > 0.3 else 0,
                gaps=gaps, n_gap=len(gaps), gap_max=max(gaps) if gaps else 0.0,
                F0=int(np.median(f0s)) if f0s else 0,
                tilt=round(float(np.median(tilts)) if tilts else 0.0, 3))


def baseline(plan, role, base_emos=("*",)):
    """同角色全库的 (wpm_all, wpm_voiced, F0, tilt) 分布。

    2026-11-20 改：原来只取 emo∈{平静,neutral,中性}，Charles 只有 4 条 —— 基线是噪声，
    而且用户已指出「紧张」这类标本身就不准（「根本不会比普通的更亮」），拿标签圈基线
    等于用不可靠的标签去判另一批句子。改成同角色全库；短句（<1.6s）的 wpm 天然虚高，
    排除在语速基线之外。
    """
    rows = []
    all_emo = ("*" in base_emos)
    for i, p in plan.items():
        if p["who"] != role:
            continue
        if not all_emo and p.get("emo") not in base_emos:
            continue
        f = os.path.join(AUDIO, i + ".wav")
        if not os.path.exists(f):
            continue
        nw = spoken_words(p.get("text"))
        if nw < 3:
            continue
        m = measure(f, nw, p.get("text"))
        # 用「有声时长」≥1.0s 当入池条件：wpm 的分母本质是有声时间，
        # 拿总时长卡会把大量 1.2~1.5s 的短对白全排掉（Charles 68 条只剩 3 条）。
        if m["voiced"] < 1.0:
            continue
        rows.append(m)
    if not rows:
        return None
    def q(k, lo=10, hi=90):
        v = sorted(r[k] for r in rows if r[k])
        if not v:
            return (0, 0)
        return (v[int(len(v) * lo / 100)], v[min(len(v) - 1, int(len(v) * hi / 100))])
    med = {k: sorted(r[k] for r in rows if r[k])[len(rows) // 2] for k in
           ("wpm_all", "wpm_voiced", "F0", "tilt")}
    return dict(n=len(rows), wpm_all=q("wpm_all"), wpm_voiced=q("wpm_voiced"),
                F0=q("F0"), tilt=q("tilt"), med=med)


def judge(m, base, emo=""):
    """语气闸（2026-11-20 按用户反馈重定判据，第三版）。

    用户原话：
      「这种都能标错，紧张这个情绪判断就有问题吧，根本不会比普通的更亮，直接替换掉吧」
      「不是说喊，是情绪很激动很快的说话，这是跟紧张完全不同的」
      「现在调整过的速度又太慢了，中间插入的停顿太明显了，没有呼吸感，停顿太空」

    据此只留两个**可靠且互不相干**的缺陷：
      · 激动快说 = 吐字语速 wpm_voiced > 同角色中位 ×1.15
        （用 wpm_voiced 而不是 wpm_all：后者被停顿污染，一插停顿就假性变慢）
      · 像喊     = voiced-tilt > 同角色 p90
        （只看 tilt，不再叠加 F0 —— 本库 F0 中位在 172~349 之间跳，是八度误判，
         拿它当判据会把正常句判死，这正是之前"紧张标错"的来源之一）

    F0 只作展示字段，不进判决。停顿只作 info：模型没停就改文本让它自己换气，
    禁止在波形上灌静音。
    """
    rs, info = [], []
    if base:
        v_med = base["med"]["wpm_voiced"]
        if v_med and m["wpm_voiced"] and m["wpm_voiced"] > v_med * 1.15:
            rs.append("激动快说 %d>%d(吐字中位×1.15)" % (m["wpm_voiced"], int(v_med * 1.15)))
        t_p90 = max(base["tilt"][1], 0.13)
        if m["tilt"] > t_p90:
            rs.append("像喊 亮%.3f>p90 %.3f" % (m["tilt"], t_p90))
    if m.get("n_break", 0) >= 1 and m["gap_max"] < 0.18:
        info.append("逗号处最长间隔 %.2fs，偏紧" % m["gap_max"])
    return rs, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--cand", default="")
    ap.add_argument("--role", default="")
    ap.add_argument("--emotions", default="平静,neutral,中性",
                    help="要验收的情绪（逗号分隔），如 平静,紧张,委屈,警惕")
    ap.add_argument("--base-emo", default="*",
                    help="取基线用的情绪（逗号分隔）；默认 * = 同角色全库（标签本身不可靠）")
    ap.add_argument("--prefix", default="CALM", help="判决前缀")
    ap.add_argument("--out", default=os.path.join(ROOT, "_calm_gate.json"))
    ap.add_argument("--md", default=os.path.join(ROOT, "_calm_gate.md"))
    a = ap.parse_args()

    plan = load_plan()
    EMOS = tuple(x.strip() for x in a.emotions.split(",") if x.strip())
    BEMOS = tuple(x.strip() for x in a.base_emo.split(",") if x.strip())
    ids = [x for x in a.ids.split(",") if x.strip()]
    if not ids:
        ids = [k for k, p in plan.items() if p.get("emo") in EMOS]
    _bc = {}
    def base_of(role):
        if role not in _bc:
            _bc[role] = baseline(plan, role, BEMOS)
            print("基线（%s %s）：%s" % (role, "/".join(BEMOS), _bc[role]), flush=True)
        return _bc[role]
    if a.role:
        base_of(a.role)

    jobs = []
    for i in ids:
        f = os.path.join(AUDIO, i + ".wav")
        if os.path.exists(f):
            jobs.append((i + "（现役）", f, i))
    if a.cand:
        for p in sorted(glob.glob(os.path.join(a.cand, "*.wav"))):
            jobs.append((os.path.basename(p)[:-4], p, ids[0]))

    out = []
    for tag, path, rid in jobs:
        nw = spoken_words(plan.get(rid, {}).get("text")) or 9
        m = measure(path, nw, plan.get(rid, {}).get("text"))
        rs, info = judge(m, base_of(plan.get(rid, {}).get("who") or "Charles"),
                         plan.get(rid, {}).get("emo") or "")
        v = (a.prefix + "_PASS") if not rs else (a.prefix + "_WARN")
        m.update(id=tag, verdict=v, reasons=rs, info=info,
                 who=plan.get(rid, {}).get("who"),
                 emo=plan.get(rid, {}).get("emo"))
        out.append(m)
        print("%-30s %-9s dur=%.2f wpm=%d/%d F0=%d tilt=%.3f gaps=%s" %
              (tag, v, m["dur"], m["wpm_all"], m["wpm_voiced"], m["F0"], m["tilt"], m["gaps"]))
        if rs:
            print("    ", "; ".join(rs))
        if info:
            print("     提示:", "; ".join(info))
    json.dump(out, io.open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
