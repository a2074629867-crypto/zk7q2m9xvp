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
import ch123_rebuild as _RB              # noqa: E402

_BL = json.load(io.open(BASE, encoding="utf-8"))
A, B, SD = _BL["A"], _BL["B"], _BL["SD"]

# 整句拖长不算重音（STRESS_PLAYBOOK §8.4 FULL_GAIN_MAX 的本意）。
# 实测：换 seed 后句子变长的，增量里 76%~81% 是**多插的静音**，不是词被读重。
# ⇒ 静音增长超过这个秒数就判「拖慢冒充重音」，不采纳。
SIL_GROWTH_MAX = 0.50


def _dur_sil(path):
    """返回 (总时长, 内部静音合计)。split_at_silence 与 trim 用的是同一把尺子。"""
    try:
        import soundfile as sf
        y, sr = sf.read(path, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        segs = _RB.split_at_silence(y, sr, min_gap=0.10)
        sil = sum(max(0.0, segs[i + 1][0] - segs[i][1]) for i in range(len(segs) - 1))
        return len(y) / float(sr), sil
    except Exception:  # noqa: BLE001
        return None, None


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
def word_zs(rec, wav=None, voiced=True):
    """词级 rel_z。voiced=True 时逐词剪掉首尾静音（ASR span 含停顿，见 _speedlib.word_durs）。"""
    import _speedlib as _SL
    import soundfile as _sf
    durs = None
    if voiced and wav:
        try:
            _y, _sr = _sf.read(wav, dtype="float32")
            if _y.ndim > 1:
                _y = _y.mean(1)
            _durs = _SL.word_durs(_y, _sr, rec.get("words") or [])
            it = iter(_durs)
            durs = [next(it) for _ in (rec.get("words") or [])]
        except Exception:  # noqa: BLE001
            durs = None
    ws = []
    for i, w in enumerate(rec.get("words") or []):
        d = clean(w["w"])
        if not d:
            continue
        ns = nsyl(w["w"])
        if ns <= 0:
            continue
        dur = (durs[i] if durs else max(1e-3, float(w["end"]) - float(w["start"])))
        ws.append(dict(w=d, ns=ns, dur=max(1e-3, dur), sps=max(1e-3, dur) / ns))
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
def stage_repick(targets, seeds, limit, pickonly=False):
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
            if pickonly:
                continue
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

    if not made and not pickonly:
        print("没有新 take"); return []

    # ★ 2026-11-24 修：take 文件名在三个 seed 目录里完全相同（c1_0011.wav），
    #   原先按 basename 压键会把 seed 丢掉 ⇒ 后面用 "sid_s43" 查永远查不到，
    #   表现为「最好 无 / 采纳 0」。键必须带目录名：s43/c1_0011。
    wl = os.path.join(ROOT, "_loop_takes_wl.json")
    lp = os.path.join(ROOT, "_loop_takes_list.txt")
    all_takes = []
    for sd in seeds:
        d = os.path.join(ROOT, "_loop_takes", "s%d" % sd)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".wav") and not f.startswith("_raw_"):
                all_takes.append(os.path.join(d, f).replace("\\", "/"))
    io.open(lp, "w", encoding="utf-8").write("\n".join(all_takes))
    print("ASR 覆盖 %d 个 take（--append，已有自动跳过）" % len(all_takes), flush=True)
    run([ASR_PY, "_wl_asr.py", "--list", lp, "--out", wl, "--append"], timeout=7200)
    tw = {}
    for k, v in json.load(io.open(wl, encoding="utf-8")).items():
        kk = k.replace("\\", "/")
        tw["%s/%s" % (os.path.basename(os.path.dirname(kk)),
                      os.path.basename(kk).rsplit(".", 1)[0])] = v

    rows = []
    for sid, tg in sorted(by_sid.items()):
        cur = orig_wl.get(sid)
        cur_n = len([w for w in (cur or {}).get("words", []) if clean(w["w"])])
        cur_ws = word_zs(cur, os.path.join(ROOT, "_regen_1123", sid + ".wav")) if cur else []
        best = None
        detail = []
        for sd in seeds:
            key = "s%d/%s" % (sd, sid)
            rec = tw.get(key)
            if not rec:
                detail.append({"seed": sd, "z": None})
                continue
            ws = word_zs(rec, os.path.join(ROOT, "_loop_takes", "s%d" % sd, sid + ".wav"))
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
        # 现状的 z 也用同一把尺子（逐词剪静音），否则新旧不同口径
        _cz = [z_of(cur_ws, t["w"], t.get("occ", 0)) for t in tg]
        _cz = [z for z in _cz if z is not None]
        curz = round(max(_cz), 2) if _cz else max((t["z"] for t in tg), default=None)
        adopt = bool(best and curz is not None and best["z"] > curz + 0.30
                     and best["z"] >= 0.60)
        # ★ 静音闸：换 seed 变长、且多出来的部分主要是静音 ⇒ 是拖慢，不是重音
        sil_note = ""
        if adopt:
            src = os.path.join(ROOT, "_loop_takes", "s%d" % best["seed"], sid + ".wav")
            c_dur, c_sil = _dur_sil(os.path.join(ROOT, "_regen_1123", sid + ".wav"))
            n_dur, n_sil = _dur_sil(src)
            if None not in (c_sil, n_sil):
                grow = n_sil - c_sil
                if grow > SIL_GROWTH_MAX:
                    adopt = False
                    sil_note = "  静音 +%.2fs(占时长增量 %.0f%%) ⇒ 拖慢不算重音" % (
                        grow, 100 * grow / max(1e-6, (n_dur - c_dur)))
        if adopt:
            src = os.path.join(ROOT, "_loop_takes", "s%d" % best["seed"], sid + ".wav")
            dst = os.path.join(ROOT, "_loop_pick", sid + ".wav")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        rows.append({"sid": sid, "words": [t["w"] for t in tg], "cur_z": curz,
                     "best_z": best and best["z"], "best_seed": best and best["seed"],
                     "adopt": adopt, "sil_note": sil_note, "detail": detail})
        print("   %-9s 现 %+.2f → 最好 %s  %s%s"
              % (sid, curz if curz is not None else 0,
                 ("%+.2f(s%d)" % (best["z"], best["seed"])) if best else "无",
                 "采纳" if adopt else "保留", sil_note), flush=True)

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
    ap.add_argument("--pick-only", action="store_true",
                    help="跳过生成，只对磁盘上已有的 take 做 ASR + 择优（修键后重评用）")
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
        stage_repick(None, seeds, a.limit, pickonly=a.pick_only)


if __name__ == "__main__":
    main()
