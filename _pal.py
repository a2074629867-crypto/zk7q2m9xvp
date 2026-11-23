# -*- coding: utf-8 -*-
"""命令面板直通车：F1 → 输入命令名 → 回车。

用法: python _pal.py "屏幕阅读器"
"""
import sys

sys.path.insert(0, "G:/_setup")
from _bw import send


def call(tool, **args):
    r = send({"op": "call", "tool": tool, "args": args})
    v = r.get("result") or {}
    return v.get("result") or v


def main():
    text = " ".join(sys.argv[1:])
    print("F1:", call("cua_keypress", keys="F1"))
    # 面板可能没弹出来，等一会
    import time
    time.sleep(1.2)
    if text:
        print("type:", call("cua_type", text=text))
        time.sleep(1.0)
        print("enter:", call("cua_keypress", keys="Enter"))


if __name__ == "__main__":
    main()
