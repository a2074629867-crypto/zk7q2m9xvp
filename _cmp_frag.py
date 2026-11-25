# -*- coding: utf-8 -*-
"""_cmp_frag.py —— 逐句对比两个目录的 A 类碎点（同一批 id）。

用法：G:/Python310/python.exe -u _cmp_frag.py _pause_fix2 _pause_fix3
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _fragscan import scan_one  # noqa: E402


def A_of(d):
    out = {}
    for p in sorted(glob.glob(os.path.join(HERE, d, "*.wav"))):
        sid = os.path.basename(p)[:-4]
        for f in scan_one(p):
            if f["peak"] >= -25:
                out.setdefault(sid, []).append(f)
    return out


def main():
    ds = sys.argv[1:]
    res = {d: A_of(d) for d in ds}
    sids = sorted(set().union(*[set(r) for r in res.values()]))
    print("%-10s %s" % ("sid", "  ".join("%-28s" % d for d in ds)))
    for sid in sids:
        cells = []
        for d in ds:
            rs = res[d].get(sid, [])
            cells.append("%-28s" % (", ".join("@%.2f(峰%.0f)" % (r["t"], r["peak"]) for r in rs) or "—"))
        print("%-10s %s" % (sid, "  ".join(cells)))
    print()
    for d in ds:
        print("%-28s A %d 处 / %d 句" % (d, sum(len(v) for v in res[d].values()), len(res[d])))


if __name__ == "__main__":
    main()
