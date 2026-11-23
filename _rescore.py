# -*- coding: utf-8 -*-
"""用改进后的词匹配重算各 align json 的 `w2v_cov`（不需要重跑模型）。

align json 里已经存了 `w2v_text`（wav2vec2 贪心解码结果），
所以只要换匹配器就能直接重算覆盖率，省 2 分钟×3 的推理时间。

用法：python _rescore.py _align_live.json _align_camp9.json _align_final9.json
每条会写回同名文件（原文件备份成 *.bak）。
"""
import io
import json
import os
import shutil
import sys

ROOT = "G:/_setup"
sys.path.insert(0, ROOT)
import _pick52 as PK
import _calm_gate as CG


def main():
    plan = CG.load_plan()
    for path in sys.argv[1:]:
        p = path if os.path.isabs(path) else os.path.join(ROOT, path)
        if not os.path.exists(p):
            print("缺文件", p)
            continue
        if not os.path.exists(p + ".bak"):
            shutil.copyfile(p, p + ".bak")
        rows = json.load(io.open(p, encoding="utf-8"))
        up = dn = 0
        for r in rows:
            rid = r.get("rid") or r["id"].split("__")[0]
            gold = PK.norm_words((plan.get(rid) or {}).get("text") or "")
            hyp = PK.norm_words(r.get("w2v_text") or "")
            if not gold:
                continue
            old = r.get("w2v_cov") or 0.0
            new = round(PK.coverage(gold, hyp), 3)
            r["w2v_cov"] = new
            if new > old + 1e-9:
                up += 1
            elif new < old - 1e-9:
                dn += 1
        json.dump(rows, io.open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        ok = sum(1 for r in rows if (r.get("w2v_cov") or 0) >= 0.85)
        print("%-24s %3d 条  cov≥0.85 %3d (%.0f%%)  上调 %d / 下调 %d" % (
            os.path.basename(p), len(rows), ok, 100.0 * ok / max(1, len(rows)), up, dn))


if __name__ == "__main__":
    main()
