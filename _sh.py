# -*- coding: utf-8 -*-
"""在云端 VS Code Web 的终端里执行一条命令（走浏览器 MCP 的 cua_execute）。

用法: python _sh.py "ls -la"
      python _sh.py --raw "多行文本"      # 只输入不回车
"""
import json
import sys

sys.path.insert(0, "G:/_setup")
from _bw import send

# 终端内容区的点击点（CSS 像素，窗口 1088x500）
CLICK = (520, 420)


def run(cmd, enter=True):
    acts = [{"type": "click", "x": CLICK[0], "y": CLICK[1]}]
    acts.append({"type": "type", "text": cmd})
    if enter:
        acts.append({"type": "keypress", "keys": "Enter"})
    out = send({"op": "call", "tool": "cua_execute", "args": {"actions": acts}}, timeout=180)
    r = out.get("result") or {}
    if r.get("isError"):
        return "ERR " + str(r.get("raw"))[:300]
    return "ok"


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    if a[0] == "--raw":
        print(run(a[1], enter=False))
    else:
        print(run(" ".join(a)))
