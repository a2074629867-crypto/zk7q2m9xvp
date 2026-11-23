# -*- coding: utf-8 -*-
"""极简 MCP stdio 客户端：直连 browser-mcp.exe，绕开工具注册。
用法:
  python _mcp.py list
  python _mcp.py call <tool> '<json-args>'
"""
import json
import os
import subprocess
import sys
import threading

EXE = r"C:\Users\86178\.workbuddy\native-runtimes\browser-use\browser-use\bin\browser-mcp.exe"


class MCP:
    def __init__(self):
        self.p = subprocess.Popen(
            [EXE],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._id = 0
        self._lock = threading.Lock()

    def _send(self, obj):
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        self.p.stdin.write(data)
        self.p.stdin.flush()

    def _recv(self, timeout=120):
        """逐行读，跳过非 JSON 行。"""
        while True:
            line = self.p.stdout.readline()
            if not line:
                return None
            s = line.decode("utf-8", "replace").strip()
            if not s:
                continue
            try:
                return json.loads(s)
            except Exception:
                continue

    def request(self, method, params=None, timeout=180):
        with self._lock:
            self._id += 1
            mid = self._id
            self._send({"jsonrpc": "2.0", "id": mid, "method": method,
                        "params": params or {}})
            while True:
                msg = self._recv()
                if msg is None:
                    raise RuntimeError("MCP 进程关闭")
                if msg.get("id") == mid:
                    if "error" in msg:
                        raise RuntimeError(json.dumps(msg["error"], ensure_ascii=False))
                    return msg.get("result")

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def init(self):
        r = self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "wb-cli", "version": "1.0"},
        })
        self.notify("notifications/initialized")
        return r

    def close(self):
        try:
            self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.terminate()
        except Exception:
            pass


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    act = sys.argv[1]
    m = MCP()
    try:
        info = m.init()
        print("server:", json.dumps(info.get("serverInfo", {}), ensure_ascii=False))
        if act == "list":
            r = m.request("tools/list")
            for t in r.get("tools", []):
                print("  %-34s %s" % (t["name"], (t.get("description") or "")[:80]))
        elif act == "call":
            name = sys.argv[2]
            args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
            r = m.request("tools/call", {"name": name, "arguments": args})
            txt = []
            for c in r.get("content") or []:
                if c.get("type") == "text":
                    txt.append(c.get("text") or "")
                else:
                    txt.append("<%s>" % c.get("type"))
            print("\n".join(txt)[:8000])
            if r.get("isError"):
                print("!! isError")
                return 2
        return 0
    finally:
        m.close()


if __name__ == "__main__":
    sys.exit(main())
