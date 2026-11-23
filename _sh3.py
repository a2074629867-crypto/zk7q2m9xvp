# -*- coding: utf-8 -*-
"""在云端 VS Code Web 终端执行命令。

坑：dom snapshot 的 node_id 是**每次快照内唯一**，旧 id 点不动东西。
所以每次都重新取快照、现找「终端」标签的 node_id。

用法: python _sh3.py "命令"
"""
import re
import sys

sys.path.insert(0, "G:/_setup")
from _bw import send

BODY = (700, 462)


def dom():
    r = send({"op": "dom"})
    return ((r.get("result") or {}).get("result") or {}).get("snapshot") or ""


def find_node(pattern):
    for ln in dom().splitlines():
        if re.search(pattern, ln):
            m = re.search(r"node_id=(\S+)", ln)
            if m:
                return m.group(1).strip('"')
    return None


def click_node(node):
    return send({"op": "call", "tool": "dom_cua_click", "args": {"node_id": str(node)}})


def run(cmd):
    # 注意：标签顺序是 <li node_id=42 aria-label="终端" role="tab">终端</li>
    # role 在 label 之后，所以不能要求 role 先行。
    nid = find_node(r'aria-label="终端"')
    if not nid:
        nid = find_node(r'role="tab"[^>]*>终端')
    if nid:
        click_node(nid)
    acts = [{"type": "click", "x": BODY[0], "y": BODY[1]},
            {"type": "type", "text": cmd},
            {"type": "keypress", "keys": "Enter"}]
    r = send({"op": "call", "tool": "cua_execute", "args": {"actions": acts}})
    res = (r.get("result") or {}).get("result") or {}
    return "ok tab=%s" % nid if not res.get("isError") else "ERR " + str(res.get("raw"))[:200]


if __name__ == "__main__":
    print(run(" ".join(sys.argv[1:])))
