# -*- coding: utf-8 -*-
"""回环收尾：把 `_loop_pick/` 里采纳的 take 正式写回，并补齐下游。

为什么不能只 copy 就完事：换了一条音频，它的词级时间戳、三档停顿、试听页全部作废，
必须按顺序补三件事，否则页面上的停顿时长与文字对不上。

顺序（每步都可单独跑）：
  1) apply  : 备份原 take → 覆盖 `_regen_1123/`
  2) asr    : 只对改动的 id 重跑 ASR，并更新 `_wl_regen1123.json`
  3) pause  : 只对改动的 id 重插三档停顿（`_run_pause_1123.py --only`）
  4) page   : 重建 `_narr_full_listen.html`

用法：
  G:/Python310/python.exe -u _apply_picks.py            # 预演（只打印）
  G:/Python310/python.exe -u _apply_picks.py --apply    # 真做
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = r"G:/_setup"
PY = r"G:/Python310/python.exe"
ASR_PY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")
MAIN = os.path.join(ROOT, "_regen_1123")
PICK = os.path.join(ROOT, "_loop_pick")
BAK = os.path.join(ROOT, "_picks_old")
WL = os.path.join(ROOT, "_wl_regen1123.json")


def run(cmd, timeout=7200):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    for ln in ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-3:]:
        print("    " + ln, flush=True)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=os.path.join(ROOT, "_loop_pick_report.json"))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.report):
        raise SystemExit("没有 %s —— 第 4 步还没跑完" % a.report)
    rep = json.load(io.open(a.report, encoding="utf-8"))
    ids = [r["sid"] for r in rep if r.get("adopt")]
    if not ids:
        print("报告里没有可采纳项"); return
    print("采纳 %d 句：%s" % (len(ids), ", ".join(ids)), flush=True)

    for r in rep:
        if r.get("adopt"):
            print("  %-9s %-16s 现 %+.2f → 最好 %+.2f (seed %s)"
                  % (r["sid"], "/".join(r.get("words") or []),
                     r.get("cur_z") or 0, r.get("best_z") or 0, r.get("best_seed")),
                  flush=True)

    if not a.apply:
        print("\n预演结束。加 --apply 才会真正写回。")
        return

    # 1) 备份 + 覆盖
    os.makedirs(BAK, exist_ok=True)
    done = []
    for sid in ids:
        src = os.path.join(PICK, sid + ".wav")
        if not os.path.exists(src):
            print("  跳过 %s（_loop_pick 里没有）" % sid); continue
        dst = os.path.join(MAIN, sid + ".wav")
        if os.path.exists(dst) and not os.path.exists(os.path.join(BAK, sid + ".wav")):
            shutil.copy2(dst, os.path.join(BAK, sid + ".wav"))
        shutil.copy2(src, dst)
        done.append(sid)
    print("写回 %d 条，原版备份在 %s" % (len(done), BAK), flush=True)

    # 2) 只对这些 id 重跑 ASR 并合并
    #    ★ 必须先删掉旧条目：`_wl_asr.py --append` 会跳过已存在的路径，
    #      不删的话换过的音频还挂着旧时间戳，rel_z 与停顿位置全错。
    wl = json.load(io.open(WL, encoding="utf-8")) if os.path.exists(WL) else {}
    for s in done:
        wl.pop("G:/_setup/_regen_1123/%s.wav" % s, None)
    json.dump(wl, io.open(WL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已清掉 %d 条旧时间戳" % len(done), flush=True)

    lp = os.path.join(ROOT, "_apply_asr_list.txt")
    io.open(lp, "w", encoding="utf-8").write(
        "\n".join(os.path.join(MAIN, s + ".wav").replace("\\", "/") for s in done))
    print("重跑 ASR %d 条" % len(done), flush=True)
    run([ASR_PY, "_wl_asr.py", "--list", lp, "--out", WL, "--append"], timeout=3600)
    wl = json.load(io.open(WL, encoding="utf-8"))
    for s in done:
        k = "G:/_setup/_regen_1123/%s.wav" % s
        if k not in wl:
            print("  !! %s 的 ASR 没写进 %s，需手工补" % (s, WL))

    # 3) 只对这些 id 重插停顿
    print("重插停顿 %d 条" % len(done), flush=True)
    run([PY, "-u", "_run_pause_1123.py", "--only", ",".join(done)], timeout=3600)

    # 4) 重建页面
    print("重建试听页", flush=True)
    run([PY, "-u", "_build_narr_ch2.py", "--chapter", "all",
         "--new", "_regen_1123_paused", "--old", "_audio_ch123/out",
         "--rates", "_rate_narr_v2.json", "--only716",
         "--out", "G:/_setup/_narr_full_listen.html",
         "--title", "旁白全集 716 句 · 新标准速度试听"], timeout=1800)
    print("\n收尾完成：写回 %d 条 → ASR → 停顿 → 页面" % len(done), flush=True)


if __name__ == "__main__":
    main()
