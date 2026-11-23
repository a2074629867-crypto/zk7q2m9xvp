# -*- coding: utf-8 -*-
"""_wl_asr.py —— Parakeet TDT v3 批量转写（词级时间戳 + 词置信度），供 wlevel_probe 用。

为什么单独一个脚本：
  ASR 必须在 asr_venv 跑（主环境 G:/Python310 没装 onnx_asr），
  F0 必须在主环境跑（asr_venv 没装 parselmouth）。
  两个环境靠这个 json 交接，与 2026-10-18 定下的两步口径一致。

用（必须 asr_venv）：
  asr_venv/Scripts/python.exe _wl_asr.py --list wavs.txt --out _wl_words.json --append
  asr_venv/Scripts/python.exe _wl_asr.py a.wav b.wav --out x.json

输出：
  { "<wav>": {"dur": 5.24, "text": "...",
                "words": [{"w": "never", "start": 0.32, "end": 0.64, "p": 0.999}]} }
  p = exp(min(token logprob))，即该词最不可信那个子词的置信度（吞字/读错的主信号）。
  时间戳粒度为 80ms（RAG 2026-10-18），短词窗少帧，下游必须用 n_fr 门槛过滤。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _asr_lib  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wavs", nargs="*")
    ap.add_argument("--list", default=None, help="每行一个 wav 路径")
    ap.add_argument("--out", default="_wl_words.json")
    ap.add_argument("--append", action="store_true", help="合并进已有 --out")
    ap.add_argument("--no-trim", action="store_true", help="不裁首尾静音")
    a = ap.parse_args()

    paths = [p.replace("\\", "/") for p in a.wavs]
    if a.list:
        paths += [ln.strip().replace("\\", "/") for ln in open(a.list, encoding="utf-8") if ln.strip()]
    if not paths:
        raise SystemExit("没有输入 wav")

    old = {}
    if a.append and os.path.exists(a.out):
        old = json.load(open(a.out, encoding="utf-8"))
    todo = [p for p in paths if p not in old]
    print("输入 %d 条，已有 %d 条，待跑 %d 条" % (len(paths), len(paths) - len(todo), len(todo)))

    if todo:
        r = _asr_lib.transcribe(todo, trim=not a.no_trim)
        old.update(r)
        json.dump(old, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s（%d 条）" % (a.out, len(old)))


if __name__ == "__main__":
    main()
