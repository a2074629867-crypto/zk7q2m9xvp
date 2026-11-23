# -*- coding: utf-8 -*-
"""在云端终端执行命令：先点“终端”标签，再点内容区输入。

用法: python _sh2.py "命令"
"""
import sys

sys.path.insert(0, "G:/_setup")
from _bw import send

TERM_TAB = "42"
BODY = (700, 460)


def click(node):
    return send({"op": "call", "tool": "dom_cua_click", "args": {"node_id": node}})


def ensure_term():
    click(TERM_TAB)


def run(cmd):
    ensure_term()
    acts = [{"type": "click", "x": BODY[0], "y": BODY[1]},
            {"type": "type", "text": cmd},
            {"type": "keypress", "keys": "Enter"}]
    out = send({"op": "call", "tool": "cua_execute", "args": {"actions": acts}})
    r = out.get("result") or {}
    return "ERR " + str(r.get("raw"))[:200] if r.get("isError") else "ok"


if __name__ == "__main__":
    print(run(" ".join(sys.argv[1:])))
