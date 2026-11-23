# -*- coding: utf-8 -*-
"""重音测试（现行定义）：**强调 = 一般落在副词上**。

与旧 `_stress_loop3.py` 的区别：
  - 旧脚本的被测目标是「人工标注 level 的词」（含名词/动词，混着走）；
  - 本脚本只问一件事：**副词有没有被读重**。副词是强调的默认落点。

判据沿用 STRESS_PLAYBOOK §1.4 第四代 rel_z（唯一现行）：
    sps  = 词时长 / 音节数（cmudict）
    rel  = sps / 句中位           # 句内归一，消掉句间语速差
    rel_z = (log(rel) - A - B*log(nsyl)) / SD
  A/B/SD 取 `_align_baseline.json`（真人 159 句 / 931 词拟合），
  所以数值与 playbook 里的 p95=1.47、阈值 1.6 同一把尺子。

为什么要用 `_wl_words.json` + `out_bak_prepause` 这一对：
  词级时间戳是在 `out_bak_prepause` 上做的（c1_0001 7.424s / c1_0003 9.475s 完全吻合），
  而 `out` 只是它的首尾 trim 版。rel_z 是句内归一，trim 不改相对时长 ⇒ 两者等价，
  用这一对可以完全避开 gap 映射。

用法：
  G:/Python310/python.exe -u _stress_adv.py
  G:/Python310/python.exe -u _stress_adv.py --dir _audio_ch123/out_bak_prepause --wl _wl_words.json
"""
import argparse
import io
import json
import math
import os
import re
import statistics as st

import numpy as np
import soundfile as sf

ROOT = r"G:/_setup"
BASE = os.path.join(ROOT, "_align_baseline.json")
PUNCT = ".,;:!?'\"()[]—-…“”‘’"

# ---- 副词判定 ----------------------------------------------------------
# 1) -ly 结尾，但要排掉「长得像副词其实不是」的一批
NOT_ADV_LY = set("""
only family reply apply supply likely lovely lonely silly ugly early daily weekly
friendly elderly holy jelly belly fly july italy assembly anomaly multiply imply
comply rely rally bully folly melancholy ally billy lily holly molly curly surly
ghastly costly deadly lively orderly cowardly scholarly stately timely unlikely
brotherly heavenly kindly monthly yearly hourly quarterly nightlife
""".split())
# 2) 没有 -ly 的常用副词（强调落点里很常见的一批）
ADV_NO_LY = set("""
very quite almost never always often sometimes seldom rarely just still already
again now then too even well fast hard late soon once twice ever hardly barely
scarcely rather somewhat much more most less least here there away back down out
off together alone instead perhaps maybe indeed so not no yes abroad ahead apart
aside ashore upward downward forward backward inward outward toward afterwards
""".split())
# 3) 明显不是强调对象的副词：否定/程度/指示/小品词，英语里天然弱读
#    （out/down/back/away 是短语动词的小品词，读轻是正确读法，不是缺陷）
ADV_SKIP = set("""
not no yes so too very quite rather somewhat much more most less least just only
even still already then now here there out down back away off up in through over
along around about apart ahead aside ever almost together alone instead
""".split())
# 4) 真正的「强调落点」：方式副词（-ly）+ 频率副词 + 少数无 -ly 方式副词
ADV_EMPH = set("""
never always often sometimes seldom rarely again once twice well fast hard badly
perhaps maybe indeed certainly probably actually really simply merely truly
finally suddenly quietly slowly carefully gently softly coldly warmly sharply
quickly calmly slowly politely kindly honestly frankly seriously completely
entirely absolutely totally utterly barely hardly scarcely
""".split())


def is_adv(w, wide=False):
    x = w.strip(PUNCT).lower()
    if not x or len(x) < 3:
        return False
    if wide:
        if x in NOT_ADV_LY:
            return False
        if x in ADV_NO_LY:
            return True
        return x.endswith("ly")
    # 严格口径：只认强调副词
    if x in ADV_SKIP or x in NOT_ADV_LY:
        return False
    if x in ADV_EMPH:
        return True
    return x.endswith("ly")


def clean(w):
    return w.strip(PUNCT).lower()


# ---- 音节数（cmudict 优先，缺失走元音组启发式）--------------------------
try:
    import cmudict
    _CMU = cmudict.dict()
except Exception:
    _CMU = {}


