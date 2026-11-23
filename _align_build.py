# -*- coding: utf-8 -*-
"""_align_build.py —— 把「旁白 take」与「真人母带」采集到同一份数据集。

    G:/Python310/python.exe _align_build.py            # 全量
    G:/Python310/python.exe _align_build.py --limit 5  # 冒烟

产出（均在 G:/_setup/）：
    _align_dataset.json   记录级（含每个词的全部字段）
    _align_words.csv      词级平表，一行一个词（Excel 可开）
    _align_takes.csv      take 级平表，一行一条 take
    _align_baseline.json  真人拟合系数 + 各层参照分位

真人侧过滤与 `_anchor_analyze.py` **逐条一致**，否则复现不出 159 句 / 931 词。
旁白侧不套那套过滤（take 是我们自己生成的，漏词用 synthetic_share 暴露，不静默丢）。
"""
import argparse
import csv
import glob
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _adv_prom as P
import _align_lib as L

ROOT = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: os.path.join(ROOT, *p)
STATE = J("_mt_adv_state.json")


# ============================ 真人侧 ============================

def human_records(limit=0):
    meta = json.load(open(J("_anchor_meta.json"), encoding="utf-8"))
    asr = {os.path.normpath(k): v for k, v in
           json.load(open(J("_anchor_asr.json"), encoding="utf-8")).items()}
    recs, dropped = [], []
    wids = sorted(meta)
    if limit:
        wids = wids[:limit]
    for wid in wids:
        m = meta[wid]
        wav = J("_anchor_stage", "_anchor__%s.wav" % wid)
        prom = J("_wpt_out", "_anchor__%s.prom" % wid)
        # ⚠️ _anchor_asr.json 的键是**绝对路径**（normpath 后），用相对路径查必然 miss
        a = asr.get(os.path.normpath(os.path.abspath(wav))) or {}
        asr_words = [w.get("w") if isinstance(w, dict) else w
                     for w in (a.get("words") or [])]
        asr_words = [w for w in asr_words if w and re.search(r"[A-Za-z]", str(w))]
        reason, cws = L.human_filter_reason(wav, prom, m["text"], asr_words)
        if reason:
            dropped.append([wid, reason])
            continue
        mt = L.measure_take(wav, prom, m["text"], cws=cws)
        if not mt:
            dropped.append([wid, "measure_take 失败"])
            continue
        recs.append(_rec("h:%s" % wid, "human", wid, None, m["text"], None,
                         wav, prom, mt))
    return recs, dropped


# ============================ 旁白侧 ============================

def _attempt_specs():
    st = json.load(open(STATE, encoding="utf-8"))["units"]
    out = []
    for u, x in sorted(st.items()):
        out.append(("%s:delivered" % u, u, "delivered", None, None,
                    J("_mt_pick", "%s.wav" % u), J("_wpt_out", "_mt_pick__%s.prom" % u)))
        pw, pp = J("_mt_pick_prev", "%s.wav" % u), J("_wpt_out", "_mt_pick_prev__%s.prom" % u)
        if os.path.exists(pw) and os.path.exists(pp):
            out.append(("%s:prev" % u, u, "prev", None, None, pw, pp))

        seen = set()
        for a in (x.get("attempts") or []):
            seed, cond = a.get("seed"), a.get("cond")
            for kind, wav, mk in (
                    ("cand", a.get("wav"), lambda s: J("_mt_adv_prom_%s" % s, "%s.prom" % u)),
                    ("ctl", a.get("ctl_wav"), lambda s: J("_mt_adv_prom_ctl_%s" % s, "%s.prom" % u))):
                if not wav:
                    continue
                key = (kind, os.path.realpath(wav))
                if key in seen:
                    continue
                seen.add(key)
                out.append(("%s:%s:%s" % (u, seed, kind), u, kind, seed, cond,
                            wav, mk(seed)))
    return out


_PAT = re.compile(r"^(N\d+)_([a-z0-9]+)_s(\d+)$")


