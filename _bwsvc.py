# -*- coding: utf-8 -*-
"""常驻浏览器代理：持有 MCP 会话，通过本地 TCP 接受命令。

★ 关键：MCP 的工具调用必须是 method="tools/call" + params={name, arguments}。
   把工具名直接当 method 会得到 -32601 method not found。

启动（后台）:  python _bwsvc.py
调用:          python _bw.py --url / --goto URL / --dom / --shot x.png / --type TEXT / --keys KEY
              python _bw.py call <tool> '<json>'
"""
import json
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mcp import MCP

HOST, PORT = "127.0.0.1", 18777
BID = 1          # Edge
TID = [None]     # 当前控制的 tab_id


def tcall(m, name, args):
    """正确的 MCP 工具调用，并把 content[].text 解成对象。"""
    r = m.request("tools/call", {"name": name, "arguments": args or {}})
    texts = [c.get("text") for c in (r.get("content") or []) if c.get("type") == "text"]
    raw = "\n".join(t for t in texts if t)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {"raw": raw}
    if r.get("isError"):
        parsed = {"isError": True, **({"raw": raw} if not isinstance(parsed, dict) else parsed)}
    return parsed


def ensure_tab(m):
    if TID[0] is not None:
        try:
            r = tcall(m, "tabs_get", {"browser_id": BID, "tab_id": TID[0]})
            if r.get("result"):
                return TID[0]
        except Exception:
            pass
    r = tcall(m, "tabs_new", {"browser_id": BID,
                              "url": "https://www.modelscope.cn/code/workspace"})
    res = r.get("result") or r
    TID[0] = res.get("tab_id") or 1
    return TID[0]


def handle(m, cmd):
    op = cmd.get("op") or "call"
    tid = None
    if op in ("url", "title", "goto", "dom", "shot", "type", "keys", "click", "reload"):
        tid = ensure_tab(m)
    if op == "call":
        tool = cmd["tool"]
        args = dict(cmd.get("args") or {})
        if tool.startswith(("tab_", "tabs_", "dom_", "cua_")):
            args.setdefault("browser_id", BID)
            args.setdefault("tab_id", ensure_tab(m))
        return tcall(m, tool, args)
    if op == "newtab":
        r = tcall(m, "tabs_new", {"browser_id": BID, "url": cmd["url"]})
        res = r.get("result") or r
        TID[0] = res.get("tab_id") or TID[0]
        return r
    if op == "goto":
        return tcall(m, "tab_goto", {"browser_id": BID, "tab_id": tid, "url": cmd["url"]})
    if op == "reload":
        return tcall(m, "tab_reload", {"browser_id": BID, "tab_id": tid})
    if op == "dom":
        return tcall(m, "dom_cua_get_visible_dom", {"browser_id": BID, "tab_id": tid})
    if op == "shot":
        args = {"browser_id": BID, "tab_id": tid}
        if cmd.get("clip"):
            args["clip"] = cmd["clip"]
        if cmd.get("fmt"):
            args["format"] = cmd["fmt"]
        if cmd.get("scale"):
            args["quality"] = cmd["scale"]
        return m.request("tools/call", {"name": "tab_screenshot", "arguments": args})
    if op == "type":
        return tcall(m, "cua_type", {"browser_id": BID, "tab_id": tid, "text": cmd["text"]})
    if op == "keys":
        return tcall(m, "cua_keypress", {"browser_id": BID, "tab_id": tid, "keys": cmd["keys"]})
    if op == "click":
        return tcall(m, "cua_click", {"browser_id": BID, "tab_id": tid,
                                      "x": cmd["x"], "y": cmd["y"]})
    if op == "url":
        return tcall(m, "tab_url", {"browser_id": BID, "tab_id": tid})
    if op == "title":
        return tcall(m, "tab_title", {"browser_id": BID, "tab_id": tid})
    if op == "ping":
        return {"ok": True, "tid": TID[0]}
    raise ValueError("unknown op " + str(op))


def serve():
    m = MCP()
    m.init()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(8)
    print("bwsvc ready on %d" % PORT, flush=True)
    while True:
        conn, _ = srv.accept()
        try:
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
            cmd = json.loads(buf.decode("utf-8"))
            try:
                out = {"ok": True, "result": handle(m, cmd)}
            except Exception as e:
                out = {"ok": False, "error": str(e)[:600]}
            conn.sendall((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall((json.dumps({"ok": False, "error": str(e)[:400]}) + "\n").encode())
            except Exception:
                pass
        finally:
            conn.close()


if __name__ == "__main__":
    serve()
