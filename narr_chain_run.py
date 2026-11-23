# -*- coding: utf-8 -*-
"""旁白生产链（chunk → <rate> 单 span → 停顿移植 → 就绪待验收）。

与 chapter_run.py 同一套调用，只是文本源改成 _narr_blocks.json / _narr_plan_v3.json，
一"块"= 一次 TTS 调用，块内只有一个 <rate> span（实测唯一不丢词的写法）。
"""
import argparse, json, os, sys, time, subprocess
sys.path.insert(0, "G:/_setup")
import numpy as np
import soundfile as sf
import dots_markup as MK
import chapter_run as CR

BLOCKS = r"G:/_setup/_narr_blocks.json"
PLAN = r"G:/_setup/_narr_plan_v3.json"
OUT = r"G:/_setup/_narr_new"
RAW = os.path.join(OUT, "raw")
FIN = os.path.join(OUT, "out")
REP = os.path.join(OUT, "rep")


def dur_of(p):
    try:
        i = sf.info(p)
        return i.frames / float(i.samplerate)
    except Exception:
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", default=BLOCKS)
    ap.add_argument("--plan", default=PLAN)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start", default="")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--gmin", type=float, default=0.85)
    ap.add_argument("--gmax", type=float, default=1.70)
    ap.add_argument("--no-transplant", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    raw = os.path.join(a.out, "raw"); fin = os.path.join(a.out, "out"); rep = os.path.join(a.out, "rep")
    for d in (raw, fin, rep):
        os.makedirs(d, exist_ok=True)

    blocks = json.load(open(a.blocks, encoding="utf-8"))
    plan = json.load(open(a.plan, encoding="utf-8"))
    if isinstance(blocks, dict):
        blocks = blocks.get("blocks") or list(blocks.values())
    pmap = {b["bid"]: b for b in plan["blocks"]}
    base = float(plan.get("base_rate") or 0.80)

    started = False
    if a.start:
        pass
    todo = []
    for b in blocks:
        if a.start and not started:
            if b["bid"] != a.start:
                continue
            started = True
        todo.append(b)
    if a.limit:
        todo = todo[:a.limit]

    print("待跑 %d 块 / 共 %d" % (len(todo), len(blocks)), flush=True)
    ok = skip = fail = 0
    t_all = time.time()
    for i, b in enumerate(todo, 1):
        bid = b["bid"]
        p = pmap.get(bid) or {}
        rate = float(p.get("rate") or base)
        why = str(p.get("why") or "")
        text = b["text"].strip()
        words = b.get("words") or len(text.split())
        mtok = CR.mtok_for(words, rate)
        tag = MK.rate(text, rate)
        rawp = os.path.join(raw, bid + ".wav")
        finp = os.path.join(fin, bid + ".wav")
        repp = os.path.join(rep, bid + ".json")

        if not a.force and os.path.exists(finp) and dur_of(finp) > 3.0:
            print("[%02d/%d] %s SKIP 已有 %.1fs" % (i, len(todo), bid, dur_of(finp)), flush=True)
            skip += 1
            continue

        t0 = time.time()
        rc, msg = CR.call_tts(tag, rawp, seed=a.seed, max_tokens=mtok)
        dt = time.time() - t0
        d = dur_of(rawp)
        if rc != 0 or d < 1.0:
            print("[%02d/%d] %s FAIL rc=%s raw=%.2fs %.0fs %s" % (
                i, len(todo), bid, rc, d, dt, msg[:120]), flush=True)
            fail += 1
            continue

        if a.no_transplant:
            src = rawp
        else:
            rc2, msg2 = CR.transplant(rawp, finp, repp, gmin=a.gmin, gmax=a.gmax)
            if rc2 != 0 or dur_of(finp) < 1.0:
                print("[%02d/%d] %s XPLANT-FAIL rc=%s %s" % (i, len(todo), bid, rc2, msg2), flush=True)
                fail += 1
                continue
            src = finp

        dd = dur_of(src)
        print("[%02d/%d] %s OK %.1fs->%.1fs  gen %.0fs rtf %.1f  rate=%.2f %s" % (
            i, len(todo), bid, d, dd, dt, dt / max(d, 0.1), rate, why[:28]), flush=True)
        ok += 1

    print("DONE ok=%d skip=%d fail=%d  wall=%.0fmin" % (ok, skip, fail, (time.time() - t_all) / 60), flush=True)


if __name__ == "__main__":
    main()