def _dir_specs(dirname, kind, prom_prefixes):
    out = []
    for wav in sorted(glob.glob(J(dirname, "*.wav"))):
        stem = os.path.basename(wav)[:-4]
        m = _PAT.match(stem)
        if not m:
            continue
        uid, cond, seed = m.group(1), m.group(2), int(m.group(3))
        prom = None
        for pre in prom_prefixes:
            p = J("_wpt_out", "%s__%s.prom" % (pre, stem))
            if os.path.exists(p):
                prom = p
                break
        out.append(("%s:%s:%s" % (uid, seed, kind), uid, kind, seed, cond, wav,
                    prom or J("_wpt_out", "%s__%s.prom" % (prom_prefixes[0], stem))))
    return out


def narr_specs():
    return _attempt_specs() + _dir_specs("_adv_tts", "tts", ["_adv_tts", "_r5"]) \
        + _dir_specs("_adv_edit", "edit", ["_adv_edit"])


def narr_records(limit=0):
    st = json.load(open(STATE, encoding="utf-8"))["units"]
    specs = narr_specs()
    if limit:
        specs = specs[:limit]
    recs, missing = [], []
    for gid, u, kind, seed, cond, wav, prom in specs:
        if not (os.path.exists(wav) and os.path.exists(prom or "")):
            missing.append([gid, "wav" if not os.path.exists(wav) else "prom"])
            continue
        x = st[u]
        mt = L.measure_take(wav, prom, x["text"], adv=x["adv"])
        if not mt:
            missing.append([gid, "measure_take 失败"])
            continue
        take = dict(kind=kind, seed=seed, cond=cond)
        recs.append(_rec("n:%s" % gid, "narr", u, take, x["text"], x["adv"],
                         wav, prom, mt))
    return recs, missing


# ============================ 公共 ============================

def _rec(gid, side, uid, take, text, adv, wav, prom, mt):
    md5 = L.md5(wav)
    kind = (take or {}).get("kind") or ""
    seed = (take or {}).get("seed") or ""
    # tid = 唯一 take 键。uid 只是「单元」级（N0034 会有 8 条 take 共用），不能做 join 键。
    tid = "%s|%s|%s|%s" % (gid, kind, seed, md5[:8])
    return dict(
        gid=gid, tid=tid, side=side, uid=uid, take=take, text=text, adv=adv,
        n_content=mt["n_content"], low_context=mt["n_content"] < L.LOW_CONTEXT_N,
        synthetic_share=mt["synthetic_share"], med_sps=mt["med_sps"],
        wav=os.path.relpath(wav, ROOT).replace("\\", "/"),
        prom=os.path.relpath(prom, ROOT).replace("\\", "/"),
        md5=md5, prom_mtime=round(os.path.getmtime(prom), 1),
        words=mt["words"])


def dedupe_tids(records):
    """同一音频可能被 state 里的多条路径指向（seed=2031 出现过三份）⇒ tid 加 ~N 后缀保证 1:1。"""
    seen = {}
    for r in records:
        t = r["tid"]
        if t in seen:
            seen[t] += 1
            r["tid"] = "%s~%d" % (t, seen[t])
        else:
            seen[t] = 1
    ids = [r["tid"] for r in records]
    assert len(ids) == len(set(ids)), "tid 仍然重复"
    return records


def adv_row(rec):
    if not rec.get("adv"):
        return None
    hits = [w for w in rec["words"] if w.get("is_adv")]
    return hits[-1] if hits else None


WORD_COLS = ["gid", "tid", "side", "uid", "kind", "seed", "cond", "adv", "is_adv",
             "w", "key", "nsyl", "t0", "t1", "span", "voiced", "speech", "share",
             "rms_x", "sps", "rel", "rel_ex", "rel_nb", "rel_z", "loc", "lin",
             "peak", "raw_peak", "p90", "n_fr", "rank", "pos", "last",
             "synthetic", "n_content", "low_context"]

TAKE_COLS = ["gid", "tid", "side", "uid", "kind", "seed", "cond", "adv", "nsyl",
             "n_content", "low_context", "synthetic_share", "med_sps",
             "w", "t0", "t1", "span", "voiced", "speech", "share", "rms_x",
             "sps", "rel", "rel_ex", "rel_nb", "rel_z", "loc", "lin", "rank", "pos", "last",
             "md5", "wav", "prom"]


