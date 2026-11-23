# -*- coding: utf-8 -*-
"""mt_score.py —— 多候选择优（默认 env 跑；ASR / NISQA 由前置脚本提供）。

口径（全部按项目已固化的规则，别再改动含义）：
- **语速用 voiced wpm**（只算有声帧，去掉 TTS 内部停顿）。
  总时长口径会把停顿算进去，把 "He said," 算成 63wpm，完全失真。
- **目标 T = 章内 voiced wpm 中位 × 0.8**（用户：速度到 0.8 够了）
- **tempo 硬夹 [0.70, 1.00]**：所需 t = T/w 低于 0.70 ⇒ 这条太快、红线内拉不回来 ⇒ 淘汰重生成；
  t > 1.00 ⇒ 本来就更慢 ⇒ **不动**（用户：原声慢的不加快）
- **不许吞字**：末词必须出现、相似度 ≥0.78
- **不许坏音频**：有声段频谱重心 ≤4600Hz（气声/半截词）、NISQA MOS ≥2.5（若有打分）
- 音色：≥4s 才计入声纹（短窗不可信）

用法：
    python mt_score.py --ch ch1 --dirs _mt_raw_s42,_mt_raw_s1234
"""
import argparse
import difflib
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mt_spot as M

ROOT = "G:/_setup"
PICK = os.path.join(ROOT, "_mt_pick")
SR_MIN_DUR_SPK = 4.0
SR_MIN_DUR_F0 = 2.5
F0_CEIL = 102.0     # 马修基线 79–80Hz；>102 就是偏了 4 个半音以上，直接判死


def toks(s):
    return "".join(c if (c.isalnum() or c == "'") else " " for c in
                   (s or "").lower().replace("\u2019", "'").replace("\u2018", "'")).split()


def squash(s):
    """去掉一切非字母数字 —— 专治 "Kingshaw" 被 ASR 拆成 "King Shaw" 这种情况。
    这类误判会把 r 压到 0.4，看起来像吞字，其实一个音都没错。"""
    return "".join(c for c in (s or "").lower()
                   .replace("\u2019", "").replace("\u2018", "") if c.isalnum())


def sim(pt, at, p_text, a_text):
    """取「词级」与「无空格字符级」两种相似度的较大者。"""
    r1 = difflib.SequenceMatcher(None, pt, at).ratio() if (pt and at) else 0.0
    r2 = difflib.SequenceMatcher(None, squash(p_text), squash(a_text)).ratio()
    return max(r1, r2)


def stats(fp, words):
    y, sr = sf.read(fp, dtype="float32", always_2d=True)
    y = y.mean(1)
    w = int(0.02 * sr)
    keep = [i for i in range(0, len(y) - w, w)
            if 20 * np.log10(np.sqrt((y[i:i + w] ** 2).mean()) + 1e-12) > -40]
    v = len(keep) * w / float(sr)
    dur = len(y) / float(sr)
    wpm = words / v * 60.0 if v > 0.15 else 0.0
    cen = 0.0
    if keep:
        z = np.concatenate([y[i:i + w] for i in keep])
        sp = np.abs(np.fft.rfft(z * np.hanning(len(z))))
        fr = np.fft.rfftfreq(len(z), 1 / sr)
        cen = float((sp * fr).sum() / (sp.sum() + 1e-9))
    return dur, v, wpm, cen


