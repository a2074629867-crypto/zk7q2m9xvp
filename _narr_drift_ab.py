# -*- coding: utf-8 -*-
"""_narr_drift_ab.py —— 旁白 726 条：注入停顿前后的漂移判决 A/B

同一判据（ver3）、同一 profile="narr"，唯一区别是文件本身；
paused 侧额外喂 allow_gaps（来自注入报告的插入区间），把「设计停顿」从「失声」里摘出去。
用法：G:/Python310/python.exe -u _narr_drift_ab.py -j 5
"""
import sys, os, json, argparse
import concurrent.futures as cf

sys.path.insert(0, "G:/_setup")
import mt_seg_drift as M

HERE = "G:/_setup"
REP = os.path.join(HERE, "_audio_narr_paused", "_pause_report.json")


def task(job):
    sid, raw, paused, gaps = job
    out = {"sid": sid}
    for tag, p, g in (("raw", raw, None), ("paused", paused, gaps)):
        try:
            r = M.one(p, profile="narr", gaps=g, silence_tolerant=True)
            out[tag] = dict(v=r["verdict"], span=r["span"].get("span_st"),
                            dur=r["dur"], n=len(r["events"]),
                            fails=[(e["t"], e["why"]) for e in r["events"] if e["level"] == "FAIL"])
        except Exception as e:  # noqa: BLE001
            out[tag] = dict(v="ERROR", err=str(e))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", type=int, default=5)
    ap.add_argument("--out", default=os.path.join(HERE, "_narr_drift_ab.json"))
    a = ap.parse_args()

    rep = {r["k"]: r for r in json.load(open(REP, encoding="utf-8"))}
    ids = open(os.path.join(HERE, "_narr_ids.txt")).read().split(",")
    jobs = []
    for i in ids:
        if not i:
            continue
        raw = os.path.join(HERE, "_audio_ch123", "out", i + ".wav")
        pz = os.path.join(HERE, "_audio_narr_paused", i + ".wav")
        if not (os.path.exists(raw) and os.path.exists(pz)):
            continue
        r = rep.get(i) or {}
        gaps = [(b["t"], b["t"] + (b.get("after") or 0))
                for b in (r.get("bounds") or []) if b.get("op") == "ins"]
        jobs.append((i, raw, pz, gaps or None))
    print("待测 %d 条" % len(jobs), flush=True)

    rows = []
    with cf.ProcessPoolExecutor(max_workers=a.j) as ex:
        for k, r in enumerate(ex.map(task, jobs), 1):
            rows.append(r)
            if k % 100 == 0:
                print("  %d/%d" % (k, len(jobs)), flush=True)

    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    import collections
    c0 = collections.Counter(r["raw"]["v"] for r in rows)
    c1 = collections.Counter(r["paused"]["v"] for r in rows)
    print("raw    ", dict(c0))
    print("paused ", dict(c1))
    up = [(r["sid"], r["raw"]["v"], r["paused"]["v"]) for r in rows
          if r["raw"]["v"] == "PASS" and r["paused"]["v"] != "PASS"]
    dn = [(r["sid"], r["raw"]["v"], r["paused"]["v"]) for r in rows
          if r["paused"]["v"] == "FAIL" and r["raw"]["v"] != "FAIL"]
    print("PASS→非PASS %d 条：%s" % (len(up), up[:10]))
    print("新 FAIL %d 条：%s" % (len(dn), dn[:10]))
    good2bad = [(r["sid"], r["raw"]["v"], r["paused"]["v"]) for r in rows
                if r["paused"]["v"] == "FAIL"]
    print("paused 侧 FAIL %d 条" % len(good2bad))
    for x in good2bad[:12]:
        print("   ", x)


if __name__ == "__main__":
    main()
