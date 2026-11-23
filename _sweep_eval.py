# -*- coding: utf-8 -*-
"""_sweep_eval.py —— 多 seed 候选的统一闸门评估 + 择优

为什么统一走 `dialog_gate.py`：候选必须和交付同口径（同一套声纹/情绪/自然度/句内漂移判据），
自己另写一套阈值，就是 DECISIONS 里记过的那种「边界抖动被当成修复」的坑。

口径取舍：
  - **关掉 scs（档内一致性）**：它要拿同档全部句子当背景，候选只有 30 条，背景不对，
    算出来的 cos 中位没有意义。回填后再用全量 v33 看它。
  - 其余全开（含第 8 维三路，用于看句内漂移有没有被修掉）
  - 必须带 `--lib _emo_refs_all.json --bg-map @_bg_map.json`（漏了就 Z-norm 混域，假跌）

用法：
  G:/Python310/python.exe _sweep_eval.py --dry     # 只打印将要跑的命令
  G:/Python310/python.exe _sweep_eval.py           # 跑 gate
  G:/Python310/python.exe _sweep_eval.py --pick    # 只按已有结果择优
"""
import argparse
import json
import os
import subprocess
import sys

HERE = "G:/_setup"
CAND = os.path.join(HERE, "_sweep", "cand")
EV = os.path.join(HERE, "_sweep", "eval")
PLAN = os.path.join(HERE, "_dlg_plan_v2.jsonl")
BASE = os.path.join(HERE, "_gate_dlg_v32.json")
OUT = os.path.join(HERE, "_sweep", "pick.json")
PY = "G:/Python310/python.exe"


def load_plan():
    return {json.loads(l)["id"]: json.loads(l) for l in open(PLAN, encoding="utf-8") if l.strip()}


def seeds():
    s = set()
    for f in os.listdir(CAND):
        if f.endswith(".wav") and "__s" in f:
            s.add(f.rsplit("__s", 1)[1][:-4])
    return sorted(s)


