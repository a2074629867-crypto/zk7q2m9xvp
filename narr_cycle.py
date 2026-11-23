# -*- coding: utf-8 -*-
"""narr_cycle.py -- 把物理闸焊进回环（闸 -> FIX 清单 -> 重生成 -> 复闸 -> state）。

口径（2026-11-20 用户定）：
  - LLM 标注结果直接进生产，不再测标注；
  - 生成后的闸必须在回环里，FIX>0 就自动回重生成，循环到 FIX=0；
  - 只跑与本次改动相关的闸，不做全量回归。

用法：
  # 只看清单，不动音频（默认）
  G:/Python310/python.exe narr_cycle.py --gate G:/_setup/_narr_phys_fix3.json

  # 真回环：重生成 FIX 条目，复闸，最多 3 轮，回填并备份
  G:/Python310/python.exe narr_cycle.py --gate G:/_setup/_narr_phys_now.json --apply

  # 只写 state 指针，不重生成
  G:/Python310/python.exe narr_cycle.py --gate G:/_setup/_narr_phys_fix3.json --state-only
"""
import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time

PY = r"G:/Python310/python.exe"
HERE = r"G:/_setup"
GATE = os.path.join(HERE, "narr_gate_phys.py")
REGEN = os.path.join(HERE, "regen_narr.py")
PLAN = os.path.join(HERE, "_castle_en_ch123_plan_v2.jsonl")
REGEN_OUT = os.path.join(HERE, "_narr_regen_1120")
AUDIO = os.path.join(HERE, "_audio_ch123", "out")
IDS = os.path.join(HERE, "_narr_ids716.json")
RATE = os.path.join(HERE, "rate_narr_sent_v1.json")
STATE = os.path.join(HERE, "_narr_state.json")

ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_gate(p):
    g = json.load(open(p, encoding="utf-8"))
    if isinstance(g, dict):
        g = g.get("items") or g.get("rows") or list(g.values())
    return g


def pct(v, q):
    v = sorted(v)
    if not v:
        return None
    k = max(0, min(len(v) - 1, int(round((len(v) - 1) * q))))
    return v[k]


def rate_policy():
    try:
        r = json.load(open(RATE, encoding="utf-8"))
        rates = r.get("rates") or {}
        slow = [k for k, v in rates.items() if float(v) < 0.99]
        return {
            "table": os.path.basename(RATE),
            "base": float(r.get("_meta", {}).get("base_rate", 1.0)),
            "slow": float(r.get("_meta", {}).get("slow_rate", 0.0)),
            "n": len(rates),
            "slow_n": len(slow),
        }
    except Exception as e:
        return {"error": str(e)}


def summarize(gate_path, rows):
    wpm = [r["wpm"] for r in rows if r.get("wpm")]
    lvl = [r["lvl"] for r in rows if r.get("lvl") is not None]
    pk = [r["peak"] for r in rows if r.get("peak") is not None]
    vc = {}
    for r in rows:
        vc[r.get("verdict", "?")] = vc.get(r.get("verdict", "?"), 0) + 1
    return {
        "gate": os.path.basename(gate_path),
        "gate_md5": md5(gate_path),
        "n": len(rows),
        "verdict": vc,
        "wpm_p50": pct(wpm, 0.5),
        "lvl_median": round(statistics.median(lvl), 2) if lvl else None,
        "peak_max": round(max(pk), 3) if pk else None,
    }


def write_state(gate_path, rows, rounds, applied):
    st = {
        "build_id": time.strftime("cycle_%Y%m%d_%H%M"),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ids_file": os.path.basename(IDS),
        "n_ids": len(json.load(open(IDS, encoding="utf-8"))),
        "audio_dir": AUDIO,
        "rate_policy": rate_policy(),
        "pause_policy": {"inner": 0.51, "bound": 1.135, "clause": 1.695,
                         "table": "pause_llm_narr_v3.json", "who": "narrator"},
        "applied": applied,
        "rounds": rounds,
        "final": summarize(gate_path, rows),
    }
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return st


