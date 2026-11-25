# -*- coding: utf-8 -*-
import json, os
ROOT = r"G:\_setup"
b = json.load(open(os.path.join(ROOT, "_narr_blocks.json"), encoding="utf-8"))
want = []
for blk in b:
    want.extend(blk["ids"])
print("blocks 里的 id 总数", len(want), "去重", len(set(want)))

for tag, jf, d, wlf in (("old", "_accent_feat_old.jsonl", "_audio_ch123/out", "_wl_words.json"),
                        ("new", "_accent_feat_new.jsonl", "_regen_final", "_wl_regen1123.json")):
    got = set()
    for ln in open(os.path.join(ROOT, jf), encoding="utf-8"):
        try:
            got.add(json.loads(ln)["id"])
        except Exception:
            pass
    miss = [x for x in want if x not in got]
    nowav = [x for x in miss if not os.path.exists(os.path.join(ROOT, d, x + ".wav"))]
    nowl = [x for x in miss if x not in json.load(open(os.path.join(ROOT, wlf), encoding="utf-8")).__str__()]
    print("== %s  got=%d  missing=%d  其中{wav不存在}=%d" % (tag, len(got), len(miss), len(nowav)))
    print("   missing 前 12:", miss[:12])
    if nowav:
        print("   缺 wav 前 12:", nowav[:12])
