# -*- coding: utf-8 -*-
"""把 3.4（词内 F0 覆盖率）用成排序器 —— §12.4 的正确用法。

不判好坏，只回答一个问题：**哪些句子里有最多「没唱出来」的词，该先拿去听？**

输出 `_f0cover_rank.csv`：
  rank, id, cover_old, cover_new, delta, n_suspect_old, suspect_words_old

排序依据：cover_old 升序（旧版最糊的排最前）。旧版没数据时用 cover_new。
"""
import csv
import io
import json
import os

ROOT = "G:/_setup"
OUT = os.path.join(ROOT, "_f0cover_rank.csv")


def main():
    o = json.load(io.open(os.path.join(ROOT, "_f0cover_old.json"), encoding="utf-8"))
    n = json.load(io.open(os.path.join(ROOT, "_f0cover_new.json"), encoding="utf-8"))

    rows = []
    for sid in sorted(set(o) | set(n)):
        a, b = o.get(sid) or {}, n.get(sid) or {}
        co, cn = a.get("med"), b.get("med")
        key = co if co is not None else (cn if cn is not None else 9.9)
        sus = a.get("sus") or []
        rows.append(dict(
            id=sid,
            cover_old="" if co is None else "%.2f" % co,
            cover_new="" if cn is None else "%.2f" % cn,
            delta=("" if (co is None or cn is None) else "%+.2f" % (cn - co)),
            n_suspect_old=len(sus),
            suspect_words_old=" ".join(
                "%s(%.2f)" % (s["w"].strip(".,;:!?"), s["cover"]) for s in sus[:12]),
            _key=key,
        ))

    rows.sort(key=lambda r: r["_key"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    cols = ["rank", "id", "cover_old", "cover_new", "delta",
            "n_suspect_old", "suspect_words_old"]
    with io.open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # 摘要
    n_very = sum(1 for r in rows if r["cover_old"] and float(r["cover_old"]) < 0.10)
    n_low = sum(1 for r in rows if r["cover_old"] and float(r["cover_old"]) < 0.20)
    print("共 %d 句 → %s" % (len(rows), OUT))
    print("  旧版 cover<0.10（几乎整句无基频）：%d 句" % n_very)
    print("  旧版 cover<0.20（整句糊）        ：%d 句" % n_low)
    print()
    print("=== 前 20 名（该先听这些）===")
    print("%-4s %-9s %6s %6s %6s  %s"
          % ("#", "id", "old", "new", "Δ", "旧版没唱出来的词"))
    for r in rows[:20]:
        print("%-4d %-9s %6s %6s %6s  %s"
              % (r["rank"], r["id"], r["cover_old"], r["cover_new"],
                 r["delta"], r["suspect_words_old"]))


if __name__ == "__main__":
    main()
