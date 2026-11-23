# -*- coding: utf-8 -*-
"""旁白 716 条全量按「新标准」重生成（原速 1.00 / 125 句按标注 0.84）。

为什么必须重跑：现役 `_audio_ch123/out` 是旧 plan（rate 0.8）生成的，
整库被统一降速约 25%，用户听感直接否掉（「这速度不对呀，还是降速过的」）。

口径：
  - rate 来自 `_castle_en_ch123_plan_v2.jsonl`：591 句 1.00、125 句 0.84
  - 不加任何 stress 标签（`<rate>` 词级注入已实测无效，见 DECISIONS 11-21）
  - 不插停顿：停顿是生成后的独立一步（`mt_final_pause`），本脚本只出原速干声
  - trim 首尾静音 + 能量平均归一到 −24dBFS + 峰值 ≤0.891（由 regen_narr.py 做）

断点续跑：输出已存在且 >50KB 的句子直接 SKIP，随时中断、重跑同一条命令即可。

用法：
  G:/Python310/python.exe -u _regen_all_1123.py              # 全量
  G:/Python310/python.exe -u _regen_all_1123.py --limit 5     # 冒烟
  G:/Python310/python.exe -u _regen_all_1123.py --ids c1_0001,c1_0003
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

ROOT = r"G:/_setup"
PY = r"G:/Python310/python.exe"
REGEN = os.path.join(ROOT, "regen_narr.py")
PLAN = os.path.join(ROOT, "_castle_en_ch123_plan_v2.jsonl")
IDS = os.path.join(ROOT, "_narr_ids716.json")
OUT = os.path.join(ROOT, "_regen_1123")
LOG = os.path.join(ROOT, "_regen_1123.jsonl")


def load_ids():
    return json.load(io.open(IDS, encoding="utf-8"))


def load_plan():
    p = {}
    for l in io.open(PLAN, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            p[r["id"]] = r
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    ids = [x.strip() for x in a.ids.split(",") if x.strip()] or load_ids()
    if a.limit:
        ids = ids[:a.limit]
    plan = load_plan()
    os.makedirs(a.out, exist_ok=True)

    todo = [i for i in ids
            if not (os.path.exists(os.path.join(a.out, i + ".wav"))
                    and os.path.getsize(os.path.join(a.out, i + ".wav")) > 50000)]
    print("总 %d 条 / 已完成 %d / 待跑 %d" % (len(ids), len(ids) - len(todo), len(todo)),
          flush=True)
    if not todo:
        print("没有待跑", flush=True)
        return

    t0 = time.time()
    done = 0
    fail = 0
    for n, sid in enumerate(todo, 1):
        rate = float((plan.get(sid) or {}).get("rate") or 1.0)
        ts = time.time()
        try:
            r = subprocess.run(
                [PY, "-u", REGEN, "--ids", sid, "--plan", PLAN, "--out", a.out],
                cwd=ROOT, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=1800)
            out = (r.stdout or "").strip().splitlines()
            tail = out[-1] if out else ""
            ok = r.returncode == 0 and os.path.exists(
                os.path.join(a.out, sid + ".wav")) and os.path.getsize(
                os.path.join(a.out, sid + ".wav")) > 50000
            err = "" if ok else ((r.stderr or "")[-300:] + " | " + (r.stdout or "")[-300:])
        except subprocess.TimeoutExpired:
            ok, tail, err = False, "TIMEOUT", "timeout 1800s"
        dt = time.time() - ts
        done += 1 if ok else 0
        fail += 0 if ok else 1

        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": sid, "rate": rate, "ok": ok, "sec": round(dt, 1),
                                "tail": tail, "err": err}, ensure_ascii=False) + "\n")

        el = time.time() - t0
        eta = el / n * (len(todo) - n) / 3600.0
        print("[%4d/%4d] %-9s rate=%.2f %5.1fs %s  已用 %.1fh  ETA %.1fh"
              % (n, len(todo), sid, rate, dt, "OK" if ok else "FAIL " + err[:120],
                 el / 3600.0, eta), flush=True)

    print("完成 OK %d / 失败 %d / 用时 %.2fh" % (done, fail, (time.time() - t0) / 3600.0),
          flush=True)


if __name__ == "__main__":
    sys.exit(main())
