# -*- coding: utf-8 -*-
"""把 `_regen_out/` 里重生成好的条目录成 dialog_gate 的验收清单，并对比新旧判定。

用法
----
  python mk_regen_gate.py            # 只列已有产物
  python mk_regen_gate.py --run      # 列完直接跑 dialog_gate
"""
import json
import os
import subprocess
import sys

PLAN = "G:/_setup/_castle_en_ch123_plan_v2.jsonl"
OUT_DIR = "G:/_setup/_regen_out"
GATE_IN = "G:/_setup/_regen_gate_all.jsonl"
GATE_OUT = "G:/_setup/_gate_regen.json"


def main():
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(PLAN, encoding="utf-8")}
    rows = []
    for fn in sorted(os.listdir(OUT_DIR)):
        if not fn.endswith(".wav"):
            continue
        i = fn[:-4]
        p = plan.get(i)
        if not p:
            continue
        if os.path.getsize(os.path.join(OUT_DIR, fn)) < 50000:
            continue
        rows.append({"path": "G:/_setup/_regen_out/" + fn,
                     "who": "Thomas" if p["speaker"] == "Edmund" else p["speaker"],
                     "emo": p["emo"], "id": i, "text": p.get("text_src") or p["text"]})
    with open(GATE_IN, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("产物 %d 条 → %s" % (len(rows), GATE_IN))
    if "--run" in sys.argv and rows:
        env = dict(os.environ, PYTHONPATH="G:/_setup;G:/_setup/emo_bench",
                   PYTHONIOENCODING="utf-8")
        subprocess.run(["G:/Python310/python.exe", "G:/_setup/dialog_gate.py",
                        "--plan", GATE_IN, "--lib", "G:/_setup/_emo_refs_all.json",
                        "--bg-map", "G:/_setup/_bg_map.json",
                        "--out", GATE_OUT], cwd="G:/_setup", env=env)


if __name__ == "__main__":
    main()
