# -*- coding: utf-8 -*-
"""补齐历史缺口：10 句带内嵌引号的旁白（从没进过 716 交付集）。

为什么会有这个缺口：
  这 10 句的正文里带弯引号（‘ ’），早期 `tokens+puncts` 拼接在弯引号上失败，
  pause 标注 `pause_llm_narr_v3.json` 对它们给了 0 个槽位 ⇒ 没进 `out_paused_narr`，
  也就没进 716 交付集。现役 `_audio_ch123/out` 里只有它们的干声（0.80 降速版）。

处置：按新标准重生成 → 插停顿（无槽位时就只做 trim+归一，不硬造停顿）→ 重建成 726 句。

用法（等抽 seed 那步跑完再跑，避免抢 GPU）：
    G:/Python310/python.exe -u _fix_missing10.py
"""
import io
import json
import os
import subprocess

ROOT = r"G:/_setup"
PY = r"G:/Python310/python.exe"
IDS = ["c1_0027", "c1_0049", "c1_0105", "c1_0167",
       "c2_0251", "c2_0267", "c2_0326",
       "c3_0797", "c3_0944", "c3_0953"]


def run(cmd, timeout=7200):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    for ln in ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-4:]:
        print("    " + ln, flush=True)
    return r


def main():
    print("补齐 %d 句" % len(IDS), flush=True)
    print("\n[1/3] 按新标准重生成", flush=True)
    run([PY, "-u", "_regen_all_1123.py", "--ids", ",".join(IDS),
         "--out", "G:/_setup/_regen_1123"], timeout=7200)

    miss = [i for i in IDS if not os.path.exists(os.path.join(ROOT, "_regen_1123", i + ".wav"))]
    if miss:
        print("!! 仍缺 %s，后续步骤跳过" % miss, flush=True)
        return

    print("\n[2/3] 插停顿（这 10 句无标注槽位，只做 trim+归一）", flush=True)
    run([PY, "-u", "_run_pause_1123.py", "--only", ",".join(IDS)], timeout=3600)

    print("\n[3/3] 重建页面（726 句，不再限定 716 集）", flush=True)
    for chap, out, title in (
            ("all", "_narr_full_listen.html", "旁白全集 · 新标准速度试听"),
            ("Chapter Two", "_narr_ch2_listen.html", "")):
        args = [PY, "-u", "_build_narr_ch2.py", "--chapter", chap,
                "--new", "_regen_1123_paused", "--old", "_audio_ch123/out",
                "--rates", "_rate_narr_v2.json", "--out", "G:/setup/" + out]
        args[args.index("G:/setup/" + out)] = os.path.join(ROOT, out)
        if title:
            args += ["--title", title]
        run(args, timeout=1800)
    print("\n完成。注意：这 10 句没有内部停顿标注，听感会比其余句子更「一口气」。",
          flush=True)


if __name__ == "__main__":
    main()