def _c(v):
    if isinstance(v, (np.floating, float)):
        return round(float(v), 3)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--dirs", required=True)
    ap.add_argument("--asr", default="_mt_asr.json")
    ap.add_argument("--nisqa", default="_mt_nisqa.json")
    ap.add_argument("--plan", default="mt_plan2.json")
    ap.add_argument("--target", type=float, default=None, help="覆盖目标 voiced wpm")
    ap.add_argument("--list-fail", action="store_true")
    a = ap.parse_args()

    plan = [p for p in json.load(open(os.path.join(ROOT, a.plan), encoding="utf-8"))
            if p["ch"] == a.ch]
    dirs = [d.strip() for d in a.dirs.split(",")]
    ap_ = os.path.join(ROOT, a.asr)
    asr = {os.path.normcase(os.path.abspath(k)): v for k, v in
           json.load(open(ap_, encoding="utf-8")).items()} if os.path.exists(ap_) else {}
    np_ = os.path.join(ROOT, a.nisqa)
    nis = {os.path.normcase(os.path.abspath(k)): v for k, v in
           json.load(open(np_, encoding="utf-8")).items()} if os.path.exists(np_) else {}
    E_ref = M.embed_ref()

    rows = []
    for p in plan:
        words = max(1, len(p["text"].split()))
        cands = []
        for d in dirs:
            fp = os.path.abspath(os.path.join(ROOT, d, p["id"] + ".wav"))
            if not os.path.exists(fp):
                continue
            try:
                dur, v, wpm, cen = stats(fp, words)
            except Exception:
                continue
            f0 = hi = lo = 0.0
            if dur >= SR_MIN_DUR_F0:
                f0, lo, hi = M.f0stats(*M.rd(fp))
            spk = float("nan")
            if dur >= SR_MIN_DUR_SPK:
                try:
                    spk = M.SPK.cos(M.SPK.embed(fp), E_ref)
                except Exception:
                    pass
            nk = os.path.normcase(fp)
            atxt = asr.get(nk, "")
            at, pt = toks(atxt), toks(p["text"])
            ratio = sim(pt, at, p["text"], atxt)
            last = [x for x in pt if not any(c.isdigit() for c in x)]
            tail_ok = bool(last) and bool(at) and any(x[:4] == last[-1][:4] for x in at[-5:])
            # 无空格字符级兜底："King Shaw" 结尾也算 "Kingshaw" 到齐了
            if not tail_ok and last:
                tail_ok = squash(last[-1])[:5] in squash(atxt)[-14:]
            cands.append({"seed": os.path.basename(d).replace("_mt_raw_s", ""),
                          "path": fp, "dur": dur, "voiced": v, "wpm": wpm,
                          "centroid": cen, "f0": f0, "spread": hi - lo, "spk": spk,
                          "ratio": ratio, "tail_ok": tail_ok,
                          "mos": nis.get(nk, {}).get("mos"),
                          "dis": nis.get(nk, {}).get("dis")})
        rows.append({"id": p["id"], "text": p["text"], "cands": cands})

    allw = [c["wpm"] for r in rows for c in r["cands"] if c["wpm"] > 0]
    if not allw:
        print("没有候选"); return
    tf = os.path.join(ROOT, "_mt_target.json")
    tat = json.load(open(tf, encoding="utf-8")) if os.path.exists(tf) else {}
    T = a.target or tat.get(a.ch) or float(np.median(allw)) * 0.8
    print("章 %s：%d 单元 / %d 候选   voiced wpm 中位 %.0f  目标 %.0f"
          % (a.ch, len(rows), sum(len(r["cands"]) for r in rows), np.median(allw), T))
    # 把目标写回文件，保证拼章阶段用的是同一个数（此前择优 189 / 拼章 191 就是没写回）
    tat[a.ch] = float(T)
    json.dump(tat, open(tf, "w", encoding="utf-8"), indent=1)

    os.makedirs(PICK, exist_ok=True)
    report, n_fb, n_single = [], 0, 0
    for r in rows:
        if not r["cands"]:
            r["flag"] = "MISSING"
            # 重要：候选目录里没有，就必须把旧 pick 删掉，否则拼章会用到过期音频
            stale = os.path.join(PICK, r["id"] + ".wav")
            if os.path.exists(stale):
                os.remove(stale)
            continue
        best, best_s = None, -1e9
        for c in r["cands"]:
            t_raw = T / c["wpm"] if c["wpm"] > 0 else 9.9
            # 后期只会做 t∈[0.70,1.00] 的拉伸（-0.70 是用户红线，>1.00 不加速）
            t_use = min(1.00, max(0.70, t_raw))
            final = c["wpm"] * t_use
            c["need_tempo"] = round(t_use, 3)
            c["final_wpm"] = round(final, 1)
            # ★ 关键：按「拉伸之后的语速」评分，而不是原始语速。
            #   否则 150wpm（不能加速）会打赢 280wpm（可拉到 196），完全搞反。
            s = 3.0 * c["ratio"]
            s += 2.5 * (c["spk"] if c["spk"] == c["spk"] else 0.0)
            s -= 2.0 * min(3.0, abs(final - T) / T * 3.0)
            s -= 1.0 * max(0.0, (c["centroid"] - 3400) / 600.0)
            if c["f0"] > 1:
                # 音高是「换人」的强信号：114Hz vs 80Hz 是 43% 偏差，比 15% 的音色亮度明显得多，
                # 所以 F0 权重必须高于 centroid。用户反复抱怨的就是这个。
                s -= 0.9 * min(3.0, abs(c["f0"] - 80) / 12.0)
            if c["tail_ok"]:
                s += 0.5
            c["score"] = s
            bad = (not c["tail_ok"]) or c["ratio"] < 0.78 or c["f0"] > 305
            # 0.70 红线内还压不到目标 30% 以内 ⇒ 实在太快，重生成
            bad = bad or final > T * 1.30
            bad = bad or c["centroid"] > 4600
            # ★ 音高出带是硬门槛（2026-10-21 ch3 教训）：213Hz/250Hz 这种不是"偏亮"，
            #   是彻底换人。此前只当扣分项 ⇒ MOS 门槛把 84Hz 的候选筛掉后，
            #   只剩 213Hz 的"干净"候选被选中。必须直接判死。
            if c["dur"] >= SR_MIN_DUR_F0 and c["f0"] > F0_CEIL:
                bad = True
            if c["mos"] is not None and c["mos"] < 2.5:
                bad = True
            c["bad"] = bad
            if not bad and s > best_s:
                best, best_s = c, s
        if best is None:
            best = max(r["cands"], key=lambda c: c["score"])
            n_fb += 1
            r["flag"] = "NEED-REGEN"
        if len(r["cands"]) == 1:
            n_single += 1
        shutil.copy2(best["path"], os.path.join(PICK, r["id"] + ".wav"))
        r["pick"] = best["seed"]
        report.append({"id": r["id"], "pick": best["seed"], "flag": r.get("flag", ""),
                       "text": r["text"],
                       "cands": [{k: _c(v) for k, v in c.items() if k != "path"}
                                 for c in r["cands"]]})

    out = os.path.join(ROOT, "_mt_score_%s.json" % a.ch)
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    fails = [r["id"] for r in rows if r.get("flag") in ("NEED-REGEN", "MISSING")]
    open(os.path.join(ROOT, "_mt_fail_%s.txt" % a.ch), "w").write(",".join(fails))
    if a.list_fail:
        print(",".join(fails)); return

    from collections import Counter
    print("择优 %d 条；硬门槛不过 %d 条；单候选 %d 条" % (len(report), n_fb, n_single))
    print("  选中 seed 分布:", dict(Counter(r["pick"] for r in rows if "pick" in r)))
    pick = []
    for c in report:
        seeds = [str(x["seed"]) for x in c["cands"]]
        if str(c["pick"]) in seeds:
            pick.append(c["cands"][seeds.index(str(c["pick"]))])
    if pick:
        w = np.array([x["wpm"] for x in pick])
        t = np.array([x["need_tempo"] for x in pick])
        print("  选中条 voiced wpm：中位 %.0f  p10–p90 %.0f–%.0f  最快 %.0f 最慢 %.0f"
              % (np.median(w), np.percentile(w, 10), np.percentile(w, 90), w.max(), w.min()))
        print("  所需 tempo：中位 %.2f  p5 %.2f  p95 %.2f  <0.70 %d 条  >1.00 %d 条"
              % (np.median(t), np.percentile(t, 5), np.percentile(t, 95),
                 (t < 0.70).sum(), (t > 1.00).sum()))
    if n_fb:
        print("  需重生成：")
        for r in rows:
            if r.get("flag") == "NEED-REGEN":
                print("    %s | %s" % (r["id"], r["text"][:64]))


if __name__ == "__main__":
    main()
