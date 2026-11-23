# -*- coding: utf-8 -*-
"""一次调用内完成：启 Edge → 连 CDP → 执行动作 → 打印结果。

因为工具调用结束后子进程会被回收，浏览器必须「起-用-读」在同一个进程里跑完。
用法：
    python _ms.py goto <url>
    python _ms.py text
    python _ms.py shot <path>
    python _ms.py run "<python 片段，变量 ws/st 可用>"   # 复杂交互
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import time

import requests
import websockets

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
UDD = r"C:\Users\86178\EdgeCDP"
BASE = "http://127.0.0.1:9222"
NOPROXY = {"http": None, "https": None}
DETACHED = 0x00000008
NEWGRP = 0x00000200


def ensure_edge():
    try:
        requests.get(BASE + "/json/version", timeout=2, proxies=NOPROXY)
        return "已在线"
    except Exception:
        pass
    subprocess.Popen([EDGE, "--remote-debugging-port=9222", "--remote-allow-origins=*",
                      "--user-data-dir=" + UDD, "--no-first-run",
                      "--disable-features=msEdgeSidebarV2", "about:blank"],
                     creationflags=DETACHED | NEWGRP, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        time.sleep(0.5)
        try:
            requests.get(BASE + "/json/version", timeout=2, proxies=NOPROXY)
            return "已启动"
        except Exception:
            continue
    raise SystemExit("Edge 起不来")


def page_ws(prefer=None):
    tabs = requests.get(BASE + "/json/list", timeout=5, proxies=NOPROXY).json()
    pages = [t for t in tabs if t.get("type") == "page"]
    if not pages:
        raise SystemExit("无 page target")
    if prefer:
        for t in pages:
            if prefer in t.get("url", ""):
                return t["webSocketDebuggerUrl"]
    for t in pages:
        if not t["url"].startswith("about:"):
            return t["webSocketDebuggerUrl"]
    return pages[0]["webSocketDebuggerUrl"]


class St:
    def __init__(self):
        self.i = 0

    async def send(self, ws, method, **p):
        self.i += 1
        mid = self.i
        await ws.send(json.dumps({"id": mid, "method": method, "params": p}))
        while True:
            m = json.loads(await ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})


async def main():
    act = sys.argv[1] if len(sys.argv) > 1 else "text"
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    print("[edge]", ensure_edge(), flush=True)

    st = St()
    async with websockets.connect(page_ws("modelscope"), max_size=64 << 20) as ws:
        await st.send(ws, "Page.enable")
        await st.send(ws, "Runtime.enable")

        if act == "goto":
            await st.send(ws, "Page.navigate", url=arg)
            await asyncio.sleep(5)
            r = await st.send(ws, "Runtime.evaluate", expression="location.href",
                              returnByValue=True)
            print("URL:", r["result"]["value"])
        elif act == "text":
            r = await st.send(ws, "Runtime.evaluate",
                              expression="document.body.innerText", returnByValue=True)
            print(r["result"]["value"] or "")
        elif act == "shot":
            r = await st.send(ws, "Page.captureScreenshot", format="png")
            open(arg, "wb").write(base64.b64decode(r["data"]))
            print("saved", arg)
        elif act == "run":
            import ast
            ns = {"asyncio": asyncio, "ws": ws, "st": st, "json": json}
            code = compile(arg, "<run>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            r = eval(code, ns)
            if r is not None:
                await r
        # 保持连接一小会儿，让页面脚本有机会跑完
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main())
