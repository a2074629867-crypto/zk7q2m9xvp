# -*- coding: utf-8 -*-
"""选角杠杆验证：同一句文本 × 同格三个参考切片，看输出 effort 是否跟着走。

要回答的问题
------------
`_stim_cast.md` 的假设是「换参考切片就能把强度拉出来」。这是假设，不是事实。
本脚本做控制实验：**同一句台词、同一 seed、同一语速**，只换参考切片（low/mid/high），
量三个输出的 effort。

判据
----
· 输出 effort 与参考 effort 同向且陡度 ≥0.30 z ⇒ 选角杠杆成立，plan_v3 可以直接跑全量
· 同向但陡度 <0.30 ⇒ 克隆把强度衰减了，需在生成端补一个“强度增益”参数
· 不同向 ⇒ 克隆根本不传强度，选角方案作废，改走文本侧标签

为什么不拿三条不同台词测
--------------------
不同台词的音素/词长/重音天然不同，量出来的差异分不清是强度还是文本。
控制变量只能同文本。

用法
----
    G:/Python310/python.exe stim_pilot.py --cell "Thomas|激动反抗"
    G:/Python310/python.exe stim_pilot.py --cell "Charles|紧张" --n 3
"""
import os
import sys
import json
import math
import argparse
import subprocess
import time
import statistics as st

sys.path.insert(0, "G:/_setup")
import stim_tier as ST  # noqa: E402

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = "G:/_setup/_emo_refs_all.json"
CAST = "G:/_setup/_stim_cast.json"
PLAN = "G:/_setup/_castle_en_ch123_plan_v3.jsonl"
REFF = "G:/_setup/_stim_ref.json"
OUT = "G:/_setup/_stim_pilot_out"


def resolve(lib, voice):
    parts = voice.rsplit("_", 1)
    head, n = parts[0], int(parts[1])
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    if 1 <= n <= len(items):
        it = items[n - 1]
        if isinstance(it, dict):
            return it.get("path"), it.get("text") or ""
        return it, ""
    return None, None


def gen(text, ref, rtext, out, seed=42, threads=2):
    mt = max(120, min(900, int(len(text.split()) * 12 + 120)))
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", str(threads),
           "--voice-ref", ref, "--reference-text", rtext or "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % mt,
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=ACPP_DIR, timeout=900)
    except subprocess.TimeoutExpired:
        return False, 0.0, "timeout"
    ok = os.path.exists(out) and os.path.getsize(out) > 50000
    tail = ((r.stdout or "") + (r.stderr or ""))[-300:] if not ok else ""
    return ok, time.time() - t0, tail


def spearman3(x, y):
    rx = [sorted(x).index(v) + 1 for v in x]
    ry = [sorted(y).index(v) + 1 for v in y]
    n = len(x)
    return 1 - 6 * sum((a - b) ** 2 for a, b in zip(rx, ry)) / (n * (n * n - 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", required=True, help='如 "Thomas|激动反抗"')
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()

    cast = json.load(open(CAST, encoding="utf-8"))[a.cell]
    cast["pick"] = {int(k): v for k, v in cast["pick"].items()}   # JSON 把 int 键变成了 str
    lib = json.load(open(LIB, encoding="utf-8"))
    refs = json.load(open(REFF, encoding="utf-8"))
    plan = [json.loads(l) for l in open(PLAN, encoding="utf-8") if l.strip()]

    who = cast["who"]
    emo = cast["emo"]
    # 控制变量：取该格最长的一句，三个切片共用这一句
    rows = [r for r in plan
            if r.get("speaker") != "narrator" and r.get("emo") == emo
            and {"Edmund": "Thomas", "Other": "Helena"}.get(r["speaker"], r["speaker"]) == who]
    if not rows:
        print("该格在计划里没有台词")
        return
    row = max(rows, key=lambda r: len(r["text"].split()))
    text = row.get("text_src") or row["text"]
    print("格 %s | %s  台词 %s（%d 词）" % (who, emo, row["id"], len(text.split())))
    print("   %s\n" % text)

    os.makedirs(OUT, exist_ok=True)
    got = []
    for lv in range(1, a.n + 1):
        if lv not in cast["pick"]:
            continue
        voice = cast["pick"][lv]["voice"]
        ref, rtext = resolve(lib, voice)
        out = os.path.join(OUT, "%s_L%d.wav" % (row["id"], lv))
        if os.path.exists(out) and os.path.getsize(out) > 50000:
            print("[L%d] %-18s 已有，跳过" % (lv, voice), flush=True)
        else:
            ok, dt, tail = gen(text, ref, rtext, out, a.seed, a.threads)
            print("[L%d] %-18s %s %.1fs %s" % (lv, voice, "OK" if ok else "FAIL", dt, tail[:120]), flush=True)
            if not ok:
                continue
        f = ST.effort_feat(out)
        got.append(dict(lv=lv, voice=voice, ref_effort=cast["pick"][lv]["effort"],
                        out=f, path=out))

    if len(got) < 2:
        print("有效样本不足，无法判")
        return

    # effort 定标：沿用 stim_tier 的角色内定标（同一角色真人 refs）
    per = {k: ST.params_of([r for r in refs if r["who"] == who], k)
           for k in ("alpha", "f0_med", "hnr")}

    def effort(f):
        z, n = 0.0, 0
        for k, sign in (("alpha", -1), ("f0_med", 1), ("hnr", -1)):
            v = f.get(k)
            if v and per[k][0] is not None:
                z += sign * (v - per[k][0]) / per[k][1]
                n += 1
        return z / n if n else None

    print("\n| 档 | 参考切片 | 参考 effort | 输出 effort | f0中位 | alpha | HNR | 时长 |")
    print("|---|---|---|---|---|---|---|---|")
    for g in got:
        f = g["out"]
        g["eff"] = effort(f)
        print("| L%d | %s | %+0.2f | %+0.2f | %.0f | %s | %.1f | %.2fs |" % (
            g["lv"], g["voice"], g["ref_effort"], g["eff"], f["f0_med"],
            ("%.1f" % f["alpha"]) if f.get("alpha") is not None else "-",
            f["hnr"] or 0, f["dur"]))

    re_ = [g["ref_effort"] for g in got]
    oe = [g["eff"] for g in got]
    rho = spearman3(re_, oe)
    gap_ref = max(re_) - min(re_)
    gap_out = max(oe) - min(oe)
    print("\n参考跃度 %+.2f → 输出跃度 %+.2f（保留 %.0f%%），秩相关 %+.2f" % (
        gap_ref, gap_out, 100.0 * gap_out / gap_ref if gap_ref else 0, rho))
    if rho > 0 and gap_out >= 0.30:
        print("判定：✓ 选角杠杆成立 → plan_v3 可以跑全量")
    elif rho > 0:
        print("判定：△ 方向对但克隆衰减了强度（%.2f<0.30）→ 生成端需要强度增益参数" % gap_out)
    else:
        print("判定：✗ 克隆不传强度，选角方案作废 → 改走文本侧强度标签")

    json.dump(got, open(os.path.join(OUT, "_pilot_%s.json" % a.cell.replace("|", "_")),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
