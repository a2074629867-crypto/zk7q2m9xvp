# -*- coding: utf-8 -*-
"""_proso_parse.py —— 把 Prosogram 的逐音节核表解析成可 join 的数据集。

    G:/Python310/python.exe _proso_parse.py

输入：
    _proso_all/*_data.txt      Prosogram 逐音节核（tab 分隔）
    _proso_map.json            安全文件名 -> tid
    _align_dataset.json        词级记录（拿 t0/t1/is_adv/nsyl）

输出：
    _proso.json                记录级
    _proso_words.csv           词级平表（tid + 词 + glissando）
    _proso_takes.csv           take 级平表（产出率、上滑/下滑数）

★ 为什么按时间映射而不是按标签：
  Prosogram 的 `_data.txt` 里 `rowLabel` 只写时间（`nucl_t1`），不写音节标签。
  它的 `syll` 层确实被读取了（日志 `Using syllable alignment from tier named <syll>`），
  只是标签没有落进这张表 ⇒ 用 `nucl_t1` 回落到我们自己的词区间，是精确的。

关键列含义（Prosogram 原生）：
    intrasyllab   音节核内部的音高变化，半音。**只在超过听感阈值 G 时非零**
                  （G = 0.16–0.32/T²，T=核时长；1997 年重合成听辨实验标定）
    intersyllab   到下一个核之间的变化，半音
    up / down     同一次变化的方向分列（up>0 或 down<0）
    trajectory    |intrasyllab|
    f0_discont    音高断点标记（八度跳变等）
    nucl_dur      音节核时长；syll_dur 整个音节区间时长
    promL2D_nucldur  L2D 提升量（核时长相对局部期望）
"""
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: os.path.join(ROOT, *p)
SRC = os.environ.get("PROSO_DIR") or J("_proso_all")

NUM = lambda v, d=0.0: (float(v) if v not in (None, "", "NA") else d)


