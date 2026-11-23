# -*- coding: utf-8 -*-
"""等第 4 步（抽 seed）跑完，自动接三步收尾。不需要人在场。

顺序（顺序不能换）：
  1) 等 repick 出齐 120 个 take（或日志出现「采纳」行）
  2) `_fix_missing10.py`   —— 补 10 句带弯引号的历史缺口（重生成 + 插停顿 + 重建 726 句）
  3) `_apply_picks.py --apply` —— 把 _loop_pick/ 的择优结果写回，并补 ASR / 停顿 / 页面

看门狗：连续 40 分钟 take 数不变 ⇒ 判定卡死，打印现场后退出（不杀进程，留证据）。

用法：
    G:/Python310/python.exe -u _chain_local_1124.py
"""
import io
import json
import os
import subprocess
import sys
import time

ROOT = r"G:/_setup"
PY = r"G:/Python310/python.exe"
TAKES = os.path.join(ROOT, "_loop_takes")
LOG = os.path.join(ROOT, "_loop_repick.log")
CHAIN_LOG = os.path.join(ROOT, "_chain_local_1124.log")
WANT = 120
STALL_SEC = 40 * 60
MAX_WAIT = 8 * 3600


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with io.open(CHAIN_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def n_takes():
    n = 0
    if not os.path.isdir(TAKES):
        return 0
    for d in os.listdir(TAKES):
        p = os.path.join(TAKES, d)
        if not os.path.isdir(p):
            continue
        for f in os.listdir(p):
            if f.endswith(".wav") and not f.startswith("_raw_"):
                n += 1
    return n


def log_tail(n=3):
    try:
        with io.open(LOG, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:]).strip()
    except OSError:
        return "(无日志)"


def run(step, cmd, timeout):
    log("▶ %s" % step)
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        for ln in out.splitlines()[-6:]:
            log("    " + ln)
        log("✔ %s  rc=%s  %.0fs" % (step, r.returncode, time.time() - t0))
        return r.returncode
    except subprocess.TimeoutExpired:
        log("✘ %s 超时 %ds" % (step, timeout))
        return -1


def main():
    log("守望器启动，等 repick 出齐 %d 个 take" % WANT)
    t_start = time.time()
    last_n, last_change = n_takes(), time.time()

    while True:
        n = n_takes()
        if n != last_n:
            last_n, last_change = n, time.time()
            log("take %d/%d" % (n, WANT))
        if n >= WANT:
            log("take 已齐 %d，进入收尾" % n)
            break
        if "采纳" in log_tail(20):
            log("日志出现「采纳」行，repick 已结束（take=%d）" % n)
            break
        if time.time() - last_change > STALL_SEC:
            log("✘ 卡死：%d 分钟无新增 take（当前 %d/%d）" % (STALL_SEC // 60, n, WANT))
            log("   日志尾：%s" % log_tail(3).replace("\n", " | "))
            return 1
        if time.time() - t_start > MAX_WAIT:
            log("✘ 总等待超过 %dh，退出（take=%d）" % (MAX_WAIT // 3600, n))
            return 1
        time.sleep(300)

    # ---- 收尾 ----
    run("补 10 句历史缺口", [PY, "-u", "_fix_missing10.py"], 3 * 3600)
    run("采纳择优结果并补齐下游", [PY, "-u", "_apply_picks.py", "--apply"], 3 * 3600)

    rep = os.path.join(ROOT, "_loop_pick_report.json")
    if os.path.exists(rep):
        try:
            d = json.load(io.open(rep, encoding="utf-8"))
            log("采纳报告：%s" % json.dumps(d, ensure_ascii=False)[:400])
        except Exception as e:  # noqa: BLE001
            log("读采纳报告失败 %s" % e)
    log("全部收尾完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