def run_gate(out):
    cmd = [PY, GATE, "--out", out]
    r = subprocess.run(cmd, cwd=HERE, env=ENV, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-800:])
        print(r.stderr[-800:])
        raise SystemExit("gate failed rc=%s" % r.returncode)
    return load_gate(out)


def regen(ids):
    cmd = [PY, REGEN, "--ids", ",".join(ids), "--plan", PLAN, "--out", REGEN_OUT]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=HERE, env=ENV, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    ok = []
    for k in ids:
        p = os.path.join(REGEN_OUT, k + ".wav")
        if os.path.exists(p) and os.path.getmtime(p) >= t0 - 2:
            ok.append(k)
    if r.returncode != 0 and not ok:
        print(r.stdout[-800:])
        print(r.stderr[-800:])
    return ok, (r.stdout or "") + (r.stderr or "")


def apply_back(ids):
    bak = os.path.join(HERE, "_bak_cycle_" + time.strftime("%m%d_%H%M"))
    os.makedirs(bak, exist_ok=True)
    done = []
    for k in ids:
        src = os.path.join(REGEN_OUT, k + ".wav")
        dst = os.path.join(AUDIO, k + ".wav")
        if not os.path.exists(src):
            continue
        if os.path.exists(dst):
            shutil.copy2(dst, os.path.join(bak, k + ".wav"))
        shutil.copy2(src, dst)
        done.append(k)
    return bak, done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", default=os.path.join(HERE, "_narr_phys_now.json"))
    ap.add_argument("--max-round", type=int, default=3)
    ap.add_argument("--apply", action="store_true", help="重生成后回填 out（先备份）")
    ap.add_argument("--state-only", action="store_true")
    a = ap.parse_args()

    rows = load_gate(a.gate)
    vc = summarize(a.gate, rows)["verdict"]
    print("gate=%s  n=%d  %s" % (os.path.basename(a.gate), len(rows), vc))

    if a.state_only:
        st = write_state(a.gate, rows, [], False)
        print("state -> %s  build_id=%s" % (STATE, st["build_id"]))
        return

    rounds = []
    for rd in range(1, a.max_round + 1):
        fix = [r["id"] for r in rows if r.get("verdict") == "FIX"]
        print("[round %d] FIX=%d %s" % (rd, len(fix), fix[:12]))
        rounds.append({"round": rd, "fix_before": fix, "fix_n": len(fix)})
        if not fix:
            break
        print("[round %d] regen ..." % rd)
        ok, log = regen(fix)
        rounds[-1]["regen_ok"] = ok
        rounds[-1]["regen_fail"] = [x for x in fix if x not in ok]
        if not ok:
            print("regen 全失败，停在 round %d" % rd)
            break
        out = os.path.join(HERE, "_narr_phys_cycle%d.json" % rd)
        print("[round %d] 复闸 ..." % rd)
        rows = run_gate(out)
        rounds[-1]["gate_after"] = summarize(out, rows)["verdict"]

    fix = [r["id"] for r in rows if r.get("verdict") == "FIX"]
    bak, applied = None, []
    if a.apply and fix:
        # 只回填「重生成后已不是 FIX」的条目；仍 FIX 的不进 out
        bad = set(fix)
        cand = sorted(set(x for r in rounds for x in r.get("regen_ok", [])) - bad)
        bak, applied = apply_back(cand)
        print("回填 %d 条，备份 %s" % (len(applied), bak))

    st = write_state(a.gate, rows, rounds, bool(applied))
    print("final FIX=%d  state -> %s  build_id=%s" % (len(fix), STATE, st["build_id"]))
    print(json.dumps(st["final"], ensure_ascii=False))
    if fix:
        print("仍未过: %s" % fix)


if __name__ == "__main__":
    main()
