# -*- coding: utf-8 -*-
"""v41 -> v46 的进出对照：谁进了 PASS、谁退了，退的原因是什么。"""
import collections
import json
import os

S = "G:/_setup"


def load(p):
    return {os.path.basename(x["wav"])[:-4]: x for x in json.load(open(os.path.join(S, p), encoding="utf-8"))}


def main():
    a = load("_gate_dlg_v41.json")
    b = load("_gate_dlg_v46.json")
    up = [k for k in b if a.get(k, {}).get("verdict") != "PASS" and b[k]["verdict"] == "PASS"]
    dn = [k for k in b if a.get(k, {}).get("verdict") == "PASS" and b[k]["verdict"] != "PASS"]
    print("v41 PASS %d -> v46 PASS %d" % (
        sum(1 for x in a.values() if x["verdict"] == "PASS"),
        sum(1 for x in b.values() if x["verdict"] == "PASS")))
    print("进 PASS %d: %s" % (len(up), up))
    print("退 PASS %d:" % len(dn))
    for k in dn:
        e = b[k].get("emo_res") or {}
        print("  %-9s %-7s gates=%s emo=%s/%s reasons=%s" % (
            k, b[k]["verdict"], {kk: vv for kk, vv in b[k]["gates"].items() if vv not in ("PASS",)},
            e.get("value"), e.get("tier"), [r["code"] for r in (b[k].get("reasons") or [])]))
    fin = json.load(open(os.path.join(S, "_dlg_final.json"), encoding="utf-8"))
    cnt = collections.Counter(x.get("bucket") or x.get("cls") for x in fin)
    print("final", dict(cnt), "n", len(fin))
    print("C:", [x["id"] for x in fin if (x.get("bucket") or x.get("cls")) == "C"])


if __name__ == "__main__":
    main()
