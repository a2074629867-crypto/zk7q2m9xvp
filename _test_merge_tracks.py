# -*- coding: utf-8 -*-
"""_test_merge_tracks.py —— merge 的分轨尺度回归测试（用合成三路结果，不碰真产物）。"""
import json
import os
import shutil
import subprocess
import sys

ROOT = "G:/_setup"
PY = "G:/Python310/python.exe"
T = os.path.join(ROOT, "_ann", "_test")


def mk(name, items, tier_map):
    d = os.path.join(T, name)
    os.makedirs(d, exist_ok=True)
    for fp in os.listdir(d):
        os.remove(os.path.join(d, fp))
    for bname, batch in items.items():
        out = []
        for it in batch:
            ps = []
            for s in it["slots"]:
                ps.append({"bid": s["bid"], "tier": tier_map(it["track"], s["bid"]),
                           "why": "test"})
            out.append({"sid": it["sid"], "pause": ps, "stress": [], "rate": None})
        json.dump({"items": out}, open(os.path.join(d, bname), "w", encoding="utf-8"),
                  ensure_ascii=False)


def load(bname):
    d = json.load(open(os.path.join(ROOT, "_ann", "tasks_tier_full", bname), encoding="utf-8"))
    return {bname: d["items"]}


def main():
    shutil.rmtree(T, ignore_errors=True)
    os.makedirs(T, exist_ok=True)
    narr = load("batch_0001.json")
    dlg = load("batch_0037.json")
    counter = {"n": 0}

    # a: 三票一致 mid；b: mid/mid/short；c: short/mid/long 轮转
    mk("a", {**narr, **dlg}, lambda trk, bid: "mid")

    def tm2(trk, bid):
        counter["n"] += 1
        return ("mid", "mid", "short")[counter["n"] % 3]

    mk("b", {**narr, **dlg}, tm2)

    def tm3(trk, bid):
        counter["n"] += 1
        return ("short", "mid", "long")[counter["n"] % 3]

    mk("c", {**narr, **dlg}, tm3)

    out = os.path.join(T, "merged")
    r = subprocess.run([PY, "annotate_prosody.py", "merge",
                        "--dirs", os.path.join(T, "a"), os.path.join(T, "b"),
                        os.path.join(T, "c"), "--out-dir", out],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    print(r.stdout)
    if r.returncode:
        print("STDERR", r.stderr[-2000:])
        return 1

    rows = [json.loads(l) for l in open(os.path.join(out, "pause_ann.jsonl"), encoding="utf-8")]
    ok = True
    secs = {"narr": {0.51, 1.135, 1.695}, "dlg": {0.0, 0.20, 0.49, 0.68}}
    for x in rows:
        if x["dur"] not in secs[x["track"]]:
            print("✗ 尺度越轨", x)
            ok = False
        if x["track"] == "narr" and x["mark"] not in {"inner", "bound", "clause"}:
            print("✗ 旁白 kind 越轨", x)
            ok = False
        if x["track"] == "dlg" and x["mark"] not in {"drop", "tight", "clause", "beat"}:
            print("✗ 对白 kind 越轨", x)
            ok = False
    agree = json.load(open(os.path.join(out, "agreement.json"), encoding="utf-8"))["agreement"]
    print("agreement", agree["pause"])
    if not rows:
        print("✗ 没有输出")
        ok = False
    print("PASS" if ok else "FAIL", "rows=%d" % len(rows))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
