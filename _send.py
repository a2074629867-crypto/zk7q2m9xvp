# -*- coding: utf-8 -*-
"""可靠地向云端终端发送一条命令。

踩坑记录：
- cua_type 只在焦点位于 xterm 时才生效；面板切换/命令结束后焦点会丢，输入被静默吞掉。
- 必须每轮重取 DOM（node_id 是快照作用域）。

做法：DOM 点「终端」标签 -> 坐标点终端内容区 -> 输入 -> 停顿 -> 回车。
用法: python _send.py "命令"
"""
import re
import sys
import time

sys.path.insert(0, "G:/_setup")
from _bw import send


def dom():
    r = send({"op": "dom"})
    return ((r.get("result") or {}).get("result") or {}).get("snapshot") or ""


def term_node():
    for ln in dom().replace("\\n", "\n").splitlines():
        if 'aria-label="终端"' in ln:
            m = re.search(r"node_id=(\d+)", ln)
            if m:
                return m.group(1)
    return None


def send_cmd(cmd, body=(600, 110), verify_tries=1):
    nid = term_node()
    if nid:
        send({"op": "call", "tool": "dom_cua_click", "args": {"node_id": nid}})
        time.sleep(0.7)
    send({"op": "click", "x": body[0], "y": body[1]})
    time.sleep(0.4)
    send({"op": "type", "text": cmd})
    time.sleep(1.0)
    send({"op": "keys", "keys": "Enter"})
    time.sleep(0.6)
    return "nid=%s" % nid


if __name__ == "__main__":
    print(send_cmd(" ".join(sys.argv[1:])))
