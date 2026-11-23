#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GPU 时段守门：等本地 RX580 空出来再跑重生成队列。

背景（2026-11-24 02:4x）：另一个 Agent 在跑旁白回环
  _loop_1123.py --stage repick / _chain_local_1124.py / regen_narr.py
audiocpp_cli.exe 常驻占卡（3.3GB）。用户要求 05:00 之后再动 GPU，
占用没释放就每次顺延 30 分钟。

用法：
  python _gpu_slot.py --check        # 只探测：空闲 exit 0 / 占用 exit 3
  python _gpu_slot.py --run          # 占用则拒跑；空闲才跑 66 条
  python _gpu_slot.py --run --force  # 用户明确批准时忽略占用

产出：_sweep/notxt66/*.wav、_align_notxt66.json、_gpu_slot_report.json
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)          # 嵌入式 Python 不会自动加，见 MEMORY 铁律

import _paths as P

PY = sys.executable
PY_CMD = "G:/Python310/python.exe"

# 其他 Agent 的驱动脚本名（出现在命令行里就算占用）
OTHER_DRIVERS = ("_loop_1123", "_chain_local_1124", "regen_narr")
# 任何会吃显存的自家脚本也算占用
OWN_GPU = ("_regen9.py", "_regen_short.py", "_campaign9.py")

PS_PROBE = (
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='audiocpp_cli.exe'\" "
    "| Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
)


def probe():
    """返回 (busy: bool, rows: list[dict], reasons: list[str])"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", PS_PROBE],
                           capture_output=True, text=True, timeout=60)
        raw = (r.stdout or "").strip()
    except Exception as e:                                  # noqa: BLE001
        return True, [], ["探测失败（%s）——保守判为占用" % e]

    if not raw or raw in ("null", "[]"):
        return False, [], []

    try:
        data = json.loads(raw)
    except Exception:                                       # noqa: BLE001
        return True, [], ["输出无法解析——保守判为占用"]
    if isinstance(data, dict):
        data = [data]

    rows, reasons = [], []
    for it in data:
        pid = it.get("ProcessId")
        name = (it.get("Name") or "").strip()
        cmd = (it.get("CommandLine") or "").strip()
        rows.append({"pid": pid, "name": name, "cmd": cmd[:180]})
        if name.lower() == "audiocpp_cli.exe":
            reasons.append("audiocpp_cli.exe 在跑（pid %s）" % pid)
        low = cmd.lower()
        for k in OTHER_DRIVERS:
            if k in low:
                reasons.append("%s 在跑（pid %s）" % (k, pid))
        for k in OWN_GPU:
            if k in low and "--ids" in low:
                reasons.append("%s 在跑（pid %s）" % (k, pid))
    # 去重
    seen, uniq = set(), []
    for x in reasons:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return bool(uniq), rows, uniq


def load_plan():
    p = os.path.join(P.ROOT, "_dlg_plan_v2.jsonl")
    out = {}
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                d = json.loads(line)
                out[d["id"]] = d
    return out


def wcount(s):
    import re
    return len(re.findall(r"[A-Za-z']+", s or ""))


def dur_of(p):
    try:
        import soundfile as sf
        return sf.info(p).duration
    except Exception:                                       # noqa: BLE001
        return None


def run(args):
    busy, rows, reasons = probe()
    print("=== GPU 探测 %s ===" % ("占用" if busy else "空闲"))
    for r in rows:
        print("  pid %-6s %-18s %s" % (r["pid"], r["name"], r["cmd"][:110]))
    if busy:
        for x in reasons:
            print("  ! " + x)

    if busy and not args.force:
        print("\n[SKIP] GPU 被占用，本次不跑。请顺延 30 分钟。")
        return 3

    ids = [x for x in open(os.path.join(P.ROOT, "_notxt_ids.txt")).read().split(",") if x.strip()]
    od = os.path.join(P.ROOT, "_sweep", "notxt66")
    os.makedirs(od, exist_ok=True)
    print("\n=== 重生成 %d 条（--no-ref-text，seed 42）→ %s ===" % (len(ids), od))
    cmd = [PY, "-u", "_regen9.py", "--ids", ",".join(ids), "--seeds", str(args.seed),
           "--no-ref-text", "--out", od]
    r = subprocess.run(cmd, cwd=P.ROOT)
    print("regen rc=%d" % r.returncode)

    wavs = sorted(f for f in os.listdir(od) if f.endswith(".wav"))
    print("产出 %d / %d" % (len(wavs), len(ids)))

    print("\n=== 吞字/覆盖率检测 ===")
    aj = os.path.join(P.ROOT, "_align_notxt66.json")
    cmd = [PY, "-u", "_align_gate.py", "--dir", od, "--plan-text", "--out", aj]
    subprocess.run(cmd, cwd=P.ROOT)

    report = {"when": None, "n_ids": len(ids), "n_wav": len(wavs), "rows": []}
    try:
        import datetime
        report["when"] = datetime.datetime.now().isoformat(timespec="seconds")
    except Exception:                                       # noqa: BLE001
        pass

    if os.path.exists(aj):
        new = {x["rid"]: x for x in json.load(open(aj, encoding="utf-8"))}
        old = {x["id"]: x for x in json.load(open(os.path.join(P.ROOT, "_align_deliver.json"),
                                                 encoding="utf-8"))}
        plan = load_plan()
        print("\n%-9s %-8s %-6s | %6s %5s | %6s %5s | %7s" %
              ("id", "who", "emo", "旧dur", "旧cov", "新dur", "新cov", "wpmΔ"))
        for rid in ids:
            n = new.get(rid)
            o = old.get(rid)
            pl = plan.get(rid, {})
            if not n:
                continue
            ow = (o or {}).get("dur") or 0
            nw = n.get("dur") or 0
            wc = wcount(pl.get("text"))
            dwpm = None
            if ow > 0.3 and nw > 0.3 and wc:
                dwpm = (wc / nw * 60) / (wc / ow * 60) - 1
            print("%-9s %-8s %-6s | %6.2f %5s | %6.2f %5s | %+6.0f%%" % (
                rid, pl.get("who", "?"), pl.get("emo", "?"),
                ow, (o or {}).get("w2v_cov"), nw, n.get("w2v_cov"),
                (dwpm or 0) * 100))
            report["rows"].append({
                "id": rid, "who": pl.get("who"), "emo": pl.get("emo"),
                "old_dur": round(ow, 3), "new_dur": round(nw, 3),
                "old_cov": (o or {}).get("w2v_cov"), "new_cov": n.get("w2v_cov"),
                "wpm_delta": None if dwpm is None else round(dwpm, 3),
                "new_text": n.get("w2v_text", "")[:160],
            })
        covs = [r["new_cov"] for r in report["rows"] if r.get("new_cov") is not None]
        if covs:
            import statistics
            print("\n新覆盖率 中位 %.3f  <0.9 共 %d 条" % (statistics.median(covs),
                                                     sum(1 for c in covs if c < 0.9)))
            report["median_cov"] = round(statistics.median(covs), 3)
            report["cov_lt_09"] = sum(1 for c in covs if c < 0.9)

    jp = os.path.join(P.ROOT, "_gpu_slot_report.json")
    json.dump(report, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n报告：%s" % jp)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    if a.check or not a.run:
        busy, rows, reasons = probe()
        print("GPU %s" % ("占用" if busy else "空闲"))
        for r in rows:
            print("  pid %-6s %-18s %s" % (r["pid"], r["name"], r["cmd"][:110]))
        for x in reasons:
            print("  ! " + x)
        return 3 if busy else 0
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
