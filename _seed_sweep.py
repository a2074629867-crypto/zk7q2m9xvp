# -*- coding: utf-8 -*-
"""_seed_sweep.py —— 多 seed 择优（不加标签，纯赌生成随机性）

针对两类「差一点点」的条目：
  A) `_hard_cap_list.json` 里 **紧张 未达** 20 条（gap 0.0023~0.083；HARD_CAP 只是经验值
     不是数学上限 —— 已有 8 条实测超过它）
  B) 当前 G/H 桶 11 条（nat_fail 3 / intra_drift 5 / scs_outlier 3，其中 c2_0371 是缺参考档，seed 救不了）

不做什么：
  - 不加 `<emo>` 标签（那是 `_emo_retag.py` 的活，且对紧张实测无效）
  - 不换参考档（换档会翻音色，`Thomas_begging_1` 的教训）
  - 不用现役 seed=42 重跑（同文本同参考同 seed 是确定性输出，波形相关 1.000000）

输出 `_sweep/cand/<id>__s<seed>.wav`，日志 `_sweep/gen.jsonl`（已存在且 >50KB 就跳过，可断点续跑）

用法：
  G:/Python310/python.exe _seed_sweep.py            # 全跑
  G:/Python310/python.exe _seed_sweep.py --limit 2  # 试跑
"""
import argparse
import json
import os
import subprocess
import sys
import time

import soundfile as sf

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = "G:/_setup/_emo_refs_all.json"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
HARD = "G:/_setup/_hard_cap_list.json"
BUCK = "G:/_setup/_dlg_buckets_v32.json"
AUD = "G:/_setup/_audio_ch123/out"
CAND = "G:/_setup/_sweep/cand"
LOG = "G:/_setup/_sweep/gen.jsonl"


def mtok(words):
    return max(120, min(900, int(words * 12 + 120)))


def resolve(lib, voice):
    parts = voice.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None, None
    head, n = parts[0], int(parts[1])
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    if 1 <= n <= len(items):
        it = items[n - 1]
        if isinstance(it, dict):
            return it.get("path"), it.get("text") or ""
        return it, ""
    return None, None


