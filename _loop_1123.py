# -*- coding: utf-8 -*-
"""旁白重音回环（四步一体，可重入）：测 → 重生成 → 再测 → 只对失败项抽 seed 重生成。

用户要的「回环」就是这四步，缺一步都不算闭：
  1) test   在现役音频上测「强调副词有没有被读重」           → _stress_adv_<tag>.json
  2) regen  按新标准 plan 重生成（1.00 / 0.84）              → _regen_1123/
  3) retest 对新音频再测同一指标（需先 ASR 出词级时间戳）      → _stress_adv_after.json
  4) repick 只对第 3 步仍失败的副词，换 seed 重出整句、按 rel_z 择优 → _loop_pick/

为什么第 4 步只能抽 seed、不能加标签：
  DECISIONS 2026-11-21 已证词级 `<rate>` 无拉长效果（0.70 与 1.40 时长完全相同），
  `<pitch>` 只在句末有效 ⇒ 唯一可用杠杆是「整句重出 + rel_z 判优」。

判据一律 rel_z（`_align_baseline.json` 真人拟合 A/B/SD），与 playbook p95=1.47 同一把尺子。

用法：
  G:/Python310/python.exe -u _loop_1123.py --stage asr
  G:/Python310/python.exe -u _loop_1123.py --stage test --tag after
  G:/Python310/python.exe -u _loop_1123.py --stage plan --limit 30
  G:/Python310/python.exe -u _loop_1123.py --stage repick --seeds 43,44,45
  G:/Python310/python.exe -u _loop_1123.py --stage all
"""
import argparse
import glob
import io
import json
import math
import os
import shutil
import statistics as st
import subprocess
import sys
import time

ROOT = r"G:/_setup"
PY = r"G:/Python310/python.exe"
ASR_PY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")
PLAN = os.path.join(ROOT, "_castle_en_ch123_plan_v2.jsonl")
IDS = os.path.join(ROOT, "_narr_ids716.json")
BASE = os.path.join(ROOT, "_align_baseline.json")

sys.path.insert(0, ROOT)
from _stress_adv import is_adv, clean, nsyl  # noqa: E402

_BL = json.load(io.open(BASE, encoding="utf-8"))
A, B, SD = _BL["A"], _BL["B"], _BL["SD"]


def run(cmd, timeout=3600, quiet=False):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if not quiet:
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        for ln in tail[-3:]:
            print("    " + ln, flush=True)
    return r


def list_wavs(d):
    return sorted(p.replace("\\", "/") for p in glob.glob(os.path.join(ROOT, d, "*.wav"))
                  if not os.path.basename(p).startswith("_raw_"))


# ---------------------------------------------------------------- stage asr
def stage_asr(d, wl):
    wavs = list_wavs(d)
    if not wavs:
        print("没有 wav"); return
    lp = os.path.join(ROOT, "_loop_asr_list.txt")
    io.open(lp, "w", encoding="utf-8").write("\n".join(wavs))
    print("ASR %d 条 → %s" % (len(wavs), wl), flush=True)
    run([ASR_PY, "_wl_asr.py", "--list", lp, "--out", wl, "--append"], timeout=10800)


# --------------------------------------------------------------- stage test
def stage_test(d, wl, tag):
    print("重音测试 dir=%s tag=%s" % (d, tag), flush=True)
    run([PY, "-u", "_stress_adv.py", "--dir", d, "--wl", wl, "--tag", tag], timeout=3600)
    p = os.path.join(ROOT, "_stress_adv_%s.json" % tag)
    return json.load(io.open(p, encoding="utf-8"))


