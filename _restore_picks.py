# -*- coding: utf-8 -*-
"""剪静音口径下的收尾：回滚 2 条 + 保留 4 条新采纳，然后交给 _apply_picks.py。

背景（2026-11-24）：ASR 的词 span 含该词后面的停顿（`end = 下一词 start`），
旧口径把「词 + 停顿」当词长 ⇒ 择优结果被污染。换成逐词剪静音后重评：

  c1_0143  violently  原版 +0.51 → 写回版 +0.49   ⇒ 回滚（没变好）
  c2_0504  loftily    原版 −0.55 → 写回版 +0.76   ⇒ 保留
  c3_0585  again      原版 +0.27 → 写回版 −1.67   ⇒ 回滚（明显变差）

新采纳 4 条（剪静音口径）：c1_0071 / c1_0085 / c3_0555 / c3_0688。

做法：把要回滚的原版放进 `_loop_pick/`，并在报告里标 adopt=True + restore=True，
再交给 `_apply_picks.py --apply` 统一走「写回 → ASR → 插停顿 → 重建页面」，
避免手工漏掉下游三步。

用法：G:/Python310/python.exe -u _restore_picks.py
"""
import io
import json
import os
import shutil

ROOT = r"G:/_setup"
PICK = os.path.join(ROOT, "_loop_pick")
BAK = os.path.join(ROOT, "_picks_old")
REP = os.path.join(ROOT, "_loop_pick_report.json")

RESTORE = ["c1_0143", "c3_0585"]
KEEP = ["c2_0504"]


def main():
    rep = json.load(io.open(REP, encoding="utf-8"))
    have = {r["sid"] for r in rep}

    for sid in RESTORE:
        src = os.path.join(BAK, sid + ".wav")
        if not os.path.exists(src):
            print("!! 备份里没有 %s，跳过" % sid)
            continue
        shutil.copy2(src, os.path.join(PICK, sid + ".wav"))
        if sid not in have:
            rep.append({"sid": sid, "words": [], "cur_z": None, "best_z": None,
                        "best_seed": None, "adopt": True, "restore": True,
                        "sil_note": "剪静音口径复评后回滚：写回版不如原版"})
        else:
            for r in rep:
                if r["sid"] == sid:
                    r["adopt"] = True
                    r["restore"] = True
                    r["sil_note"] = "剪静音口径复评后回滚：写回版不如原版"
        print("回滚 %s" % sid)

    # 保留项（已写回且复评通过）不重复处理，只做标记
    for r in rep:
        if r["sid"] in KEEP:
            r["keep_verified"] = True

    json.dump(rep, io.open(REP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(1 for r in rep if r.get("adopt"))
    print("报告更新：adopt=%d（含回滚 %d）" % (n, len(RESTORE)))
    print("下一步：G:/Python310/python.exe -u _apply_picks.py --apply")


if __name__ == "__main__":
    main()
