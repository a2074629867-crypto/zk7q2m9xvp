# -*- coding: utf-8 -*-
"""_frag_truth.py —— 判「碎点」里夹的那一截到底是不是完整的一个词。

`_fragscan` 只按「两洞之间有声 <0.35s」计数，会把「停顿—短词—停顿」也算进去。
真正的「碎」是夹层里**没有完整词**（词被切掉一半）。用交付版自己的词时间戳判就行。

用法：G:/Python310/python.exe -u _frag_truth.py [--dir _regen_final] [--wl _wl_final2.json]
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="_regen_final")
    ap.add_argument("--wl", default="_wl_final2.json")
    a = ap.parse_args()

    D = json.load(open(os.path.join(HERE, "_fragscan.json"), encoding="utf-8"))
    rows = D.get(a.dir) or []
    W = {}
    for k, v in json.load(open(os.path.join(HERE, a.wl), encoding="utf-8")).items():
        sid = k.replace("\\", "/").rsplit("/", 1)[-1]
        if sid.endswith(".wav"):
            sid = sid[:-4]
        W[sid] = v["words"]

    whole, half = [], []
    for r in rows:
        if r["cls"] not in ("A", "B"):
            continue
        ws = W.get(r["sid"])
        if not ws:
            continue
        g0 = r["t"] + r["d1"]
        g1 = g0 + r["gap"]
        inside = [w for w in ws if w["start"] >= g0 - 0.04 and w["end"] <= g1 + 0.04]
        rec = dict(r)
        rec["words"] = [w["w"] for w in inside]
        (whole if inside else half).append(rec)

    print("%s（%s）：A+B 共 %d 处，夹层含完整词的 %d 处，不含（=半个词/被切）%d 处"
          % (a.dir, a.wl, len(whole) + len(half), len(whole), len(half)))
    print()
    print("不含完整词（真碎）：")
    for r in sorted(half, key=lambda x: -x["peak"]):
        print("  %-9s @%6.2f 洞%.2f+%.2f+%.2f 夹层%.2f 峰%.0f dB"
              % (r["sid"], r["t"], r["d1"], r["gap"], r["d2"], r["gap"], r["peak"]))
    print()
    print("含完整词（停顿—词—停顿，正常）：")
    for r in sorted(whole, key=lambda x: -x["peak"])[:12]:
        print("  %-9s @%6.2f 夹层%.2f 峰%.0f dB  词=%s"
              % (r["sid"], r["t"], r["gap"], r["peak"], r["words"]))
    json.dump(dict(half=[r["sid"] for r in half], whole=[r["sid"] for r in whole]),
              open(os.path.join(HERE, "_frag_truth.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