# --------------------------------------------------------------- stage plan
def stage_plan(after, limit):
    weak = after.get("weak_instances") or []
    # 只挑强调副词、且确实读平了的；一个词在库里反复失败时优先处理
    tgt = [x for x in weak if x["z"] < 0.0]
    tgt.sort(key=lambda x: (x["z"], x["w"]))
    if limit:
        tgt = tgt[:limit]
    p = os.path.join(ROOT, "_loop_targets.json")
    json.dump(tgt, io.open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("目标 %d 条（z<0 的强调副词实例）→ %s" % (len(tgt), p), flush=True)
    for x in tgt[:10]:
        print("   %-9s %-12s z=%+.2f occ=%d" % (x["sid"], x["w"], x["z"], x.get("occ", 0)))
    return tgt


# ------------------------------------------------------------ rel_z 计算
def word_zs(rec):
    ws = []
    for w in rec.get("words") or []:
        d = clean(w["w"])
        if not d:
            continue
        ns = nsyl(w["w"])
        if ns <= 0:
            continue
        dur = max(1e-3, float(w["end"]) - float(w["start"]))
        ws.append(dict(w=d, ns=ns, dur=dur, sps=dur / ns))
    if len(ws) < 3:
        return ws
    med = st.median([x["sps"] for x in ws])
    if med <= 0:
        return ws
    for x in ws:
        x["z"] = (math.log(x["sps"] / med) - A - B * math.log(max(1, x["ns"]))) / SD
    return ws


def z_of(ws, word, occ=0):
    hits = [x for x in ws if x["w"] == word]
    if len(hits) <= occ:
        return None
    return hits[occ]["z"]


# ------------------------------------------------------------- stage repick
def stage_repick(targets, seeds, limit):
    if not targets:
        p = os.path.join(ROOT, "_loop_targets.json")
        targets = json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else []
    if limit:
        targets = targets[:limit]
    if not targets:
        print("没有目标"); return []

    plan = {json.loads(l)["id"]: json.loads(l)
            for l in io.open(PLAN, encoding="utf-8") if l.strip()}
    # 同一句可能有多个副词失败 ⇒ 按句聚合，一句只抽一次 seed
    by_sid = {}
    for t in targets:
        by_sid.setdefault(t["sid"], []).append(t)

    orig_wl = {}
    for f in ["_wl_regen1123.json"]:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            for k, v in json.load(io.open(p, encoding="utf-8")).items():
                orig_wl[os.path.basename(k).rsplit(".", 1)[0]] = v

    print("抽 seed 重出 %d 句 × %d 个 seed" % (len(by_sid), len(seeds)), flush=True)
    made = []
    for sid in sorted(by_sid):
        for sd in seeds:
            # ★ 必须绝对路径：regen_narr 调 audiocpp 时 cwd 是 acpp 目录，
            #   相对 --out 会被写到 acpp 目录下（2026-11-23 踩过一次，5 个 take 全丢）。
            out = os.path.join(ROOT, "_loop_takes", "s%d" % sd)
            if os.path.exists(os.path.join(out, sid + ".wav")):
                continue
            t0 = time.time()
            r = run([PY, "-u", "regen_narr.py", "--ids", sid, "--plan", PLAN,
                     "--out", out, "--seed", str(sd), "--log", "_loop_takes.jsonl"],
                    timeout=1800, quiet=True)
            ok = os.path.exists(os.path.join(out, sid + ".wav"))
            print("   %-9s seed=%d %s %.0fs" % (sid, sd, "OK" if ok else "FAIL", time.time() - t0),
                  flush=True)
            if ok:
                made.append(os.path.join(out, sid + ".wav").replace("\\", "/"))

    if not made:
        print("没有新 take"); return []

    wl = os.path.join(ROOT, "_loop_takes_wl.json")
    lp = os.path.join(ROOT, "_loop_takes_list.txt")
    io.open(lp, "w", encoding="utf-8").write("\n".join(made))
    run([ASR_PY, "_wl_asr.py", "--list", lp, "--out", wl, "--append"], timeout=7200)
    tw = {os.path.basename(k).rsplit(".", 1)[0]: v
          for k, v in json.load(io.open(wl, encoding="utf-8")).items()}

    rows = []
    for sid, tg in sorted(by_sid.items()):
        cur = orig_wl.get(sid)
        cur_n = len([w for w in (cur or {}).get("words", []) if clean(w["w"])])
        best = None
        detail = []
        for sd in seeds:
            key = "%s_s%d" % (sid, sd)
            rec = tw.get(key)
            if not rec:
                detail.append({"seed": sd, "z": None})
                continue
            ws = word_zs(rec)
            n_take = len([w for w in rec.get("words", []) if clean(w["w"])])
            zs = [z_of(ws, t["w"], t.get("occ", 0)) for t in tg]
            zs = [z for z in zs if z is not None]
            zv = round(max(zs), 2) if zs else None
            # 吞字护栏：词数比原 take 少 2 个以上直接淘汰
            drop = cur_n - n_take
            detail.append({"seed": sd, "z": zv, "n_words": n_take, "drop": drop,
                           "path": rec and os.path.join(ROOT, "_loop_takes", "s%d" % sd,
                                                        sid + ".wav")})
            if zv is None or drop > 1:
                continue
            if best is None or zv > best["z"]:
                best = {"z": zv, "seed": sd, "drop": drop}
        curz = max((t["z"] for t in tg), default=None)
        adopt = bool(best and curz is not None and best["z"] > curz + 0.30
                     and best["z"] >= 0.60)
        if adopt:
            src = os.path.join(ROOT, "_loop_takes", "s%d" % best["seed"], sid + ".wav")
            dst = os.path.join(ROOT, "_loop_pick", sid + ".wav")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        rows.append({"sid": sid, "words": [t["w"] for t in tg], "cur_z": curz,
                     "best_z": best and best["z"], "best_seed": best and best["seed"],
                     "adopt": adopt, "detail": detail})
        print("   %-9s 现 %+.2f → 最好 %s  %s"
              % (sid, curz if curz is not None else 0,
                 ("%+.2f(s%d)" % (best["z"], best["seed"])) if best else "无",
                 "采纳" if adopt else "保留"), flush=True)

    rep = os.path.join(ROOT, "_loop_pick_report.json")
    json.dump(rows, io.open(rep, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_ad = sum(1 for r in rows if r["adopt"])
    print("\n采纳 %d / %d 句 → %s；结果 %s" % (n_ad, len(rows), "_loop_pick/", rep), flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["asr", "test", "plan", "repick", "all"])
    ap.add_argument("--dir", default="_regen_1123")
    ap.add_argument("--wl", default="_wl_regen1123.json")
    ap.add_argument("--tag", default="after")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seeds", default="43,44,45")
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]

    if a.stage in ("asr", "all"):
        stage_asr(a.dir, a.wl)
    if a.stage in ("test", "all"):
        after = stage_test(a.dir, a.wl, a.tag)
        print(json.dumps({k: after.get(k) for k in
                          ["n_sent", "n_adv", "auc_adv", "adv_pct_mean",
                           "adv_ge_16", "adv_lt_0"]}, ensure_ascii=False), flush=True)
    if a.stage in ("plan", "all"):
        p = os.path.join(ROOT, "_stress_adv_%s.json" % a.tag)
        after = json.load(io.open(p, encoding="utf-8"))
        stage_plan(after, a.limit)
    if a.stage in ("repick", "all"):
        stage_repick(None, seeds, a.limit)


if __name__ == "__main__":
    main()
