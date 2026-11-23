# -*- coding: utf-8 -*-
"""守望器：等全量重生成跑完，自动接上回环的第 3、4 步。

为什么要守望器：全量 716 条要跑十几小时，跑完时不一定有人在。
用户要求「测试链路回环再重新生成，这个链路也不能停」⇒ 不能停在「跑完了」等指令。

做三件事，每件都可重入：
  1) 轮询 `_regen_1123/` 直到 716 条齐（或连续 40 分钟无新增 ⇒ 判定卡死，直接进下一步）
  2) 对新库做 ASR + 重音再测（`_loop_1123.py --stage asr` / `test --tag after`）
  3) 只对仍失败的强调副词抽 seed 重出（`--stage plan` / `repick --limit 40`）

不碰现役音频：第 4 步的产物写 `_loop_pick/`，不覆盖 `_regen_1123/`，也不覆盖 `_audio_ch123/out`。

用法（后台）：
  G:/Python310/python.exe -u _chain_1123.py
"""
import glob
import io
import json
import os
import subprocess
import time

ROOT = r"G:/_setup"
PY = r"G:/Python310/python.exe"
DIR = os.path.join(ROOT, "_regen_1123")
TOTAL = 716
POLL = 300
STALL_MIN = 40


def count():
    return len([p for p in glob.glob(os.path.join(DIR, "*.wav"))
                if not os.path.basename(p).startswith("_raw_")])


def sh(args, timeout=14400):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    for ln in tail[-4:]:
        print("    " + ln, flush=True)
    return r.returncode


def main():
    print("守望开始：目标 %d 条" % TOTAL, flush=True)
    last, last_change = -1, time.time()
    while True:
        n = count()
        if n != last:
            print("[%s] 已完成 %d / %d" % (time.strftime("%H:%M"), n, TOTAL), flush=True)
            last, last_change = n, time.time()
        if n >= TOTAL:
            print("全量到齐 %d 条，进入回环" % n, flush=True)
            break
        if (time.time() - last_change) / 60.0 >= STALL_MIN:
            print("!! %d 分钟无新增（卡在 %d 条）⇒ 判定卡死，按现有 %d 条继续"
                  % (STALL_MIN, n, n), flush=True)
            break
        time.sleep(POLL)

    print("\n=== 第 3 步：ASR ===", flush=True)
    sh([PY, "-u", "_loop_1123.py", "--stage", "asr"], timeout=21600)
    print("\n=== 第 3 步：再测 ===", flush=True)
    sh([PY, "-u", "_loop_1123.py", "--stage", "test", "--tag", "after"], timeout=7200)
    print("\n=== 第 4 步：列目标 ===", flush=True)
    sh([PY, "-u", "_loop_1123.py", "--stage", "plan", "--tag", "after", "--limit", "40"],
       timeout=600)
    print("\n=== 第 4 步：抽 seed 重出 ===", flush=True)
    sh([PY, "-u", "_loop_1123.py", "--stage", "repick", "--limit", "40",
        "--seeds", "43,44,45"], timeout=36000)
    print("\n回环走完。产物：_stress_adv_after.json / _loop_targets.json / _loop_pick_report.json",
          flush=True)


if __name__ == "__main__":
    main()
