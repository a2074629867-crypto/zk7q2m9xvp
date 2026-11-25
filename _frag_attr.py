# -*- coding: utf-8 -*-
"""_frag_attr.py —— 把 `_pause_fix2` 剩下的碎点归因：干声自带 vs 注入新引入。

A 档（夹层 ≥−25 dBFS）才是用户能听出来的「碎」。
干声自带 ⇒ 模型坏 take，只能换 seed；注入新引入 ⇒ 切点/校验还能再修。

用法：G:/Python310/python.exe -u _frag_attr.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    D = json.load(open(os.path.join(HERE, "_fragscan.json"), encoding="utf-8"))
    dry = {r["sid"]: r for r in D["_regen_1123_norm"]}
    fix = D["_pause_fix2"]
    old = D["_regen_final"]

    dryA = {}
    for r in D["_regen_1123_norm"]:
        if r["cls"] == "A":
            dryA.setdefault(r["sid"], []).append(r)

    print("干声自带 A 类：%d 处 / %d 句" % (sum(len(v) for v in dryA.values()), len(dryA)))
    print("修复版剩余 A 类：%d 处 / %d 句"
          % (sum(1 for r in fix if r["cls"] == "A"), len(set(r["sid"] for r in fix if r["cls"] == "A"))))
    print("交付版 A 类：%d 处 / %d 句"
          % (sum(1 for r in old if r["cls"] == "A"), len(set(r["sid"] for r in old if r["cls"] == "A"))))
    print()

    newA = [r for r in fix if r["cls"] == "A"]
    src, intro = [], []
    for r in newA:
        # 同一句、时间相差 <0.5s 的干声 A 处 ⇒ 归为干声自带
        hit = [x for x in dryA.get(r["sid"], []) if abs(x["t"] - r["t"]) < 0.5]
        (src if hit else intro).append(r)
    print("修复版 A 类归因：")
    print("  干声自带（换 seed 才能修）：%d 处 / %d 句"
          % (len(src), len(set(r["sid"] for r in src))))
    print("  注入新引入（还能再修）  ：%d 处 / %d 句"
          % (len(intro), len(set(r["sid"] for r in intro))))
    for r in src:
        print("   [源] %-9s @%6.2f 洞%.2f+%.2f+%.2f 峰%.0f dB"
              % (r["sid"], r["t"], r["d1"], r["gap"], r["d2"], r["peak"]))
    for r in intro:
        print("   [新] %-9s @%6.2f 洞%.2f+%.2f+%.2f 峰%.0f dB"
              % (r["sid"], r["t"], r["d1"], r["gap"], r["d2"], r["peak"]))
    json.dump(dict(src=[r["sid"] for r in src], intro=[r["sid"] for r in intro]),
              open(os.path.join(HERE, "_frag_attr.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
