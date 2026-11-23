# -*- coding: utf-8 -*-
"""_c8_eval.py —— C 类（素材/参考档不匹配）8 条返工候选的闸与择优。

为什么有这一批：v35 的 C 10 条里 8 条是 `ref_fallback` ——
生成时该情绪的参考档「不可用」，退回 calm/excited/scold，于是情绪值够不到 p10。
现在两档表（`_ref_tier2.json`）已补全（含 Thomas excited 的最近邻代理档），
用**正确情绪的参考**重生成 3 seed，看能不能把这 8 条拉回通过。

这也正是「检测 → 定位到用错参考 → 换参考重生成 → 复检 → 回填」这条闭环的最后一段。

用法：G:/Python310/python.exe -u _c8_eval.py
产物：`_sweep/gate_c8.json`、`_c8_pick.json`（`_sweep_backfill.py --pick` 可直接吃）
"""
import collections
import glob
import json
import os
import subprocess
import sys

HERE = "G:/_setup"
PLAN = os.path.join(HERE, "_dlg_plan_v2_paused.jsonl")
BASE = os.path.join(HERE, "_gate_dlg_v35.json")
CAND = os.path.join(HERE, "_sweep", "cand3")
OUT_PLAN = os.path.join(HERE, "_sweep", "plan_c8.jsonl")
OUT_GATE = os.path.join(HERE, "_sweep", "gate_c8.json")
PICK = os.path.join(HERE, "_c8_pick.json")

IDS = ["c1_0052", "c2_0295", "c2_0324", "c2_0371",
       "c2_0430", "c3_0632", "c3_0872", "c3_0921"]

RANK = {"PASS": 3, "MANUAL": 2, "REGEN": 1}
EMO_RANK = {"到位": 2, "勉强": 1, "未达": 0, None: 0}


def main():
    global CAND, OUT_PLAN, OUT_GATE, PICK, IDS, BASE
    if "--ids" in sys.argv:
        IDS = [x.strip() for x in sys.argv[sys.argv.index("--ids") + 1].split(",") if x.strip()]
    if "--base" in sys.argv:
        BASE = sys.argv[sys.argv.index("--base") + 1]
    if "--cand" in sys.argv:
        CAND = sys.argv[sys.argv.index("--cand") + 1]
    if "--tag" in sys.argv:
        _t = sys.argv[sys.argv.index("--tag") + 1]
        OUT_PLAN = os.path.join(HERE, "_sweep", "plan_%s.jsonl" % _t)
        OUT_GATE = os.path.join(HERE, "_sweep", "gate_%s.json" % _t)
        PICK = os.path.join(HERE, "_%s_pick.json" % _t)
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(PLAN, encoding="utf-8") if l.strip()}
    rows, seen = [], set()
    for i in IDS:
        for p in sorted(glob.glob(os.path.join(CAND, "%s__s*.wav" % i))):
            seed = os.path.basename(p).rsplit("__s", 1)[1][:-4]
            if (i, seed) in seen:
                continue
            seen.add((i, seed))
            r = dict(plan[i])
            r["path"] = p
            r["id"] = "%s__s%s" % (i, seed)
            rows.append(r)
    print("候选 %d 条" % len(rows))
    if not rows:
        return 1
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
    print((p.stdout or "")[-500:])
    if p.returncode != 0:
        print("闸失败 rc=%s\n%s" % (p.returncode, (p.stderr or "")[-800:]))
        return 1

    base = {os.path.basename(x["wav"])[:-4]: x
            for x in json.load(open(BASE, encoding="utf-8"))}
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
        bc = [r["code"] for r in (b.get("reasons") or [])]
        be = (b.get("emo_res") or {})
        print("\n== %s  现役 %s  %s" % (rid, b["verdict"], bc))
        best = None
        for seed, x in sorted(by.get(rid, [])):
            codes = [r["code"] for r in (x.get("reasons") or [])]
            e = (x.get("emo_res") or {})
            n = (x.get("nat") or {})
            g = (x.get("gates") or {})
            ok = RANK.get(x["verdict"], 0) > RANK.get(b["verdict"], 0)
            # 不退步：情绪档不许降、自然度不许从 ok 掉到 fail、时长不许缩到 0.85 倍以下
            if EMO_RANK.get(e.get("tier"), 0) < EMO_RANK.get(be.get("tier"), 0):
                ok = False
            if n.get("code") == "nat_fail":
                ok = False
            try:
                if float(x["tech"]["dur"]) < 0.85 * float(b["tech"]["dur"]):
                    ok = False
            except (KeyError, TypeError, ValueError):
                pass
            print("   s%-3s %-7s %-7s emo=%-4s nat=%-7s %s" %
                  (seed, x["verdict"], g.get("tech"), e.get("tier"),
                   n.get("code"), (codes or "")))
            if ok:
                sc = RANK.get(x["verdict"], 0) * 10 - len(codes)
                if best is None or sc > best[0]:
                    best = (sc, seed, x, codes)
        if best:
            _, seed, x, codes = best
            picks[rid] = dict(seed=seed, verdict=x["verdict"], reasons=codes,
                              emo=(x.get("emo_res") or {}).get("tier"),
                              intra=(x.get("gates") or {}).get("intra"),
                              nat=(x.get("nat") or {}).get("code"),
                              why="c8: 换正确情绪参考后重生成")

    print("\n可回填 %d / %d 条：%s" % (len(picks), len(IDS),
                                   json.dumps(picks, ensure_ascii=False)))
    json.dump(dict(picks=picks, keep=[i for i in IDS if i not in picks]),
              open(PICK, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s" % PICK)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
