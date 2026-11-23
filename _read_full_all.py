# -*- coding: utf-8 -*-
"""全量「读全率」扫描：239 条对白 + 716 条旁白，找出「闸全 PASS 但整句没读完」的交付件。

起因（2026-11-15 18:5x）：`c1_0034` 七闸全 PASS，但 ASR 只认出后半句 4 个词（召回 0.40），
前半 2.5s 是糊的；`c2_0369`（"no schools are free"）ASR **一个词都认不出**。
七闸里没有任何一维管「有没有把字念出来」，这一维是空的。

输出：`_read_full_<tag>.json`，每条 {id, recall, n_asr, n_ref, hyp}
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

AUD = os.path.join(HERE, "_audio_ch123", "out_paused")
NARR = os.path.join(HERE, "_audio_narr_paused")
PLAN = os.path.join(HERE, "_dlg_plan_v2.jsonl")
CASTLE = os.path.join(HERE, "_castle_en_ch123_plan.jsonl")


def norm_words(s):
    import re
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[^A-Za-z']+", " ", s)
    return [w.lower().strip("'") for w in s.split() if w.strip("'")]


def recall(ref, hyp):
    if not ref:
        return 0.0
    i = hit = 0
    for w in hyp:
        while i < len(ref):
            if ref[i] == w or ref[i] in w or w in ref[i]:
                hit += 1
                i += 1
                break
            i += 1
        else:
            break
    return hit / float(len(ref))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", choices=["dlg", "narr"], default="dlg")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    from transplant_prosody2 import word_times

    if a.track == "dlg":
        plan = {}
        for l in open(PLAN, encoding="utf-8"):
            l = l.strip()
            if l:
                o = json.loads(l)
                plan[o["id"]] = o
        root = AUD
    else:
        plan = {}
        for l in open(CASTLE, encoding="utf-8"):
            l = l.strip()
            if not l:
                continue
            o = json.loads(l)
            if not o.get("dialog"):
                plan[o["id"]] = dict(o, who="narrator")
        root = NARR

    ids = [k for k in plan if os.path.exists(os.path.join(root, k + ".wav"))]
    ids.sort()
    if a.limit:
        ids = ids[:a.limit]
    print("扫 %d 条（%s）" % (len(ids), root), flush=True)

    out = []
    for n, k in enumerate(ids, 1):
        ref = norm_words(plan[k].get("text") or "")
        p = os.path.join(root, k + ".wav")
        try:
            hyp = norm_words(" ".join(t for _a, _b, t in word_times(p)))
        except Exception as e:  # noqa: BLE001
            out.append(dict(id=k, err=str(e)[:80]))
            continue
        r = recall(ref, hyp)
        out.append(dict(id=k, recall=round(r, 3), n_asr=len(hyp), n_ref=len(ref),
                        hyp=" ".join(hyp)[:160]))
        if n % 20 == 0:
            print("  %d/%d" % (n, len(ids)), flush=True)

    tag = a.out or os.path.join(HERE, "_read_full_%s.json" % a.track)
    json.dump(out, open(tag, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    ok = [x for x in out if "recall" in x]
    bad = sorted([x for x in ok if x["recall"] < 0.80], key=lambda z: z["recall"])
    print("完成 %d 条；召回 <0.80 共 %d 条（%.1f%%）"
          % (len(ok), len(bad), 100.0 * len(bad) / max(1, len(ok))), flush=True)
    for x in bad[:40]:
        print("  %-9s 召回 %.2f  ASR %d/%d 词  %s"
              % (x["id"], x["recall"], x["n_asr"], x["n_ref"], x["hyp"][:70]), flush=True)
    print("写出", tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
