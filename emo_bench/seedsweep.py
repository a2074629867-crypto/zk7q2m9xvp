#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""seed 扫描：同一个 ref + 同一个条件，换 seed 打 N 遍，
看判据值在 seed 之间的方差有多大。

用途：回答「加标签一直重试到合格，行不行」——
如果能过的概率是 P，那期望要试 1/P 次；如果天花板就够不到，重试无穷次也没用。
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_matrix as G

OUTDIR = os.path.join(HERE, "out", "seedsweep")
os.makedirs(OUTDIR, exist_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", required=True)
    ap.add_argument("--cond", required=True)
    ap.add_argument("--seeds", default="3001,3002,3003,3004,3005,3006")
    ap.add_argument("--xvec", default="on")
    a = ap.parse_args()

    seeds = [int(s) for s in a.seeds.split(",")]
    made = []
    t0 = time.time()
    for i, sd in enumerate(seeds):
        # 复用 gen_matrix.run_one，但它写到 out/gen/<tag>.wav，这里事后搬走
        p, st = G.run_one(a.pid, a.cond, sd, a.xvec)
        if st == "ok" and p:
            dst = os.path.join(OUTDIR, "%s__%s__s%d.wav" % (a.pid, a.cond, sd))
            import shutil
            shutil.copy2(p, dst)
            made.append({"path": dst, "pid": a.pid, "cond": a.cond, "seed": sd})
            # 从 out/gen 删掉，避免污染主矩阵索引
            try:
                os.remove(p)
            except Exception:
                pass
        print("  seed %d -> %s" % (sd, st), flush=True)
        time.sleep(8)
        if (i + 1) % 12 == 0:
            time.sleep(60)

    with open(os.path.join(OUTDIR, "_index.jsonl"), "a", encoding="utf-8") as f:
        for m in made:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print("done %d/%d in %.0fs" % (len(made), len(seeds), time.time() - t0))


if __name__ == "__main__":
    main()
