# -*- coding: utf-8 -*-
"""_backfill_r6b.py —— r6 非「警惕」13 条的逐条裁决与回填（2026-11-13）。

为什么不直接用 finish_r6.py --gate：那份只看闸门三闸，不看「新条比旧条丢字」。
本轮 ASR A/B（_asr_ab_r6.json）拓出 4 条「闸门 PASS/MANUAL 但实际丢字」的，
必须逐条否决 —— 二选一这种事不许整批过。

裁决口径（三条硬闸，缺一不可）：
  1) 闸门 verdict 不得为 REGEN
  2) ASR 覆盖率不得比旧条低 0.05 以上（cov_new ≥ cov_old − 0.05）
  3) 声纹不得从 PASS 掉到 MANUAL
已回填的 8 条（01:02）仍按同一口径复核，不重复动文件。
"""
import hashlib
import json
import os
import shutil
from datetime import datetime

HERE = "G:/_setup"
OUT = os.path.join(HERE, "_audio_ch123", "out")
SRC = os.path.join(HERE, "_regen_r6_out")
BAK = os.path.join(HERE, "_audio_ch123", "out_bak_r6_1113")
PLAN = os.path.join(HERE, "_dlg_plan_v2.jsonl")
LOG = os.path.join(HERE, "_backfill_r6b_log.json")

# (id, 结论, 理由)
DEC = [
    ("c2_0306", "accept", "REGEN mostly_silence → MANUAL；ASR 0.81→0.94（丢字减少）"),
    ("c2_0326", "accept", "ref_fallback 消失；ASR 0.95→0.95；仅剩 intra_drift（与旧同）"),
    ("c3_0655", "accept", "ref_poor → PASS；ASR 1.00/1.00"),
    ("c1_0052", "reject", "闸门仅 MANUAL，但 ASR 1.00→0.60，丢 anyway/cricket（新档拖慢到 94wpm 反而模糊）"),
    ("c2_0371", "reject", "ASR 1.00→0.22，只剩 Boring schools on free.（真截断）"),
    ("c2_0468", "reject", "ASR 1.00→0.86，丢 you've/that's/all"),
    ("c3_0643", "reject", "闸门 PASS，但 ASR 0.82→0.64（旧也有 0.82，本身偏低）；文本还有 babybaby 拼接错误"),
]


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def main():
    asr = {x["id"]: x for x in json.load(open(os.path.join(HERE, "_asr_ab_r6.json"), encoding="utf-8"))}
    r6 = {x["id"]: x for x in json.load(open(os.path.join(HERE, "_regen_r6.json"), encoding="utf-8"))}
    plan = {}
    for line in open(PLAN, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            plan[r["id"]] = r
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    os.makedirs(BAK, exist_ok=True)

    done = 0
    for i, dec, why in DEC:
        old = os.path.join(OUT, i + ".wav")
        new = os.path.join(SRC, i + ".wav")
        a = asr.get(i, {})
        rec = dict(id=i, decision=dec, why=why, voice=r6[i]["voice"], emo=r6[i]["emo"],
                   cov_old=a.get("cov_old"), cov_new=a.get("cov_new"),
                   miss_new=a.get("miss_new"),
                   at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if dec == "accept":
            if not os.path.exists(new):
                rec["decision"] = "skip"
                rec["why"] += "（候选文件缺失）"
            else:
                bp = os.path.join(BAK, i + ".wav")
                if not os.path.exists(bp):
                    shutil.copy2(old, bp)
                shutil.copy2(new, old)
                okmd5 = md5(old) == md5(new)
                rec["backup"] = bp
                rec["md5_ok"] = okmd5
                plan[i]["voice"] = r6[i]["voice"]
                done += 1
        log.append(rec)
        print("%-9s %-7s cov %.2f→%.2f  %s" % (i, rec["decision"],
                                             a.get("cov_old") or 0, a.get("cov_new") or 0, why))

    if done:
        with open(PLAN, "w", encoding="utf-8", newline="\n") as f:
            for r in plan.values():
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n回填 %d 条 · 台账 %s" % (done, LOG))
    for x in log:
        if x["decision"] == "accept" and not x.get("md5_ok", True):
            print("  !! md5 不一致：%s" % x["id"])


if __name__ == "__main__":
    main()
