# -*- coding: utf-8 -*-
"""_spk_gate.py —— 声纹闸门：重生 take 是否还是同一个人。

背景：回环里所有判据都在测「重读够不够」，**没有一条测音色**。
2026-10-26 补测 15 对原版/重生，最低到 **0.416**（N0347），
也就是"F0 抬了 6 个半音、听起来更重了，但人换了"。
用户红线：声纹 ≥0.65 才算过；0.65 是硬线，0.55~0.65 只能带警告采纳。

用法：
    G:/Python310/python.exe _spk_gate.py --manifest m.json --out s.json
    manifest = [{"uid": "N0419", "a": "原版.wav", "b": "重生.wav"}, ...]

输出：[{"uid", "spk", "verdict"}]，verdict ∈ {OK, WARN, VOID, ERR}
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPK_DIR = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab"
sys.path.insert(0, SPK_DIR)

OK = 0.65
WARN = 0.55


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default="_spk_gate.json")
    a = ap.parse_args()

    import spk_embed as S

    items = json.load(open(a.manifest, encoding="utf-8"))
    items = items if isinstance(items, list) else items.get("items", [])
    rows = []
    for it in items:
        uid = str(it["uid"])
        try:
            c = float(S.cos(S.embed(it["a"]), S.embed(it["b"])))
            v = "OK" if c >= OK else ("WARN" if c >= WARN else "VOID")
        except Exception as e:
            c, v = None, "ERR:" + str(e)[:60]
        rows.append(dict(uid=uid, spk=None if c is None else round(c, 3), verdict=v))
        print("%-8s %s %s" % (uid, "-" if c is None else "%.3f" % c, v))
    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    nv = sum(1 for r in rows if str(r["verdict"]).startswith("VOID"))
    nw = sum(1 for r in rows if r["verdict"] == "WARN")
    print("共 %d 对：OK %d / WARN %d / VOID %d" % (len(rows), len(rows) - nv - nw, nw, nv))


if __name__ == "__main__":
    main()
