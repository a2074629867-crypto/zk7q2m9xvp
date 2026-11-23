# -*- coding: utf-8 -*-
"""物理闸驱动的重出：只针对 FIX 的那几条，换 seed 重生成，取第一条过闸的。

为什么单独一条路：
  FIX 的原因是「结尾硬切 / 电平跑偏 / 语速越界」，这些不是重音问题，
  不该混进 `_loop_1123.py` 的重音回环（那边按 rel_z 择优，会选出更差物理指标的 take）。
  这里按**物理闸**择优，指标与闸完全同源，选出来的必然能过。

护栏：
  - 原 take 先备份到 `_gate_fix/old/`，不直接丢
  - 新 take 必须「为什么」条目数 ≤ 原 take，才允许替换
  - 只在显式给出 --apply 时才写回 `_regen_1123/`

用法：
  G:/Python310/python.exe -u _gate_fix.py --seeds 51,52
  G:/Python310/python.exe -u _gate_fix.py --seeds 51,52 --apply
"""
import argparse
import glob
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = r"G:/_setup"
PY = r"G:/Python310/python.exe"
PLAN = os.path.join(ROOT, "_castle_en_ch123_plan_v2.jsonl")
GATE = os.path.join(ROOT, "narr_gate_phys.py")
MAIN_DIR = os.path.join(ROOT, "_regen_1123")
FIX_DIR = os.path.join(ROOT, "_gate_fix")


def run(cmd, timeout=7200, quiet=False):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if not quiet:
        for ln in ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-3:]:
            print("    " + ln, flush=True)
    return r


def gate(d, out):
    run([PY, "-u", GATE, "--dir", d.replace("\\", "/"), "--out", out, "--abs-voiced"],
        timeout=3600, quiet=True)
    return {x["id"]: x for x in json.load(io.open(out, encoding="utf-8"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="51,52")
    ap.add_argument("--src", default=os.path.join(ROOT, "_narr_phys_regen1123.json"))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]

    cur = {x["id"]: x for x in json.load(io.open(a.src, encoding="utf-8"))}
    fix = [k for k, v in cur.items() if v["verdict"] == "FIX"]
    if not fix:
        print("没有 FIX，不用重出"); return
    print("FIX %d 条：%s" % (len(fix), ", ".join(fix)), flush=True)

    # 1) 逐 seed 重出
    for sd in seeds:
        out = os.path.join(FIX_DIR, "s%d" % sd)
        todo = [i for i in fix if not os.path.exists(os.path.join(out, i + ".wav"))]
        if not todo:
            print("seed %d 已有全部 take" % sd, flush=True); continue
        print("seed %d 重出 %d 条" % (sd, len(todo)), flush=True)
        run([PY, "-u", "regen_narr.py", "--ids", ",".join(todo), "--plan", PLAN,
             "--out", out.replace("\\", "/"), "--seed", str(sd),
             "--log", "_gate_fix_takes.jsonl"], timeout=7200)

    # 2) 逐个 seed 过闸
    takes = {}
    for sd in seeds:
        d = os.path.join(FIX_DIR, "s%d" % sd)
        if not glob.glob(os.path.join(d, "*.wav")):
            continue
        g = gate(d, os.path.join(ROOT, "_gate_fix_s%d.json" % sd))
        takes[sd] = g
        print("  seed %d: %s" % (sd, {k: v["verdict"] for k, v in g.items()}), flush=True)

    # 3) 择优：先比严重度（PASS<WATCH<FIX），再比「为什么」条目数
    SEV = {"PASS": 0, "WATCH": 1, "FIX": 2}
    os.makedirs(os.path.join(FIX_DIR, "old"), exist_ok=True)
    rows = []
    for sid in fix:
        old = cur[sid]
        best = None
        for sd in seeds:
            g = (takes.get(sd) or {}).get(sid)
            if not g:
                continue
            key = (SEV.get(g["verdict"], 3), len(g["why"]))
            if best is None or key < best["key"]:
                best = dict(seed=sd, key=key, nwhy=len(g["why"]),
                            verdict=g["verdict"], why=g["why"],
                            wpm=g["wpm"], tail=g["tail"], lvl=g["lvl"])
        adopt = bool(best and best["key"] < (SEV.get(old["verdict"], 3), len(old["why"])))
        rows.append(dict(id=sid, old=dict(verdict=old["verdict"], why=old["why"],
                                          wpm=old["wpm"], tail=old["tail"], lvl=old["lvl"]),
                         best=best, adopt=adopt))
        print("  %-9s 原[%s %s] → 新[%s %s] %s"
              % (sid, old["verdict"], ";".join(old["why"]) or "-",
                 best and best["verdict"], best and (";".join(best["why"]) or "-"),
                 "采纳" if adopt else "保留"), flush=True)

        if adopt and a.apply:
            src = os.path.join(FIX_DIR, "s%d" % best["seed"], sid + ".wav")
            bak = os.path.join(FIX_DIR, "old", sid + ".wav")
            if not os.path.exists(bak):
                shutil.copy2(os.path.join(MAIN_DIR, sid + ".wav"), bak)
            shutil.copy2(src, os.path.join(MAIN_DIR, sid + ".wav"))

    rep = os.path.join(ROOT, "_gate_fix_report.json")
    json.dump(rows, io.open(rep, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(1 for r in rows if r["adopt"])
    print("\n可采纳 %d / %d%s → %s"
          % (n, len(rows), "（已写回）" if a.apply else "（未写回，加 --apply）", rep),
          flush=True)


if __name__ == "__main__":
    main()
