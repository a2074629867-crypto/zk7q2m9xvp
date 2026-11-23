# -*- coding: utf-8 -*-
"""cand53 选片 → 放进 pick/ 目录 → 重建试听页（**不回填**）。

回填留给人耳点头后再做：上一轮就是先回填再试听，被否一次等于白改 10 条。

用法：
  G:/Python310/python.exe -u _finish53.py --ids c2_0246,...  [--asr]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, "G:/_setup")
import _calm_gate as CG
import _pick52 as PK

ROOT = "G:/_setup"
CAND = os.path.join(ROOT, "_sweep", "cand53")
PICK = os.path.join(CAND, "pick")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--cand", default=CAND)
    ap.add_argument("--pick-dir", default="")
    ap.add_argument("--sum", default=os.path.join(ROOT, "_pick53_summary.json"))
    ap.add_argument("--asr-json", default=os.path.join(ROOT, "_words_cand53.json"))
    ap.add_argument("--out-json", default=os.path.join(ROOT, "_pick53.json"))
    ap.add_argument("--no-asr", action="store_true")
    a = ap.parse_args()

    if not a.no_asr:
        r = subprocess.run([PK.ASR_PY, os.path.join(ROOT, "_asr_lib.py"),
                            "--out", a.asr_json, "--append"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("ASR:", (r.stdout or "").strip()[-200:])
        if r.returncode:
            print("ASR-ERR:", (r.stderr or "")[-400:])

    # 直接复用 pick52 的判定；它自己会再跑一次 ASR（有缓存则很快）
    cmd = [sys.executable, "-u", os.path.join(ROOT, "_pick52.py"),
           "--ids", a.ids, "--cand", a.cand,
           "--asr-json", a.asr_json, "--out", a.out_json]
    if a.no_asr:
        cmd.append("--no-asr")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print((r.stdout or "")[-2500:])

    if not os.path.exists(a.out_json):
        print("选片失败")
        return
    d = json.load(open(a.out_json, encoding="utf-8"))
    rows, best = d["rows"], d["best"]

    pickdir = a.pick_dir or os.path.join(a.cand, "pick")
    os.makedirs(pickdir, exist_ok=True)
    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    plan = CG.load_plan()
    summary = {}
    for i in ids:
        cand_rows = [x for x in rows if x["id"] == i]
        if not cand_rows:
            print("%-9s 无候选" % i)
            continue
        # 先取 pick52 推荐的；没有就按分数取最好的一条
        chosen = next((x for x in cand_rows if x["tag"] == best.get(i)), None)
        if chosen is None:
            cand_rows.sort(key=lambda x: (x["reject"] is not None, -x["score"][0], -x["score"][1]))
            chosen = cand_rows[0]
        src = chosen["path"]
        dst = os.path.join(pickdir, "%s.wav" % i)
        shutil.copyfile(src, dst)
        flag = "OK" if not chosen["reject"] and not chosen["reasons"] else "WARN"
        summary[i] = {"tag": chosen["tag"], "flag": flag,
                      "cov": chosen["cov"], "reasons": chosen["reasons"],
                      "reject": chosen["reject"], "dur": round(chosen["m"]["dur"], 2),
                      "alt": [x["tag"] for x in cand_rows if x["tag"] != chosen["tag"]]}
        print("%-9s <- %-16s %s cov=%s dur=%.2f %s" %
              (i, chosen["tag"], flag, chosen["cov"], chosen["m"]["dur"],
               ";".join((chosen["reject"] or []) + chosen["reasons"])))

    json.dump(summary, open(a.sum, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写入", pickdir, len(summary), "个")


if __name__ == "__main__":
    main()
