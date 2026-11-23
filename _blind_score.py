# -*- coding: utf-8 -*-
"""盲测打分：对比多个 rater 的判定与人工 gold，并检验「多 Agent 合议」是否真的涨准确率。

    python _blind_score.py

输入：G:/_setup/_blind/out_*.json（每个 rater 一份）+ key.json + _accent_eval_set.json
输出：每个 rater 的准确率 / 伪影 P-R-F1 / 假阳性率，两两一致性，
     以及多数投票（2/3、3/3 一致时）的准确率。
"""
import glob
import json
import os
import re
from itertools import combinations

BL = "G:/_setup/_blind"
GOLD = "G:/_setup/_accent_eval_set.json"

ART = "cwt_artifact"
VAL = "valid_focus"


def norm_label(x):
    u = str(x).upper()
    if "ARTIFACT" in u:
        return ART
    if "VALID" in u:
        return VAL
    return None


def load_rater(path):
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"\[.*\]", txt, re.S)
    if not m:
        raise ValueError(f"no json array in {path}")
    arr = json.loads(m.group(0))
    out = {}
    for row in arr:
        k = str(row.get("id", "")).strip().upper()
        lab = norm_label(row.get("label", row.get("verdict", "")))
        if k and lab:
            out[k] = {"label": lab, "reason": row.get("reason", "")}
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma separated rater names, e.g. B,step5,hy4")
    a = ap.parse_args()

    key = json.load(open(os.path.join(BL, "key.json"), encoding="utf-8"))
    g = json.load(open(GOLD, encoding="utf-8"))
    blind = json.load(open(os.path.join(BL, "blind_ctx.json"), encoding="utf-8"))
    top1_by_id = {b["id"]: b["top1"].strip().lower() for b in blind}
    gold_by = {(it["uid"], it["top1"].strip().lower()): it for it in g["items"]}

    ids = sorted(key)
    gold = {}
    group = {}
    disputed = set()
    ambig = set()
    for x in ids:
        it = gold_by[(key[x], top1_by_id[x])]
        gold[x] = ART if it["label"] == ART else VAL
        group[x] = it.get("group", "?")
        if it.get("disputed"):
            disputed.add(x)
        if it["label"] == "ambiguous":
            ambig.add(x)
    clean = [x for x in ids if x not in disputed and x not in ambig]

    files = sorted(glob.glob(os.path.join(BL, "out_*.json")))
    if a.only:
        keep = {x.strip() for x in a.only.split(",") if x.strip()}
        files = [f for f in files
                 if os.path.basename(f).rsplit(".", 1)[0].replace("out_", "") in keep]
    if not files:
        raise SystemExit("no out_*.json found")

    raters = {}
    for f in files:
        name = os.path.basename(f).rsplit(".", 1)[0].replace("out_", "")
        r = load_rater(f)
        miss = [x for x in ids if x not in r]
        if miss:
            print(f"[warn] {name} missing {len(miss)}: {miss[:6]}")
        raters[name] = r

    print(f"gold: {len(ids)}  (artifact {sum(1 for v in gold.values() if v==ART)}, "
          f"valid {sum(1 for v in gold.values() if v==VAL)})")
    print(f"raters: {list(raters)}\n")

    hdr = f"{'rater':8s} {'n':>3s} {'acc':>6s} {'P(art)':>7s} {'R(art)':>7s} {'F1':>6s} {'FP':>3s} {'FN':>3s}  {'acc_fn':>7s} {'acc_ct':>7s}"
    print(hdr)
    print("-" * len(hdr))
    per = {}
    for name, r in raters.items():
        tp = fp = tn = fn = 0
        for x in ids:
            if x not in r:
                continue
            p, y = r[x]["label"], gold[x]
            if y == ART and p == ART:
                tp += 1
            elif y == ART:
                fn += 1
            elif p == ART:
                fp += 1
            else:
                tn += 1
        n = tp + fp + tn + fn
        acc = (tp + tn) / n
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        per[name] = {"acc": acc, "tp": tp, "fp": fp, "tn": tn, "fn": fn}
        def gacc(grp):
            xs = [x for x in ids if group[x] == grp and x in r]
            if not xs:
                return float("nan")
            return sum(1 for x in xs if r[x]["label"] == gold[x]) / len(xs)
        print(f"{name:8s} {n:3d} {acc:6.3f} {prec:7.3f} {rec:7.3f} {f1:6.3f} {fp:3d} {fn:3d}  "
              f"{gacc('function_top1'):7.3f} {gacc('content_top1'):7.3f}")

    names = [n for n in raters if all(x in raters[n] for x in ids)]
    if len(names) < 2:
        print("\n(need >=2 complete raters for agreement)")
        return

    print("\n=== pairwise agreement ===")
    for a, b in combinations(names, 2):
        same = sum(1 for x in ids if raters[a][x]["label"] == raters[b][x]["label"])
        both_wrong = sum(1 for x in ids
                         if raters[a][x]["label"] == raters[b][x]["label"] != gold[x])
        print(f"  {a} vs {b}: agree {same}/{len(ids)} = {same/len(ids)*100:.1f}%   "
              f"一致且都错 {both_wrong}")

    print("\n=== majority vote (>=2 of N) ===")
    vote = {}
    for x in ids:
        labs = [raters[n][x]["label"] for n in names]
        vote[x] = ART if labs.count(ART) > labs.count(VAL) else VAL if labs.count(VAL) > labs.count(ART) else None
    decided = [x for x in ids if vote[x]]
    acc = sum(1 for x in decided if vote[x] == gold[x]) / len(decided)
    print(f"  decided {len(decided)}/{len(ids)}   acc={acc:.3f}   "
          f"ties {len(ids)-len(decided)}")

    print("\n=== unanimous only ===")
    un = [x for x in ids if len({raters[n][x]["label"] for n in names}) == 1]
    if un:
        accu = sum(1 for x in un if raters[names[0]][x]["label"] == gold[x]) / len(un)
        print(f"  unanimous {len(un)}/{len(ids)} ({len(un)/len(ids)*100:.1f}%)   acc on those = {accu:.3f}")
        print(f"  => 一致不等于正确：{'成立' if accu < 0.95 else '不成立'}")
        # 一致性覆盖 vs 正确率增益
    print("\n=== cost of agreement ===")
    covered = len(un) / len(ids)
    single = sum(per[n]["acc"] for n in names) / len(names)
    print(f"  best single acc {max(per[n]['acc'] for n in names):.3f} / mean {single:.3f}")
    print(f"  unanimous coverage {covered*100:.0f}%  acc {accu if un else float('nan'):.3f}")

    print("\n=== clean subset (drop 3 ambiguous + 5 disputed) ===")
    print(f"  n={len(clean)}  (artifact {sum(1 for x in clean if gold[x]==ART)}, "
          f"valid {sum(1 for x in clean if gold[x]==VAL)})")
    for name, r in raters.items():
        xs = [x for x in clean if x in r]
        if not xs:
            continue
        ok = sum(1 for x in xs if r[x]["label"] == gold[x])
        fp = sum(1 for x in xs if gold[x] == VAL and r[x]["label"] == ART)
        fn = sum(1 for x in xs if gold[x] == ART and r[x]["label"] == VAL)
        print(f"  {name:8s} acc={ok/len(xs):.3f} ({ok}/{len(xs)})  FP={fp} FN={fn}")
    if len(names) >= 2:
        un2 = [x for x in clean if len({raters[n][x]["label"] for n in names}) == 1]
        if un2:
            oku = sum(1 for x in un2 if raters[names[0]][x]["label"] == gold[x])
            print(f"  unanimous on clean: {len(un2)}/{len(clean)}  acc={oku/len(un2):.3f}")

    print("\n=== per-item table ===")
    print(f"{'id':5s} {'grp':14s} {'gold':12s} " + " ".join(f"{n[:6]:>6s}" for n in names))
    for x in ids:
        cells = " ".join(f"{'ART' if raters[n][x]['label']==ART else 'val':>6s}" for n in names)
        mark = "  <<" if any(raters[n][x]["label"] != gold[x] for n in names) else ""
        print(f"{x:5s} {group[x]:14s} {'ART' if gold[x]==ART else 'val':12s} {cells}{mark}")


if __name__ == "__main__":
    main()