def build_plans():
    plan = load_plan()
    os.makedirs(EV, exist_ok=True)
    made = []
    for sd in seeds():
        src = os.path.join(EV, "plan_s%s.jsonl" % sd)
        rows = []
        for f in sorted(os.listdir(CAND)):
            if not f.endswith(".wav") or not f.endswith("__s%s.wav" % sd):
                continue
            rid = f.split("__s")[0]
            p = plan.get(rid)
            if not p:
                continue
            rows.append(dict(path=os.path.join(CAND, f), who=p["who"], emo=p["emo"],
                             id=rid, voice=p.get("voice"), text=p.get("text")))
        with open(src, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        made.append((sd, src, len(rows)))
    return made


def run_gate(made, dry=False):
    outs = []
    for sd, src, n in made:
        out = os.path.join(EV, "gate_s%s.json" % sd)
        cmd = [PY, os.path.join(HERE, "dialog_gate.py"),
               "--plan", src, "--out", out, "--no-scs",
               "--lib", os.path.join(HERE, "_emo_refs_all.json"),
               "--bg-map", "@" + os.path.join(HERE, "_bg_map.json")]
        print("[s%s] %d 条 → %s" % (sd, n, out), flush=True)
        print("   " + " ".join(cmd), flush=True)
        if dry:
            continue
        r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        tail = (r.stdout or "").strip().splitlines()[-3:]
        print("   rc=%d %s" % (r.returncode, " | ".join(tail)), flush=True)
        if r.returncode != 0:
            print("   stderr:", (r.stderr or "")[-400:], flush=True)
        if os.path.exists(out):
            outs.append(out)
    return outs


def tgt_of(base, rid):
    """原条的主要问题类型。"""
    b = base.get(rid) or {}
    codes = [x["code"] for x in (b.get("reasons") or [])]
    e = (b.get("emo_res") or {})
    if "nat_fail" in codes:
        return "nat"
    if "intra_drift" in codes:
        return "intra"
    if any(c.startswith("scs") for c in codes):
        return "scs"
    if e.get("tier") in ("未达", "勉强"):
        return "emo"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--pick", action="store_true")
    a = ap.parse_args()

    made = build_plans()
    print("候选 seed: %s" % ", ".join("s%s(%d)" % (s, n) for s, _, n in made), flush=True)
    if not a.pick:
        run_gate(made, dry=a.dry)
        if a.dry:
            return

    base = {x["wav"][:-4]: x for x in json.load(open(BASE, encoding="utf-8"))}
    # 汇总所有候选
    cands = {}
    for sd, _src, _n in made:
        p = os.path.join(EV, "gate_s%s.json" % sd)
        if not os.path.exists(p):
            continue
        for x in json.load(open(p, encoding="utf-8")):
            rid = x["id"]
            cands.setdefault(rid, []).append(dict(seed=sd, res=x))

    print("\n%-9s %-6s %-22s %s" % ("id", "目标", "原判", "候选"))
    picks, keep = {}, []
    for rid, cs in sorted(cands.items()):
        b = base.get(rid)
        if not b:
            continue
        t = tgt_of(base, rid)
        bg = b.get("gates") or {}
        be = (b.get("emo_res") or {})
        bnat = (b.get("nat") or {}).get("score")

        RANK = {"到位": 2, "勉强": 1, "未达": 0, None: 0}

        def no_regress(c):
            """非目标维度不许退步：情绪档位不许降、句内不许从 PASS 掉到 FAIL、时长不少于 0.85×"""
            e = (c["res"].get("emo_res") or {})
            n = (c["res"].get("nat") or {})
            g = (c["res"].get("gates") or {})
            if RANK.get(e.get("tier"), 0) < RANK.get(be.get("tier"), 0):
                return False
            if (bg.get("intra") == "PASS") and g.get("intra") == "FAIL":
                return False
            if (b.get("nat") or {}).get("code") == "nat_ok" and n.get("code") == "nat_fail":
                return False
            try:
                if float(c["res"]["tech"]["dur"]) < 0.85 * float(b["tech"]["dur"]):
                    return False
            except (KeyError, TypeError, ValueError):
                pass
            return True

        def ok(c):
            """候选是否**真的修好了原条的某一个缺陷**（按原条实际有哪些缺陷判，不按单一 t 判）。

            ★ c3_0839 同时有 nat_fail 与 emo_unreachable，按 t 归一成 "nat" 后会
              要求 nat_ok（候选只到 warn）⇒ 明明情绪从 未达 变 到位 也被判失败。
              所以这里按「原条缺陷集合」逐个看，修好任一项就算通过，再由 no_regress 兜底。
            """
            g = c["res"].get("gates") or {}
            e = c["res"].get("emo_res") or {}
            n = (c["res"].get("nat") or {})
            if g.get("tech") != "PASS":
                return False
            codes = {x["code"] for x in (b.get("reasons") or [])}
            fixed = False
            if "nat_fail" in codes and n.get("code") == "nat_ok":
                fixed = True
            if (e.get("tier") == "到位") and (be.get("tier") in (None, "未达", "勉强")):
                fixed = True
            if "intra_drift" in codes and g.get("intra") == "PASS":
                fixed = True
            return fixed and n.get("code") != "nat_fail"

        def score(c):
            g = c["res"].get("gates") or {}
            e = c["res"].get("emo_res") or {}
            n = (c["res"].get("nat") or {})
            s = 0
            s += 3 if e.get("tier") == "到位" else (1 if e.get("tier") == "勉强" else 0)
            s += 2 if g.get("intra") == "PASS" else 0
            s += 2 if n.get("code") == "nat_ok" else 0
            s += 1 if (c["res"].get("timbre_seq") or {}).get("level") == "ok" else 0
            return s

        good = [c for c in cs if ok(c) and no_regress(c)]
        desc = " ".join("s%s:%s/%s/nat%s" % (
            c["seed"],
            (c["res"].get("emo_res") or {}).get("tier"),
            (c["res"].get("gates") or {}).get("intra"),
            (c["res"].get("nat") or {}).get("code")) for c in cs)
        print("%-9s %-6s %-22s %s" % (
            rid, t,
            "%s/%s/nat%s" % (be.get("tier"), bg.get("intra"), (b.get("nat") or {}).get("code")),
            desc))
        if good:
            best = max(good, key=score)
            picks[rid] = dict(seed=best["seed"], score=score(best),
                              why=t, emo=(best["res"].get("emo_res") or {}).get("tier"),
                              nat=(best["res"].get("nat") or {}).get("code"),
                              intra=(best["res"].get("gates") or {}).get("intra"))
        else:
            keep.append(rid)

    print("\n可回填 %d 条 / 保留原文件 %d 条" % (len(picks), len(keep)))
    json.dump(dict(picks=picks, keep=keep), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("写出 %s" % OUT)


if __name__ == "__main__":
    main()