def write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    print("== 真人侧 ==")
    hrecs, hdrop = human_records(a.limit)
    print("  有效 %d 句 / %d 词；丢弃 %d" % (
        len(hrecs), sum(r["n_content"] for r in hrecs), len(hdrop)))
    from collections import Counter
    print("  丢弃原因:", Counter(r for _, r in hdrop).most_common(6))

    print("== 旁白侧 ==")
    nrecs, nmiss = narr_records(a.limit)
    print("  有效 %d 条 take / %d 词；缺件 %d" % (
        len(nrecs), sum(r["n_content"] for r in nrecs), len(nmiss)))
    if nmiss:
        print("  缺件:", nmiss[:8])
    print("  分组:", Counter(r["take"]["kind"] for r in nrecs).most_common())

    print("== 拟合音节基线（真人）==")
    bl = L.fit_baseline(hrecs, tag="human")
    bl["at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("  log(rel) = %.4f + %.4f*log(nsyl)   r=%.3f  sd=%.4f  n=%d"
          % (bl["A"], bl["B"], bl["r"], bl["SD"], bl["n_words"]))

    for r in hrecs + nrecs:
        L.apply_rel_z(r, bl)

    ref = L.build_reference(hrecs)
    bl["ref"] = ref
    L.save_baseline(bl)
    print("  baseline → _align_baseline.json")

    data = dict(
        built=bl["at"],
        note="真人侧与旁白侧共用 _align_lib.measure_take；rel 分母=句内全部内容词 sps 中位；"
             "tid=(gid|kind|seed|md5[0:8]) 是唯一 take 键，(tid,pos) 可 1:1 join 词表",
        baseline=dict(A=bl["A"], B=bl["B"], SD=bl["SD"], r=bl["r"], n_words=bl["n_words"]),
        n_human=len(hrecs), n_narr=len(nrecs),
        dropped=hdrop, missing=nmiss,
        records=dedupe_tids(hrecs + nrecs))
    out = a.out or J("_align_dataset.json")
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("  → %s (%.1f MB)" % (os.path.basename(out), os.path.getsize(out) / 1e6))

    # ---- 词级 CSV ----
    wrows = []
    for r in data["records"]:
        for w in r["words"]:
            d = dict(w)
            d.update(gid=r["gid"], tid=r["tid"], side=r["side"], uid=r["uid"],
                     kind=(r["take"] or {}).get("kind"),
                     seed=(r["take"] or {}).get("seed"),
                     cond=(r["take"] or {}).get("cond"),
                     adv=r["adv"], n_content=r["n_content"],
                     low_context=r["low_context"])
            wrows.append(d)
    write_csv(J("_align_words.csv"), WORD_COLS, wrows)
    print("  → _align_words.csv (%d 行)" % len(wrows))

    # ---- take 级 CSV ----
    trows = []
    for r in data["records"]:
        d = dict(gid=r["gid"], tid=r["tid"], side=r["side"], uid=r["uid"], adv=r["adv"],
                 n_content=r["n_content"], low_context=r["low_context"],
                 synthetic_share=r["synthetic_share"], med_sps=r["med_sps"],
                 md5=r["md5"], wav=r["wav"], prom=r["prom"])
        d.update(r["take"] or {})
        ar = adv_row(r)
        if ar:
            d.update(ar)
        trows.append(d)
    write_csv(J("_align_takes.csv"), TAKE_COLS, trows)
    print("  → _align_takes.csv (%d 行)" % len(trows))

    # ---- 自检 ----
    assert len(wrows) == sum(r["n_content"] for r in data["records"]), "行数自洽失败"
    keys = [(x["tid"], x["pos"]) for x in wrows]
    assert len(keys) == len(set(keys)), "词表 join 键 (tid,pos) 不唯一"
    assert len(trows) == len(data["records"]), "takes 行数与记录数不符"
    print("  自检：词行数 == sum(n_content) ✓  (tid,pos) 唯一 ✓  403 条 take 1:1 ✓")


if __name__ == "__main__":
    main()
