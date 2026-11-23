# -*- coding: utf-8 -*-
"""抽查剪辑后覆盖率骤降的条目：原文 / 剪前 w2v / 剪后 w2v / 剪辑报告。"""
import io
import json
import sys

sys.path.insert(0, "G:/_setup")
import _calm_gate as CG

IDS = ["c2_0277", "c3_0660", "c2_0303", "c1_0164", "c2_0212", "c1_0028", "c2_0282"]

pre = {r["id"]: r for r in json.load(io.open("_align_camp9.json", encoding="utf-8"))}
post = {r["id"]: r for r in json.load(io.open("_align_final9.json", encoding="utf-8"))}
rep = json.load(io.open("_post_final9.json", encoding="utf-8"))
plan = CG.load_plan()

for i in IDS:
    p = plan.get(i, {})
    print("== %s  %s" % (i, (p.get("text") or "")[:70]))
    pr = next((v for k, v in pre.items() if k.split("__")[0] == i), None)
    print("   final9 : cov=%.2f  %s" % ((pr or {}).get("w2v_cov") or 0, (pr or {}).get("w2v_text")))
    print("   post   : cov=%.2f  %s" % ((post.get(i) or {}).get("w2v_cov") or 0,
                                        (post.get(i) or {}).get("w2v_text")))
    r = rep.get(i)
    if r:
        print("   fix    : %.2f->%.2f  填%d段  剪%s" % (r.get("dur", 0), r.get("out_dur", 0),
                                                    r.get("filled", 0), r.get("cuts")))
