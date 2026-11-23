#!/usr/bin/env python3
"""云端终端可靠执行器。

要点（都是踩过的）：
- dom_cua_get_visible_dom 每次重编号 → 必须「取 DOM → 立刻点」在同一轮完成
- node_id 必须传字符串
- 终端标签 = aria-label="终端"（<li> 或 <a> 都有，点 <a> 更稳）
- Enter 会间歇性丢失 → 连按三次
- 面板高度会变 → 命令统一 clear 后打印，输出固定从顶部开始
"""
import re
import sys
import time

sys.path.insert(0, "G:/_setup")
from _bw import send  # noqa: E402


def _dom():
    r = send({"op": "dom"})
    d = (r.get("result") or {}).get("result") or {}
    return (d.get("snapshot") or "").replace("\\n", "\n")


def _find(pattern):
    for ln in _dom().splitlines():
        if re.search(pattern, ln):
            m = re.search(r"node_id=(\d+)", ln)
            if m:
                return m.group(1)
    return None


def focus_terminal(maximize=True):
    """确保终端面板可见且有焦点。返回是否成功。"""
    if maximize:
        n = _find(r'aria-label="最大化面板大小"')
        if n:
            send({"op": "call", "tool": "dom_cua_click", "args": {"node_id": n}})
            time.sleep(1.2)
    # 面板可能被折叠 → 先展开
    if not _find(r'aria-label="终端"'):
        n = _find(r'aria-label="切换面板 \(Ctrl\+J\)"')
        if n:
            send({"op": "call", "tool": "dom_cua_click", "args": {"node_id": n}})
            time.sleep(1.5)
    tab = _find(r'<a[^>]*aria-label="终端"') or _find(r'aria-label="终端"')
    if not tab:
        return False
    send({"op": "call", "tool": "dom_cua_click", "args": {"node_id": tab}})
    time.sleep(1.5)
    return True


def run(cmd, wait=6):
    ok = focus_terminal()
    if not ok:
        print("FOCUS_FAIL", flush=True)
        return False
    send({"op": "type", "text": cmd})
    time.sleep(1.4)
    for _ in range(3):
        send({"op": "keys", "keys": "Enter"})
        time.sleep(1.0)
    time.sleep(wait)
    return True


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "echo HELLO_$(date +%T)"
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    sys.exit(0 if run(c, w) else 1)
