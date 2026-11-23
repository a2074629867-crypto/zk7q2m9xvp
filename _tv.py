# -*- coding: utf-8 -*-
"""云端终端输入器（稳健版）。

历史坑：
1. 坐标点击不可靠 —— 终端面板高度会变，(700,462) 有时落在编辑器上。
2. DOM 里找 aria-label="终端" 有时拿不到（面板折叠/快照裁剪）。
3. Ctrl+` 是 toggle，面板已开时会把终端关掉。

⇒ 用命令面板 `workbench.action.terminal.focus`，它无条件把焦点送进终端。
用法: python _tv.py "命令"
"""
import sys
import time

sys.path.insert(0, "G:/_setup")
from _bw import send


def kp(keys):
    return send({"op": "keys", "keys": keys})


def typ(text):
    return send({"op": "type", "text": text})


def focus_terminal():
    """命令面板 -> workbench.action.terminal.focus"""
    kp("Control+Shift+P")
    time.sleep(1.2)
    typ("workbench.action.terminal.focus")
    time.sleep(1.0)
    kp("Enter")
    time.sleep(1.0)


def main(cmd):
    focus_terminal()
    typ(cmd)
    time.sleep(0.8)
    kp("Enter")
    return "sent"


if __name__ == "__main__":
    print(main(" ".join(sys.argv[1:])))
