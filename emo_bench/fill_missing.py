# -*- coding: utf-8 -*-
"""补齐矩阵缺格：对失败组合扫 seed，取第一个「时长正常且非空音」的。

判据（比 gen_matrix 的 dur>0.5 严）：dur > 1.5s 且 peak > 0.05，
因为失败模式的典型产物是 0.32s / peak 0.001 的空音，dur 阈值放宽会放过垃圾。
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "G:/voice_lib")
import gen_matrix as G
import soundfile as sf
import numpy as np

PIDS = ["C_normal", "C_soft", "C_excited", "C_angry",
        "E_calm", "E_loud", "E_scold", "E_begging"]
CONDS = ["base", "happy", "sad", "angry", "afraid", "calm"]
SEEDS = [2051, 2052, 2054, 2055, 2056, 2057, 2058]


def good(p):
    if not p or not os.path.exists(p):
        return None
    try:
        i = sf.info(p)
        y, _ = sf.read(p, dtype="float32", always_2d=True)
        peak = float(np.abs(y).max())
    except Exception:
        return None
    if i.duration > 1.5 and peak > 0.05:
        return i.duration
    return None


def main():
    idx = os.path.join(G.HERE, "out", "gen_index.jsonl")
    have = {(d["pid"], d["cond"]) for d in map(json.loads, open(idx, encoding="utf-8"))}
    miss = [(p, c) for p in PIDS for c in CONDS if (p, c) not in have]
    print("缺格 %d: %s" % (len(miss), miss), flush=True)
    if not miss:
        return
    with open(idx, "a", encoding="utf-8") as fh:
        for pid, cond in miss:
            got = None
            for sd in SEEDS:
                p, st = G.run_one(pid, cond, sd)
                d = good(p)
                if d:
                    got = (p, sd, d)
                    break
                print("   %s/%s seed=%d 无效(%s)" % (pid, cond, sd, st), flush=True)
                G.time.sleep(8)
            if got:
                p, sd, d = got
                fh.write(json.dumps(dict(pid=pid, cond=cond, seed=sd, path=p,
                                         ref=G.CAST[pid][0], text=G.TEXT,
                                         dur=round(d, 2)), ensure_ascii=False) + "\n")
                fh.flush()
                print("OK %s/%s seed=%d dur=%.2f" % (pid, cond, sd, d), flush=True)
            else:
                print("STILL FAIL %s/%s" % (pid, cond), flush=True)
            G.time.sleep(8)
    print("补齐结束")


if __name__ == "__main__":
    main()
