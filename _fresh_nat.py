# -*- coding: utf-8 -*-
"""_fresh_nat.py —— 回填后刷新自然度缓存。

为什么必须刷：`gate_nat.check` 对**交付目录**里的条目走缓存分支（缓存里存 raw，
判决按对白参照重算）。文件被回填覆盖后，raw 还是旧音频的 —— 不刷新，全量复检
就是在拿旧分数审新音频，整轮回填白干。

★ 2026-11-13 01:45 修：原来写死只读 `_backfill_r5_log.json`，r6 回填后压根没刷到。
  改为合并多份台账（默认 r5 + r6），并且参考档记录按实际用到的 tier 自动补，
  不再写死 `Charles_nervous_2 / Charles_angry_2` 两个名字。

用法：
  G:/Python310/python.exe _fresh_nat.py
  G:/Python310/python.exe _fresh_nat.py --logs _backfill_r5_log.json,_backfill_r6_log.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
import _nat_guard as NG

HERE = "G:/_setup"
NAT = os.path.join(HERE, "_nat_dlg.json")
VNAT = os.path.join(HERE, "_voice_nat.json")
REF_MIN = 2.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="_backfill_r5_log.json,_backfill_r6_log.json")
    a = ap.parse_args()

    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
    nat = json.load(open(NAT, encoding="utf-8"))

    done, tiers = set(), set()
    for name in a.logs.split(","):
        p = os.path.join(HERE, name.strip())
        if not os.path.exists(p):
            print("跳过（不存在）：%s" % name, flush=True)
            continue
        for x in json.load(open(p, encoding="utf-8")):
            if x.get("action") == "replaced":
                done.add(x["id"])
                if x.get("voice"):
                    tiers.add(x["voice"])
    print("刷新 %d 条已回填记录（来自 %s）" % (len(done), a.logs), flush=True)

    miss = []
    for k, i in enumerate(sorted(done), 1):
        p = os.path.join(HERE, "_audio_ch123/out", i + ".wav")
        if not os.path.exists(p):
            miss.append(i)
            continue
        r = NG.verdict(p, domain="dlg")
        r["who"] = nat.get(i, {}).get("who") or plan.get(i, {}).get("who")
        r["emo"] = nat.get(i, {}).get("emo") or plan.get(i, {}).get("emo")
        r["tier"] = plan.get(i, {}).get("voice") or nat.get(i, {}).get("tier")
        old = nat.get(i, {}).get("score")
        nat[i] = r
        print("  [%2d/%d] %-8s %-20s score %6s -> %6s  %s" % (
            k, len(done), i, r.get("tier"), old, r.get("score"), r.get("verdict")), flush=True)
    if miss:
        print("  缺文件（未刷新）：%s" % miss, flush=True)

    json.dump(nat, open(NAT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("-> _nat_dlg.json 已更新（%d 条）" % len(nat), flush=True)

    print("\n补参考档质量记录", flush=True)
    vn = json.load(open(VNAT, encoding="utf-8"))
    for tier in sorted(tiers):
        p = os.path.join(HERE, "_cloud_backup/voice_lib", tier + ".wav")
        if not os.path.exists(p):
            print("  %-22s 参考文件缺（跳过）" % tier, flush=True)
            continue
        r = NG.raw(p) or {}
        vn[tier] = dict(mos=r.get("nq_mos"), noi=r.get("nq_noi"), dis=r.get("nq_dis"),
                        col=r.get("nq_col"), sp=r.get("sp"))
        print("  %-22s MOS %.2f  ref_poor=%s" % (
            tier, r.get("nq_mos") or 0, (r.get("nq_mos") or 0) < REF_MIN), flush=True)
    json.dump(vn, open(VNAT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("-> _voice_nat.json 已更新（%d 条）" % len(vn), flush=True)


if __name__ == "__main__":
    main()
