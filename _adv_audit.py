# -*- coding: utf-8 -*-
"""_adv_audit.py —— 用「原文↔ASR 对齐」重算全部双票单元的声学表现。

与 mt_adv_fix 的区别：不吃 judge 状态，全量重算，用于重新标定阈值。
输出按「最不突出」排序，供抽听。
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, "G:/_setup")
import _adv_check as AC
import _adv_align

ROOT = "G:/_setup"
PLAN = "B:/mt-tts/data/plan/mt_plan3b.json"
PROM_DIR = os.path.join(ROOT, "_wpt_out")
STATE = os.path.join(ROOT, "_mt_adv_state.json")
PY310 = "G:/Python310/python.exe"

FUNC = set("""a an the and or but nor so yet for if because as than that this these those
i you he she it we they me him her us them my your his its our their am is are was were be
been do does did have has had will would can could may might must to of in on at by with
from into about once too then not no up down out off over under again there here all any
some each every other another such what which who whom whose when where why how""".split())


def f0(prom, wav, word, text):
    r = subprocess.run([PY310, os.path.join(ROOT, "_f0_accent.py"),
                        "--prom", prom, "--word", word, "--wav", wav, "--text", text],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300)
    lines = [x for x in (r.stdout or "").strip().splitlines() if x.startswith("{")]
    return json.loads(lines[-1]) if lines else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_adv_audit.json")
    ap.add_argument("--show", type=int, default=12)
    a = ap.parse_args()

    plan = {str(it["id"]): it["text"] for it in
            (lambda d: d if isinstance(d, list) else d.get("items", []))(
                json.load(open(PLAN, encoding="utf-8")))}
    st = json.load(open(STATE, encoding="utf-8"))
    units = st["units"]

    prom_by_uid = {}
    for f in os.listdir(PROM_DIR):
        if f.endswith(".prom") and "__" in f:
            u = f[:-5].split("__", 1)[1]
            prom_by_uid.setdefault(u, []).append(os.path.join(PROM_DIR, f))

    rows = []
    for uid, x in sorted(units.items()):
        text = x["text"]
        adv = x["adv"]
        cands = prom_by_uid.get(uid) or []
        if not cands:
            rows.append(dict(uid=uid, adv=adv, note="no_prom"))
            continue
        best = None
        for p in sorted(cands):
            base = os.path.splitext(os.path.basename(p))[0]
            d, u = base.split("__", 1)
            wav = os.path.join(ROOT, d, u + ".wav")
            if not os.path.exists(wav):
                continue
            got = AC.analyse(text, AC.read_prom(p), uid, d.replace("_mt_raw_s", ""))
            hit = [g for g in got if g["adv"].lower() == adv.lower()]
            if not hit:
                continue
            g = max(hit, key=lambda z: z.get("sps") or 0)
            r = f0(p, wav, adv, text)
            pct = (r.get("rank") or {}).get("pct") if r else None
            rec = dict(uid=uid, adv=adv, seed=d.replace("_mt_raw_s", ""),
                       sps=g.get("sps"), verdict=g["verdict"],
                       synthetic=g.get("synthetic"), f0_pct=pct,
                       f0_loc=(r or {}).get("loc"), n_words=(r or {}).get("n_words"),
                       n_content=((r or {}).get("rank") or {}).get("n"))
            if r is None:
                rec["note"] = "f0_fail"
            if best is None:
                best = rec
            else:
                # 取两轴都最好的那一条
                def score(z):
                    return ((z.get("sps") or 0) / 0.28) + ((z.get("f0_pct") or 0))
                if score(rec) > score(best):
                    best = rec
        if best:
            rows.append(best)

    rows.sort(key=lambda z: ((z.get("sps") or 0) / 0.28) + (z.get("f0_pct") or 0))
    print("%-8s %-13s %-5s %-6s %-6s %-7s %-5s %s"
          % ("uid", "adv", "seed", "sps", "F0分位", "F0峰", "内容词", "备注"))
    for r in rows[:a.show]:
        print("%-8s %-13s %-5s %-6s %-6s %-7s %-5s %s"
              % (r.get("uid"), r.get("adv"), r.get("seed"), r.get("sps"),
                 r.get("f0_pct"), r.get("f0_loc"), r.get("n_content"),
                 r.get("note", "") + ("syn" if r.get("synthetic") else "")))
    ok = [r for r in rows if (r.get("sps") or 0) >= 0.28 or (r.get("f0_pct") or 0) >= 0.65]
    print("\n合计 %d 条；任一路达标 %d 条（%.1f%%）"
          % (len(rows), len(ok), 100.0 * len(ok) / max(1, len(rows))))
    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", a.out)


if __name__ == "__main__":
    main()
