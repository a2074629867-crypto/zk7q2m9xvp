# -*- coding: utf-8 -*-
"""_build_lib2.py —— 补 Joseph / Helena 声纹模板，产出 v2 库（不改原库）

背景：`_emo_refs.json` 只有 Charles(9) + Thomas(16) = 25 条，而台账里有
Joseph 53 条、Helena 8 条 ⇒ **61/239 条对白没有模板**，角色/情绪闸对它们等于空转
（`_selftest.py` T5a 就是这么判 FAIL 的）。

素材：`refs_cast/Joseph_<emo>_c<NNN>.wav`（38 条）、`Helena_<emo>_c<NNN>.wav`（15 条），
都是单句切片，正好是建模板要的形态（不是拼接参考）。

分域：Joseph/Helena 来自 Hope Gap 片，背景集必须用 `out_sv/bg_hopegap.json`（200 条），
不能用城堡片的 `cues_znorm2.json` —— `chain_check.py` 里已写明不分域的后果：
法语片台词被吸走，PASS 38→17、准确率 86.4%→47.5%。

用法：
  G:/Python310/python.exe _build_lib2.py
  G:/Python310/python.exe _build_lib2.py --out _emo_refs_v2.json
"""
import argparse
import json
import os
import re

ROOT = "G:/_setup"
REFS = os.path.join(ROOT, "refs_cast")


def scan(role):
    out = {}
    for fn in sorted(os.listdir(REFS)):
        if not fn.startswith(role + "_"):
            continue
        m = re.match(r"%s_([a-z]+)_c(\d+)\.wav$" % role, fn)
        if not m:
            continue        # Joseph_clean_mid_02793.wav 这种没情绪标记的不要
        emo = m.group(1)
        out.setdefault(emo, []).append({
            "path": os.path.join(REFS, fn),
            "name": "c%s" % m.group(2),
            "z": 0.0,
            "text": "",
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=os.path.join(ROOT, "_emo_refs.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "_emo_refs_v2.json"))
    ap.add_argument("--max-per-emo", type=int, default=4,
                    help="每档最多取几条（太多会把质心拉向个别录音条件）")
    a = ap.parse_args()

    lib = json.load(open(a.lib, encoding="utf-8"))
    for role in ("Joseph", "Helena"):
        got = scan(role)
        if not got:
            print("⚠ %s 无素材" % role)
            continue
        lib[role] = {}
        for emo, items in got.items():
            sel = items[:a.max_per_emo]
            lib[role][emo] = sel
            print("%-8s %-9s %d 条（共 %d 可用）" % (role, emo, len(sel), len(items)))

    json.dump(lib, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tot = sum(len(v) for r in lib.values() for v in r.values())
    print("\n角色 %s / 模板 %d 条 → %s" % (sorted(lib.keys()), tot, a.out))

    # 背景集映射（分域，必须一起用）
    bm = {"Charles": "G:/_setup/out_sv/bg_castle.json",
          "Thomas": "G:/_setup/out_sv/bg_castle.json",
          "Joseph": "G:/_setup/out_sv/bg_hopegap.json",
          "Helena": "G:/_setup/out_sv/bg_hopegap.json"}
    p = os.path.join(ROOT, "_bg_map_v2.json")
    json.dump(bm, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("bg-map → %s" % p)


if __name__ == "__main__":
    main()
