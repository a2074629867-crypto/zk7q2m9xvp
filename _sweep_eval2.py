# -*- coding: utf-8 -*-
"""_sweep_eval2.py —— 对 `_sweep/cand/` 里的新候选跑同一套闸，与现役 v34 比

为什么不用 `_sweep_eval.py`：那个是为 G/H + 紧张 20 条写死的（按桶类型取判据）。
这次是 7 条「未进过 sweep」的 B/G/H，判据要按「整条 verdict + 关键维度」比。

用法：G:/Python310/python.exe -u _sweep_eval2.py
产物：`_sweep/gate2.json`（候选判决）、`_sweep/pick2.json`（每条挑哪个 seed）
"""
import os, sys, json, glob, subprocess, collections

HERE = "G:/_setup"
PLAN = os.path.join(HERE, "_dlg_plan_v2_paused.jsonl")
BASE = os.path.join(HERE, "_gate_dlg_v34.json")
CAND = os.path.join(HERE, "_sweep", "cand")
OUT_PLAN = os.path.join(HERE, "_sweep", "plan2.jsonl")
OUT_GATE = os.path.join(HERE, "_sweep", "gate2.json")

IDS = ["c1_0052", "c2_0274", "c2_0324", "c2_0430", "c2_0487", "c3_0625", "c3_0632"]

RANK = {"PASS": 3, "MANUAL": 2, "REGEN": 1}


def main():
    plan = {json.loads(l)["id"]: json.loads(l) for l in open(PLAN, encoding="utf-8") if l.strip()}
    rows = []
    seen = set()
    for i in IDS:
        for p in sorted(glob.glob(os.path.join(CAND, "%s__s*.wav" % i))):
            seed = os.path.basename(p).rsplit("__s", 1)[1][:-4]
            if (i, seed) in seen:
                continue
            seen.add((i, seed))
            if i not in plan:
                print("  跳过（不在 plan）", i)
                continue
            r = dict(plan[i])
            r["path"] = p
            r["id"] = "%s__s%s" % (i, seed)
            rows.append(r)
    print("候选 %d 条" % len(rows))
    with open(OUT_PLAN, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    env = dict(os.environ)
    env["PYTHONPATH"] = "G:/_setup;G:/_setup/emo_bench"
    cmd = [r"G:/Python310/python.exe", "-u", "dialog_gate.py",
           "--plan", OUT_PLAN, "--lib", "_emo_refs_all.json",
           "--bg-map", "@_bg_map.json", "--out", OUT_GATE]
    print("跑闸 …", flush=True)
    p = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print((p.stdout or "")[-600:])
    if p.returncode != 0:
        print("闸失败 rc=%s" % p.returncode)
        print((p.stderr or "")[-800:])
        return 1

    base = {x["wav"][:-4]: x for x in json.load(open(BASE, encoding="utf-8"))}
    got = json.load(open(OUT_GATE, encoding="utf-8"))
    by = collections.defaultdict(list)
    for x in got:
        sid = os.path.basename(x["wav"])[:-4]
        rid, _, seed = sid.rpartition("__s")
        by[rid].append((seed, x))

    picks = {}
    for rid in IDS:
        b = base.get(rid)
        if not b:
            continue
        print("\n== %s  现役 %s  %s" % (rid, b["verdict"],
                                        [r["code"] for r in (b.get("reasons") or [])]))
        best = None
        for seed, x in by.get(rid, []):
            codes = [r["code"] for r in (x.get("reasons") or [])]
            print("   s%-3s %-7s %s" % (seed, x["verdict"], codes))
            score = RANK.get(x["verdict"], 0) * 10 - len(codes)
            if best is None or score > best[0]:
                best = (score, seed, x)
        if best and RANK.get(best[2]["verdict"], 0) > RANK.get(b["verdict"], 0):
            picks[rid] = dict(seed=best[1], verdict=best[2]["verdict"],
                              reasons=[r["code"] for r in (best[2].get("reasons") or [])])
    print("\n可回填 %d 条：%s" % (len(picks), json.dumps(picks, ensure_ascii=False)))
    json.dump(picks, open(os.path.join(HERE, "_sweep", "pick2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.exit(main() or 0)
