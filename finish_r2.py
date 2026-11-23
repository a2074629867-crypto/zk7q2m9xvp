# -*- coding: utf-8 -*-
"""finish_r2.py —— 第二轮重生成收尾：建候选清单 → 物理硬闸 → 回填 → 更新 plan 的 voice。

为什么必须更新 plan 的 voice：`gate_emotion(ref_emo=...)` 取的是「生成时用的档」。
回填后如果 plan 还写旧 voice，复检会按旧档判 ref_fallback，等于白改一轮。

用法：
  python finish_r2.py --plan-only          # 只建候选清单（给 dialog_gate 跑）
  python finish_r2.py --gate _gate_r2_cand.json   # 用闸门结果做硬闸 + 回填
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")

ACPP_PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
DLG_PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
R2 = "G:/_setup/_regen_r2.json"
R2_OUT = "G:/_setup/_regen_r2_out"
OUT = "G:/_setup/_audio_ch123/out"
BAK = "G:/setup_never"  # 占位，实际备份目录见下
BAK = "G:/_setup/_audio_ch123/out_bak_r2_1111"
CAND_PLAN = "G:/_setup/_dlg_plan_r2_cand.jsonl"
OK_JSON = "G:/_setup/_backfill_r2_ok.json"
LOG = "G:/_setup/_backfill_r2_log.json"

RATIO_LO, RATIO_HI = 0.65, 1.55
PEAK_MAX = 0.999


def texts():
    d = {}
    for line in open(ACPP_PLAN, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            d[r["id"]] = r
    return d


def cmd_plan():
    src = texts()
    todo = json.load(open(R2, encoding="utf-8"))
    out = []
    miss = []
    for r in todo:
        i = r["id"]
        p = os.path.join(R2_OUT, i + ".wav")
        if not os.path.exists(p) or i not in src:
            miss.append(i)
            continue
        out.append({"path": p, "who": src[i].get("speaker"), "emo": r["emo"],
                    "id": i, "voice": r["voice"], "text": src[i]["text"]})
    with open(CAND_PLAN, "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print("候选清单 %d 条 -> %s" % (len(out), CAND_PLAN))
    if miss:
        print("  缺 %d 条: %s" % (len(miss), miss[:8]))


def cmd_gate(gate_json):
    src = texts()
    todo = {r["id"]: r for r in json.load(open(R2, encoding="utf-8"))}
    gate = {r["id"]: r for r in json.load(open(gate_json, encoding="utf-8"))}
    os.makedirs(BAK, exist_ok=True)

    acc, rej = [], []
    for i, g in gate.items():
        new = os.path.join(R2_OUT, i + ".wav")
        old = os.path.join(OUT, i + ".wav")
        if not (os.path.exists(new) and os.path.exists(old)):
            rej.append((i, "文件缺"))
            continue
        d1, d2 = sf.info(old).duration, sf.info(new).duration
        ratio = d2 / d1 if d1 > 0 else 0
        y, _ = sf.read(new, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        pk = float(np.abs(y).max())
        bad = []
        if g["verdict"] == "REGEN":
            bad.append("闸门REGEN")
        if not (RATIO_LO <= ratio <= RATIO_HI):
            bad.append("时长x%.2f" % ratio)
        if pk >= PEAK_MAX:
            bad.append("削波%.3f" % pk)
        if bad:
            rej.append((i, " ".join(bad)))
        else:
            acc.append({"id": i, "verdict": g["verdict"], "ratio": round(ratio, 2),
                        "voice": todo[i]["voice"], "emo": todo[i]["emo"],
                        "dur_old": round(d1, 2), "dur_new": round(d2, 2)})

    print("通过双闸 %d 条 / 拒绝 %d 条" % (len(acc), len(rej)))
    import collections
    print("  通过里判决:", dict(collections.Counter(x["verdict"] for x in acc)))
    print("  拒绝原因:", dict(collections.Counter(x[1].split()[0] for x in rej)))

    log = []
    for x in acc:
        i = x["id"]
        new = os.path.join(R2_OUT, i + ".wav")
        old = os.path.join(OUT, i + ".wav")
        shutil.copy2(old, os.path.join(BAK, i + ".wav"))
        shutil.copy2(new, old)
        log.append(dict(x, action="replaced", backup=os.path.join(BAK, i + ".wav"),
                        at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # 更新 ACL 计划层的 voice（复检要按新档判 ref_emo）
    old_plan = {}
    for line in open(DLG_PLAN, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            old_plan[r["id"]] = r
    vmap = {x["id"]: x["voice"] for x in acc}
    for i, v in vmap.items():
        if i in old_plan:
            old_plan[i]["voice"] = v
    with open(DLG_PLAN, "w", encoding="utf-8") as f:
        for r in old_plan.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    json.dump(acc, open(OK_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    old = []
    if os.path.exists(LOG):
        old = json.load(open(LOG, encoding="utf-8"))
    json.dump(old + log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n回填 %d 条，plan 的 voice 已同步更新 %d 条" % (len(log), len(vmap)))
    print("台账 %s  备份 %s" % (LOG, BAK))

    # 落盘校验
    import hashlib
    bad = [x["id"] for x in log
           if hashlib.md5(open(os.path.join(OUT, x["id"] + ".wav"), "rb").read()).hexdigest()
           != hashlib.md5(open(os.path.join(R2_OUT, x["id"] + ".wav"), "rb").read()).hexdigest()]
    print("落盘校验不一致:", bad if bad else "无 ✓")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--gate", default="")
    a = ap.parse_args()
    if a.plan_only:
        cmd_plan()
    elif a.gate:
        cmd_gate(a.gate)
    else:
        ap.error("给 --plan-only 或 --gate")


if __name__ == "__main__":
    main()
