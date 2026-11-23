# -*- coding: utf-8 -*-
"""_nat_narr_table.py —— 给旁白 865 条出自然度判决表（不重跑模型，只重算判决）。

依赖：`_nat_cache.json`（键 = 文件名|md5）+ `_nat_stat.json`（旁白参照）
判据：`_nat_guard.score_raw(domain='narr')` —— FAIL<-2.3σ / WARN<-1.4σ / 语音<0.9s 不判
"""
import json, os, glob, collections
import sys
sys.path.insert(0, "G:/_setup")
import _nat_guard as NM

PICK = "G:/_setup/_mt_pick"
OUT = "G:/_setup/_nat_narr.json"

stat = NM.load_stat("narr")
cache = NM._cache()
print("[ref] nq_mos %.2f+-%.2f n=%d | reg a=%.2f b=%.2f r=%.2f" % (
    stat["nq_mos"]["mean"], stat["nq_mos"]["sd"], stat["nq_mos"]["n"],
    stat["_reg"]["a"], stat["_reg"]["b"], stat["_reg"]["r"]))

wavs = sorted(glob.glob(os.path.join(PICK, "*.wav")))
rows, miss = [], []
for i, w in enumerate(wavs, 1):
    k = NM._key(w)
    c = cache.get(k)
    uid = os.path.splitext(os.path.basename(w))[0]
    if not c or "nq_mos" not in c or "squim" not in c:
        miss.append(uid)
        rows.append(dict(uid=uid, verdict="UNMEASURED", why="no fingerprint in cache"))
        continue
    if not c.get("sp"):
        # 缓存里 2061/2929 条没存语音时长（旧版 _nat_guard 不写 sp）。
        # 不重跑模型：raw() 命中缓存时只现算 trimmed 时长，NISQA/SQUIM 直接复用。
        c = dict(NM.raw(w))
    d = NM.score_raw(dict(c), stat=stat, domain="narr")
    rows.append(dict(uid=uid, verdict=d["verdict"], score=d.get("score"),
                     ens=d.get("ens"), res=d.get("res"), axis=d.get("axis"),
                     sp=c.get("sp"), why=d["why"]))
    if i % 200 == 0:
        print("  %d/%d" % (i, len(wavs)), flush=True)

json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
cnt = collections.Counter(r["verdict"] for r in rows)
print("\n[verdict] %s  total %d" % (dict(cnt), len(rows)))
print("[coverage] measured %d | cache miss %d" % (len(rows) - len(miss), len(miss)))

fails = sorted([r for r in rows if r["verdict"] == "FAIL"], key=lambda x: x["score"] or 0)
print("\n[FAIL %d]" % len(fails))
for r in fails[:30]:
    print("  %-7s %+6.2f  %s" % (r["uid"], r["score"] or 0, (r.get("why") or "")[:40]))
warns = [r for r in rows if r["verdict"] == "WARN"]
print("\n[WARN %d] worst 10:" % len(warns))
for r in sorted(warns, key=lambda x: x["score"] or 0)[:10]:
    print("  %-7s %+6.2f" % (r["uid"], r["score"] or 0))
short = [r for r in rows if r["verdict"] == "UNKNOWN"]
print("\n[too short %d]" % len(short))
if miss:
    print("[cache miss %d] %s%s" % (len(miss), miss[:10], " ..." if len(miss) > 10 else ""))
