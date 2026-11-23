# -*- coding: utf-8 -*-
"""_adv_backfill.py —— 把旧格式 attempts（只有 sps/f0_pct）补成新格式（loc/dur_z/spk）。

为什么需要：`_mt_adv_state.json` 里 15 条重生的 attempts 是 2026-10-26 早些时候
（旧判据：sps + F0 分位）写入的，没有 loc、没有声纹。新回环要靠 loc 判 PASS、
靠声纹一票否决，所以必须按新口径重算一遍再回填。

数据来源：
  loc / dur_z  ← `_adv_prom_regen.json`（同 uid、同 seed 的行）
  spk          ← 现算：重生 wav vs 该单元当前在用版本（原版）
"""
import json
import os
import subprocess
import sys

ROOT = "G:/_setup"
STATE = os.path.join(ROOT, "_mt_adv_state.json")
PY310 = "G:/Python310/python.exe"

sys.path.insert(0, ROOT)
import mt_adv_fix as M   # noqa: E402  只借 prom_wav / judge / SPK_WARN


def main():
    st = json.load(open(STATE, encoding="utf-8"))
    us = st["units"]
    reg = json.load(open(os.path.join(ROOT, "_adv_prom_regen.json"), encoding="utf-8"))["rows"]
    idx = {}
    for r in reg:
        if r.get("verdict") in ("UNMEASURED", "NO_AUDIO"):
            continue
        idx[(r["uid"], str(r["set"]))] = r

    pairs = []
    for u, x in us.items():
        for a in (x.get("attempts") or []):
            w = a.get("wav")
            if not w or not os.path.exists(w):
                continue
            o = os.path.join(ROOT, "_mt_pick", u + ".wav")
            if not os.path.exists(o):
                o = M.orig_wav(u)
            if o:
                pairs.append(dict(uid="%s|%s" % (u, a.get("seed")), a=o, b=w))
    got = {}
    if pairs:
        mf = os.path.join(ROOT, "_spk_man_backfill.json")
        of = os.path.join(ROOT, "_spk_res_backfill.json")
        json.dump(pairs, open(mf, "w", encoding="utf-8"), ensure_ascii=False)
        if os.path.exists(of):
            os.remove(of)
        subprocess.run([PY310, os.path.join(ROOT, "_spk_gate.py"),
                        "--manifest", mf, "--out", of], check=False)
        if os.path.exists(of):
            got = {r["uid"]: r for r in json.load(open(of, encoding="utf-8"))}

    n = 0
    for u, x in sorted(us.items()):
        for a in (x.get("attempts") or []):
            r = idx.get((u, str(a.get("seed"))))
            if r:
                a["loc"] = r.get("loc")
                a["dur_z"] = r.get("dur_z")
                a["sps"] = r.get("sps")
                a["voiced"] = r.get("voiced")
                a["rms_x"] = r.get("rms_x")
            s = got.get("%s|%s" % (u, a.get("seed")))
            if s:
                a["spk"] = s.get("spk")
                a["spk_verdict"] = s.get("verdict")
            # 按新判据重判
            rec = dict(verdict="OK" if a.get("loc") is not None else "UNMEASURED",
                       voiced=a.get("voiced"), rms_x=a.get("rms_x"),
                       dur_z=a.get("dur_z"), loc=a.get("loc"), spk=a.get("spk"))
            j, by = M.judge(rec, "ok" if M.human_ok(x) else None)
            a["judge"], a["by"] = j, by
            n += 1
    st["calibration"] = st.get("calibration", {})
    st["calibration"]["backfill_2026_10_26"] = dict(
        note="attempts 补全 loc/dur_z/spk 并按 F0 单轴 + 声纹闸门重判")
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("%-8s %-3s %-6s %-6s %-6s %s" % ("uid", "sd", "loc", "dur_z", "spk", "判定"))
    for u, x in sorted(us.items()):
        for a in (x.get("attempts") or []):
            print("%-8s %-3s %-6s %-6s %-6s %s"
                  % (u, str(a.get("seed"))[-2:], a.get("loc"), a.get("dur_z"),
                     a.get("spk"), "%s %s" % (a.get("judge"), a.get("by"))))
    print("回填 %d 条 attempt" % n)


if __name__ == "__main__":
    main()