def nsyl(w):
    x = clean(w)
    if not x:
        return 0
    if x in _CMU:
        return max(1, len([p for p in _CMU[x][0] if p[-1].isdigit()]))
    if "-" in x:
        n = sum(nsyl(p) for p in x.split("-") if p)
        if n:
            return n
    # 启发式：元音组数，末尾不发音 e 扣掉
    v = re.findall(r"[aeiouy]+", x)
    n = len(v)
    if x.endswith("e") and n > 1 and not x.endswith("le"):
        n -= 1
    return max(1, n)


def auc(pos, neg):
    if not pos or not neg:
        return 0.5
    allv = np.array(list(pos) + list(neg), float)
    r = np.argsort(np.argsort(allv)) + 1
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0)
                 / (len(pos) * len(neg)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="_audio_ch123/out_bak_prepause")
    ap.add_argument("--wl", default="_wl_words.json")
    ap.add_argument("--tag", default="before")
    ap.add_argument("--only", default="",
                    help="只测这批 sid（逗号分隔或文件，每行一个）。用于新旧同口径对比")
    a = ap.parse_args()

    bl = json.load(io.open(BASE, encoding="utf-8"))
    A, B, SD = bl["A"], bl["B"], bl["SD"]
    print("基线 %s：n_words=%d A=%.4f B=%.4f SD=%.4f"
          % (bl["tag"], bl["n_words"], A, B, SD), flush=True)

    wl = json.load(io.open(os.path.join(ROOT, a.wl), encoding="utf-8"))
    # 按 basename 建索引：换任何目录（out / _regen_1123）都能对上，不再写死路径
    wl_by_sid = {}
    for k, v in wl.items():
        wl_by_sid[os.path.basename(k).rsplit(".", 1)[0]] = v
    ids = json.load(io.open(os.path.join(ROOT, "_narr_ids716.json"), encoding="utf-8"))
    if a.only:
        if os.path.exists(a.only):
            keep = [ln.strip() for ln in io.open(a.only, encoding="utf-8") if ln.strip()]
        else:
            keep = [x.strip() for x in a.only.split(",") if x.strip()]
        ks = set(keep)
        ids = [i for i in ids if i in ks]
        print("限定 %d 句" % len(ids), flush=True)

    adv_z, non_z, adv_pct, non_pct = [], [], [], []
    w_adv_z, w_non_z, w_adv_pct = [], [], []
    rows, per_adv, miss = [], {}, {}
    n_sent = n_word = n_adv = 0
    top1_adv = top3_adv = 0
    w_top1 = w_top3 = w_nadv = 0

    for sid in ids:
        p = os.path.join(ROOT, a.dir, sid + ".wav")
        rec = wl_by_sid.get(sid)
        if not rec or not os.path.exists(p):
            continue
        try:
            y, sr = sf.read(p, dtype="float32")
        except Exception:
            continue
        if getattr(y, "ndim", 1) > 1:
            y = y.mean(1)
        wav_dur = len(y) / float(sr)
        if abs(wav_dur - float(rec.get("dur") or 0)) > 0.05:
            # 时间戳与音频不同源，跳过（宁缺勿错）
            continue

        ws = []
        for w in rec["words"]:
            d = clean(w["w"])
            if not d:
                continue
            ns = nsyl(w["w"])
            if ns <= 0:
                continue
            dur = max(1e-3, float(w["end"]) - float(w["start"]))
            ws.append(dict(w=d, raw=w["w"], ns=ns, dur=dur, sps=dur / ns))
        if len(ws) < 3:
            continue

        med = st.median([x["sps"] for x in ws])
        if med <= 0:
            continue
        for x in ws:
            x["rel"] = x["sps"] / med
            x["z"] = (math.log(x["rel"]) - A - B * math.log(max(1, x["ns"]))) / SD

        n_sent += 1
        n_word += len(ws)
        zs = np.array([x["z"] for x in ws])
        order = np.argsort(-zs)
        rank = np.empty(len(ws), int)
        rank[order] = np.arange(1, len(ws) + 1)
        for i, x in enumerate(ws):
            x["pct"] = 1.0 - (rank[i] - 1) / max(1, len(ws) - 1)
            x["occ"] = sum(1 for j in range(i) if ws[j]["w"] == x["w"])

        ad = [x for x in ws if is_adv(x["w"])]
        wad = [x for x in ws if is_adv(x["w"], wide=True)]
        nd = [x for x in ws if not is_adv(x["w"])]
        if wad:
            w_nadv += len(wad)
            w_adv_z.extend([x["z"] for x in wad])
            w_non_z.extend([x["z"] for x in ws if not is_adv(x["w"], wide=True)])
            w_adv_pct.extend([x["pct"] for x in wad])
            if is_adv(ws[order[0]]["w"], wide=True):
                w_top1 += 1
            if any(is_adv(ws[order[i]]["w"], wide=True)
                   for i in range(min(3, len(ws)))):
                w_top3 += 1
        if not ad:
            continue
        n_adv += len(ad)
        adv_z.extend([x["z"] for x in ad])
        non_z.extend([x["z"] for x in nd])
        adv_pct.extend([x["pct"] for x in ad])
        non_pct.extend([x["pct"] for x in nd])
        if is_adv(ws[order[0]]["w"]):
            top1_adv += 1
        if any(is_adv(ws[order[i]]["w"]) for i in range(min(3, len(ws)))):
            top3_adv += 1

        for x in ad:
            per_adv.setdefault(x["w"], []).append(x["z"])
            if x["z"] < 0.0:
                miss.setdefault(x["w"], []).append(
                    {"sid": sid, "z": round(x["z"], 2), "pct": round(x["pct"], 2),
                     "occ": x["occ"], "dur": round(x["dur"], 3)})
        rows.append({"sid": sid, "n": len(ws), "n_adv": len(ad),
                     "adv_z_max": round(float(max(x["z"] for x in ad)), 2),
                     "adv_z_mean": round(float(np.mean([x["z"] for x in ad])), 2)})

    out = {
        "tag": a.tag, "dir": a.dir,
        "n_sent": n_sent, "n_word": n_word, "n_adv": n_adv,
        "auc_adv": auc(adv_z, non_z),
        "adv_z_mean": round(float(np.mean(adv_z)), 3) if adv_z else None,
        "adv_z_median": round(float(np.median(adv_z)), 3) if adv_z else None,
        "non_z_mean": round(float(np.mean(non_z)), 3) if non_z else None,
        "adv_pct_mean": round(100 * float(np.mean(adv_pct)), 1) if adv_pct else None,
        "non_pct_mean": round(100 * float(np.mean(non_pct)), 1) if non_pct else None,
        "adv_ge_16": int(sum(1 for z in adv_z if z >= 1.6)),
        "adv_lt_0": int(sum(1 for z in adv_z if z < 0.0)),
        "top1_adv_rate": round(100.0 * top1_adv / max(1, n_sent), 1),
        "top3_adv_rate": round(100.0 * top3_adv / max(1, n_sent), 1),
        "top_adv": sorted(((w, len(v), round(float(np.mean(v)), 2))
                           for w, v in per_adv.items() if len(v) >= 3),
                          key=lambda t: -t[2])[:15],
        "weak_adv": sorted(((w, len(v), round(float(np.mean(v)), 2))
                            for w, v in per_adv.items() if len(v) >= 3),
                           key=lambda t: t[2])[:15],
        "wide": {
            "n_adv": w_nadv,
            "auc_adv": auc(w_adv_z, w_non_z),
            "adv_z_mean": round(float(np.mean(w_adv_z)), 3) if w_adv_z else None,
            "adv_pct_mean": round(100 * float(np.mean(w_adv_pct)), 1) if w_adv_pct else None,
            "adv_ge_16": int(sum(1 for z in w_adv_z if z >= 1.6)),
            "adv_lt_0": int(sum(1 for z in w_adv_z if z < 0.0)),
            "top1_adv_rate": round(100.0 * w_top1 / max(1, n_sent), 1),
            "top3_adv_rate": round(100.0 * w_top3 / max(1, n_sent), 1),
        },
        "miss_rank": sorted(((w, len(v), round(float(np.mean([q["z"] for q in v])), 2))
                             for w, v in miss.items()),
                            key=lambda t: (t[2], -t[1]))[:20],
        "miss_sample": [dict(w=w, **v[0]) for w, v in
                        sorted(miss.items(), key=lambda kv: kv[1][0]["z"])[:15]],
        # 回环第 4 步的输入：逐条列出所有 z<0 的强调副词实例（按 z 升序）
        "weak_instances": sorted(
            [dict(w=w, **q) for w, v in miss.items() for q in v],
            key=lambda x: x["z"]),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000], flush=True)
    dst = os.path.join(ROOT, "_stress_adv_%s.json" % a.tag)
    json.dump(out, io.open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写入 %s" % dst, flush=True)


if __name__ == "__main__":
    main()