def load_take(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"):
        if not r.get("nucl_t1"):
            continue
        intra = NUM(r.get("intrasyllab"))
        out.append(dict(
            t0=NUM(r.get("nucl_t1")), t1=NUM(r.get("nucl_t2")),
            dur=NUM(r.get("nucl_dur")), syll_dur=NUM(r.get("syll_dur")),
            f0_min=NUM(r.get("f0_min")), f0_max=NUM(r.get("f0_max")),
            f0_med=NUM(r.get("f0_median")), f0_start=NUM(r.get("f0_start")),
            f0_end=NUM(r.get("f0_end")),
            intra=intra, inter=NUM(r.get("intersyllab")),
            up=NUM(r.get("up")), down=NUM(r.get("down")),
            traj=NUM(r.get("trajectory")), discont=NUM(r.get("f0_discont")),
            loudness=NUM(r.get("loudness")), prom=NUM(r.get("promL2D_nucldur")),
        ))
    return out


PROF_KEEP = {
    "SpeechRate": "speech_rate", "NrofNuclei": "n_nucl_prof", "NrofSafe": "n_safe",
    "SpeechTime": "speech_time", "PropPhon": "prop_phon", "PropPause": "prop_pause",
    "F0MedianHz": "f0_med_hz", "F0StdevHz": "f0_sd_hz", "PitchRange": "pitch_range_st",
    "PitchTopST": "pitch_top_st", "PitchBottomST": "pitch_bot_st",
    "PropLevel": "prop_level", "Gliss": "prop_gliss", "Rises": "prop_rise",
    "Falls": "prop_fall", "TrajIntra": "traj_intra", "TrajInter": "traj_inter",
    "TrajPhon": "traj_phon", "TrajIntraZ": "traj_intra_z", "TrajInterZ": "traj_inter_z",
    "NuclDurMean": "nucl_dur_mean", "NuclDurStdev": "nucl_dur_sd",
    "nPVI_nucldur": "npvi_nucldur", "nPVI_sylldur": "npvi_sylldur",
    "nPVI_voweldur": "npvi_voweldur",
}


def load_profile(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"))
    if not rows:
        return {}
    r = rows[0]
    return {v: NUM(r.get(k)) for k, v in PROF_KEEP.items() if k in r}



def word_at(words, t):
    """核起点落在哪个词里；落在间隙就取最近的词边界。返回 (索引, 词)。"""
    for i, w in enumerate(words):
        if float(w["t0"]) <= t < float(w["t1"]):
            return i, w
    i = min(range(len(words)),
            key=lambda j: min(abs(t - float(words[j]["t0"])), abs(t - float(words[j]["t1"]))))
    return i, words[i]


def main():
    mp = json.load(open(J("_proso_map.json"), encoding="utf-8"))
    data = json.load(open(J("_align_dataset.json"), encoding="utf-8"))
    recs = {r["tid"]: r for r in data["records"]}

    takes, wrows, nu_all, profs = [], [], [], []
    seen = set()
    for f in sorted(glob.glob(os.path.join(SRC, "*_data.txt"))):
        if "_profile" in f:
            continue
        name = os.path.basename(f)[: -len("_data.txt")]
        if name not in mp:
            continue
        meta = mp[name]
        rec = recs.get(meta["tid"]) or {}
        words = [w for w in (rec.get("words") or []) if w.get("t0") is not None]
        if not words:
            continue
        nu = load_take(f)
        seen.add(name)
        if not nu:
            continue

        # ---- 核 -> 词（按词实例，不按词形：一句里两个 "the" 不能混）----
        byw = {}
        for x in nu:
            wi, w = word_at(words, x["t0"])
            byw.setdefault(wi, []).append(x)
            nu_all.append(dict(tid=meta["tid"], gid=meta["gid"], kind=meta["kind"],
                               side=rec.get("side"), word=w.get("key") or "",
                               pos=w.get("pos"), is_adv=(w.get("key") == (meta.get("adv") or "")),
                               **{k: x[k] for k in ("t0", "t1", "dur", "f0_med",
                                                    "f0_start", "f0_end", "intra", "inter",
                                                    "up", "down", "traj", "discont",
                                                    "loudness", "prom")}))

        # 整条 take 的核时长中位（做词内相对时长用）
        durs = sorted(x["dur"] for x in nu)
        med_dur = durs[len(durs) // 2] if durs else 0.0

        for wi, lst in byw.items():
            w = words[wi]
            wk = w.get("key") or ""
            ups = sum(1 for x in lst if x["up"] > 0)
            dns = sum(1 for x in lst if x["down"] < 0)
            mx = max((abs(x["intra"]) for x in lst), default=0.0)
            rel_d = (sum(x["dur"] for x in lst) / len(lst)) / med_dur if med_dur else 0.0
            wrows.append(dict(
                tid=meta["tid"], gid=meta["gid"], kind=meta["kind"], side=rec.get("side"),
                word=wk, pos=w.get("pos"), is_adv=(wk == (meta.get("adv") or "")),
                rel_z=w.get("rel_z"), loc=w.get("loc"), sps=w.get("sps"),
                n_nuclei=len(lst), n_up=ups, n_down=dns, n_move=ups + dns,
                glide=("up" if ups and not dns else "down" if dns and not ups
                       else "both" if ups and dns else "level"),
                max_abs_intra=round(mx, 2),
                sum_intra=round(sum(x["intra"] for x in lst), 2),
                mean_dur=round(sum(x["dur"] for x in lst) / len(lst), 3),
                rel_dur=round(rel_d, 2),
                f0_med=round(sorted(x["f0_med"] for x in lst)[len(lst) // 2], 1),
                f0_range=round(max(x["f0_max"] for x in lst) - min(x["f0_min"] for x in lst), 1),
                loudness=round(max(x["loudness"] for x in lst), 1),
            ))

        adv = [x for i, lst in byw.items() if (words[i].get("key") or "") == (meta.get("adv") or "")
               for x in lst]
        takes.append(dict(
            tid=meta["tid"], gid=meta["gid"], kind=meta["kind"],
            side=rec.get("side"), adv=meta.get("adv"),
            seed=(rec.get("take") or {}).get("seed"),
            cond=(rec.get("take") or {}).get("cond"),
            n_iv=meta.get("n_syll_cmu") or 0, n_nucl=len(nu),
            yield_rate=round(len(nu) / max(1, meta.get("n_syll_cmu") or 1), 3),
            n_up=sum(1 for x in nu if x["up"] > 0),
            n_down=sum(1 for x in nu if x["down"] < 0),
            n_level=sum(1 for x in nu if abs(x["intra"]) < 1e-9),
            mean_abs_intra=round(sum(abs(x["intra"]) for x in nu) / len(nu), 2),
            max_abs_intra=round(max(abs(x["intra"]) for x in nu), 2),
            med_nucl_dur=round(med_dur, 3),
            adv_nucl=len(adv),
            adv_move=sum(1 for x in adv if x["up"] > 0 or x["down"] < 0),
            adv_up=sum(1 for x in adv if x["up"] > 0),
            adv_down=sum(1 for x in adv if x["down"] < 0),
            adv_max_intra=round(max((abs(x["intra"]) for x in adv), default=0.0), 2),
            adv_intra=round(sum(x["intra"] for x in adv), 2) if adv else 0.0,
            adv_rel_dur=round((sum(x["dur"] for x in adv) / len(adv)) / med_dur, 2) if adv and med_dur else 0.0,
        ))

        # ---- prosodic profile（整条 take 的韵律画像：nPVI / glissando 分布 / 音域）----
        pf = os.path.join(SRC, name + "_profile_data.txt")
        if os.path.exists(pf):
            p = load_profile(pf)
            if p:
                p.update(tid=meta["tid"], gid=meta["gid"], kind=meta["kind"],
                         side=rec.get("side"), adv=meta.get("adv"))
                profs.append(p)

    json.dump(dict(n_takes=len(takes), n_words=len(wrows), n_nuclei=len(nu_all),
                   n_profiles=len(profs), takes=takes, words=wrows, nuclei=nu_all,
                   profiles=profs),
              open(J("_proso.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def dump(path, cols, rows):
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)

    dump(J("_proso_words.csv"),
         ["tid", "gid", "kind", "side", "word", "pos", "is_adv", "rel_z", "loc", "sps", "n_nuclei", "n_up", "n_down",
          "n_move", "glide", "max_abs_intra", "sum_intra", "mean_dur", "rel_dur",
          "f0_med", "f0_range", "loudness"], wrows)
    dump(J("_proso_takes.csv"),
         ["tid", "gid", "kind", "side", "adv", "seed", "cond", "n_iv", "n_nucl", "yield_rate",
          "n_up", "n_down", "n_level", "mean_abs_intra", "max_abs_intra", "med_nucl_dur",
          "adv_nucl", "adv_move", "adv_up", "adv_down", "adv_max_intra", "adv_intra",
          "adv_rel_dur"], takes)
    dump(J("_proso_nuclei.csv"),
         ["tid", "gid", "kind", "side", "word", "pos", "is_adv", "t0", "t1", "dur", "f0_med",
          "f0_start", "f0_end", "intra", "inter", "up", "down", "traj", "discont",
          "loudness", "prom"], nu_all)
    dump(J("_proso_profile.csv"),
         ["tid", "gid", "kind", "side", "adv"] + list(PROF_KEEP.values()), profs)

    iv = sum(t["n_iv"] for t in takes)
    nu = sum(t["n_nucl"] for t in takes)
    print("→ _proso.json  %d 条 take / %d 个词 / %d 个核" % (len(takes), len(wrows), len(nu_all)))
    print("  音节区间 %d  识别出核 %d  总产出率 %.0f%%" % (iv, nu, 100.0 * nu / max(1, iv)))
    miss = [k for k in mp if k not in seen]
    print("  未产出（Prosogram 失败或无核）: %d 条" % len(miss))
    for k in miss[:5]:
        print("    ", mp[k]["tid"])


if __name__ == "__main__":
    main()
