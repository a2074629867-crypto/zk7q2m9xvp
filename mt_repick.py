# -*- coding: utf-8 -*-
"""按 60 条人工标注标定出的规则重选候选。

规则（来自 mt_label_analysis.py 的实测结论）：
  1. 硬门槛（保命项，不能破）：
       tail_ok（末词必须出现）/ ASR 相似度 >= 0.78 /
       F0 <= 102Hz（dur>=2.5s）/ 拉伸后语速 <= 目标*1.30 / 重心 <= 4600
     MOS 门槛从 2.5 降到 1.6 —— 标注证明 MOS 对偏好无预测力
     （用户所选里 MOS 最高占 40%、最低占 47%，等于随机），
     它只能挡真正的气声垃圾（`he said,` MOS 1.03 那类），不该用来排序。
  2. 排序：**选最暗（频谱重心最低）**，同暗取语速更快的。
     标注实测命中 42/58 = 72%；原打分器 27/58 = 47%；重心最高只有 19%。
  3. 人工标注（_mt_human_labels.json）优先，不参与自动规则。
     4 条问句的人工判定与「最暗」方向相反（问句要起伏），必须保留。
"""
import json
import os
import shutil
import sys

ROOT = "G:/_setup"
CHS = ["ch1", "ch2", "ch3"]
PICK = os.path.join(ROOT, "_mt_pick")
TARGET = 190.0
MOS_FLOOR = 1.6
CEN_CEIL = 4600.0
F0_CEIL = 102.0
RATIO_MIN = 0.78
SPEED_CEIL = TARGET * 1.30


def load_human():
    p = os.path.join(ROOT, "_mt_human_labels.json")
    if not os.path.exists(p):
        return {}
    d = json.load(open(p, encoding="utf-8"))
    return {k: str(v["pick"]) for k, v in d.items()}


def passes(c):
    if not c["tail_ok"]:
        return False, "末词缺"
    if c["ratio"] < RATIO_MIN:
        return False, "ASR"
    if c["f0"] > F0_CEIL and c["dur"] >= 2.5:
        return False, "F0"
    if c["final_wpm"] > SPEED_CEIL:
        return False, "太快"
    if c["centroid"] > CEN_CEIL:
        return False, "过亮"
    if c.get("mos") is not None and c["mos"] < MOS_FLOOR:
        return False, "气声"
    return True, ""


def main():
    dry = "--apply" not in sys.argv
    human = load_human()
    print("人工标注 %d 条：%s" % (len(human), human))
    print("模式：%s" % ("试运行" if dry else "写入"))
    print()

    stat = dict(total=0, changed=0, same=0, single=0, nouse=0,
                human=0, by_reason={})
    changes = []
    nouse_ids = []

    for ch in CHS:
        sp = os.path.join(ROOT, "_mt_score_%s.json" % ch)
        rows = json.load(open(sp, encoding="utf-8"))
        for x in rows:
            uid = x["id"]
            ex = [c for c in x["cands"]
                  if os.path.exists(os.path.join(ROOT, "_mt_raw_s%s" % c["seed"], uid + ".wav"))]
            if not ex:
                continue
            stat["total"] += 1

            # 人工标注优先
            if uid in human:
                new = [c for c in ex if str(c["seed"]) == human[uid]]
                if new:
                    stat["human"] += 1
                    if str(x["pick"]) != human[uid]:
                        changes.append((uid, ch, str(x["pick"]), human[uid], "人工", 0.0))
                        x["pick"] = int(human[uid]) if human[uid].isdigit() else human[uid]
                        x["flag"] = "USER-PICK"
                        if not dry:
                            shutil.copy2(os.path.join(ROOT, "_mt_raw_s%s" % human[uid], uid + ".wav"),
                                         os.path.join(PICK, uid + ".wav"))
                    continue

            ok = [c for c in ex if passes(c)[0]]
            if not ok:
                stat["nouse"] += 1
                nouse_ids.append(uid)
                x["flag"] = "NEED-REGEN"
                continue
            if len(ok) == 1:
                stat["single"] += 1
            best = min(ok, key=lambda z: (z["centroid"], -z["final_wpm"]))
            cur = [c for c in ex if str(c["seed"]) == str(x["pick"])]
            cur = cur[0] if cur else None

            if cur is not None and str(cur["seed"]) == str(best["seed"]):
                stat["same"] += 1
                x["flag"] = "OK"
                continue

            stat["changed"] += 1
            delta = best["centroid"] - (cur["centroid"] if cur else 0)
            changes.append((uid, ch, str(cur["seed"]) if cur else "-", str(best["seed"]),
                            "最暗", delta))
            x["pick"] = int(best["seed"]) if str(best["seed"]).isdigit() else best["seed"]
            x["flag"] = "LABEL-RULE"
            if not dry:
                shutil.copy2(os.path.join(ROOT, "_mt_raw_s%s" % best["seed"], uid + ".wav"),
                             os.path.join(PICK, uid + ".wav"))

        if not dry:
            json.dump(rows, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("单元 %d：不变 %d / 换选 %d / 人工 %d / 单候选 %d / 无可用 %d"
          % (stat["total"], stat["same"], stat["changed"], stat["human"],
             stat["single"], stat["nouse"]))
    print()
    print("换选明细（前 20 条）：")
    for c in changes[:20]:
        print("  %-7s %s  s%-6s → s%-6s  %-6s 重心 %+.0f" % (c[0], c[1], c[2], c[3], c[4], c[5]))
    print()
    if nouse_ids:
        print("无可用候选（需重生成）%d 条：" % len(nouse_ids))
        print("  " + ",".join(nouse_ids))
    if not dry:
        json.dump([dict(id=c[0], ch=c[1], old=c[2], new=c[3], why=c[4], dcen=c[5])
                   for c in changes],
                  open(os.path.join(ROOT, "_mt_repick_log.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print()
        print("已写入 _mt_pick/ 与 _mt_score_*.json；明细 _mt_repick_log.json")


if __name__ == "__main__":
    main()