def targets():
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(PLAN, encoding="utf-8") if l.strip()}
    hard = json.load(open(HARD, encoding="utf-8"))
    buck = json.load(open(BUCK, encoding="utf-8"))

    out, why = [], {}
    for x in hard:
        if x["emo"] == "紧张" and x["tier"] == "未达":
            out.append(x["id"])
            why.setdefault(x["id"], []).append("emo_gap=%+.4f" % (x["p10"] - x["val"]))
    for k in ("G", "H"):
        for i in buck.get(k) or []:
            if i not in out:
                out.append(i)
            why.setdefault(i, []).append("bucket=" + k)
    items = []
    for rid in out:
        p = plan.get(rid)
        if not p:
            continue
        head, _, n = (p.get("voice") or "").rpartition("_")
        if not head:
            continue
        items.append(dict(id=rid, voice=p["voice"], who=p["who"], emo=p["emo"],
                          text=p.get("text_src") or p["text"], why=why[rid]))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="7,11")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--ids", default="", help="直接给 id 列表（逗号分隔），覆盖 targets()")
    ap.add_argument("--cand-dir", default="",
                    help="候选输出目录（默认 _sweep/cand）。换参考返工时必须换目录，"
                         "否则同名 __sN.wav 会被当成「已生成」跳过 —— 那是别的参考生成的")
    ap.add_argument("--ref-map", default="",
                    help="id→参考的强制映射 JSON（{id:{path,text}}）；用于「该情绪档存在但生成时用错档」的返工")
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]
    if a.ref_map:
        globals()["_REF_FORCE"] = json.load(open(a.ref_map, encoding="utf-8"))
    global CAND
    if a.cand_dir:
        CAND = a.cand_dir
    if a.ids:
        _want = [x.strip() for x in a.ids.split(",") if x.strip()]
        _plan = {json.loads(l)["id"]: json.loads(l)
                 for l in open(PLAN, encoding="utf-8") if l.strip()}
        _it = []
        for rid in _want:
            pp = _plan.get(rid)
            if not pp:
                print("  跳过（不在 plan）", rid)
                continue
            _it.append(dict(id=rid, voice=pp["voice"], who=pp["who"], emo=pp["emo"],
                            text=pp.get("text_src") or pp["text"], why=["manual"]))
        globals()["_FORCE"] = _it

    os.makedirs(CAND, exist_ok=True)
    lib = json.load(open(LIB, encoding="utf-8"))
    items = globals().get("_FORCE") or targets()
    todo = [(it, s) for it in items for s in seeds]
    if a.limit:
        todo = todo[:a.limit]
    print("目标 %d 条 × %d seed = %d 个候选" % (len(items), len(seeds), len(todo)), flush=True)

    ok = skip = fail = 0
    t0all = time.time()
    with open(LOG, "a", encoding="utf-8", newline="\n") as log:
        for k, (it, seed) in enumerate(todo, 1):
            rid = it["id"]
            out = os.path.join(CAND, "%s__s%d.wav" % (rid, seed))
            if os.path.exists(out) and os.path.getsize(out) > 50000:
                skip += 1
                continue
            _f = globals().get("_REF_FORCE", {}).get(rid)
            if _f:
                ref, rtext = _f["path"], _f.get("text") or ""
            else:
                ref, rtext = resolve(lib, it["voice"])
            if not ref or not os.path.exists(ref):
                print("[%d/%d] %s 参考解析失败 %s" % (k, len(todo), rid, it["voice"]), flush=True)
                fail += 1
                continue
            text = it["text"]
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", str(a.threads),
                   "--voice-ref", ref, "--reference-text", rtext or "",
                   "--text", text, "--seed", str(seed), "--out", out,
                   "--request-option", "max_tokens=%d" % mtok(len(text.split())),
                   "--session-option", "dots_tts.mem_saver=true", "--metrics"]
            base = os.path.join(AUD, rid + ".wav")
            d_old = sf.info(base).duration if os.path.exists(base) else 0.0
            t0 = time.time()
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   cwd=ACPP_DIR, timeout=1200)
                outtxt = (r.stdout or "") + (r.stderr or "")
                rc = r.returncode
            except subprocess.TimeoutExpired:
                print("[%d/%d] %s s%d 超时" % (k, len(todo), rid, seed), flush=True)
                fail += 1
                continue
            dt = time.time() - t0
            dur = None
            for line in outtxt.splitlines():
                if "audio_duration_ms=" in line:
                    try:
                        dur = float(line.split("=")[1]) / 1000.0
                    except ValueError:
                        pass
            good = os.path.exists(out) and os.path.getsize(out) > 50000
            if good and d_old and dur and dur < 0.6 * d_old:
                good = False
                print("[%d/%d] %s s%d 残片 %.2fs < 0.6×%.2fs 丢弃"
                      % (k, len(todo), rid, seed, dur, d_old), flush=True)
                try:
                    os.remove(out)
                except OSError:
                    pass
            log.write(json.dumps(dict(id=rid, seed=seed, voice=it["voice"], ok=good, rc=rc,
                                      ref=os.path.basename(str(ref)), ref_path=ref,
                                      dur=dur, sec=round(dt, 1),
                                      size=os.path.getsize(out) if os.path.exists(out) else 0),
                                 ensure_ascii=False) + "\n")
            log.flush()
            if good:
                ok += 1
            else:
                fail += 1
            print("[%d/%d] %s %s s%d %s %.1fs"
                  % (k, len(todo), rid, it["voice"], seed, "OK" if good else "FAIL", dt), flush=True)
    print("完成 OK %d / 跳过 %d / 失败 %d，用时 %.0fs"
          % (ok, skip, fail, time.time() - t0all))


if __name__ == "__main__":
    main()
