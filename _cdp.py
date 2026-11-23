# -*- coding: utf-8 -*-
"""极简 CDP 客户端：直连本机 Edge 的 9222 端口，不需要 playwright。

    python _cdp.py open https://example.com
    python _cdp.py eval "document.title"
    python _cdp.py shot out.png
    python _cdp.py type "ls -la\n"
    python _cdp.py click "button.submit"
    python _cdp.py text            # 页面纯文本
"""
import asyncio
import base64
import json
import sys

import requests
import websockets

BASE = "http://127.0.0.1:9222"
NOPROXY = {"http": None, "https": None}   # Clash 会劫持 localhost，必须显式绕过


def _page_ws():
    """取当前活动页的 webSocketDebuggerUrl。"""
    tabs = requests.get(BASE + "/json/list", timeout=5, proxies=NOPROXY).json()
    pages = [t for t in tabs if t.get("type") == "page"]
    if not pages:
        raise SystemExit("没有 page target")
    # 优先非 about:blank
    for t in pages:
        if not t["url"].startswith("about:"):
            return t["webSocketDebuggerUrl"]
    return pages[0]["webSocketDebuggerUrl"]


def _new_tab(url):
    r = requests.put(BASE + "/json/new?" + url, timeout=10, proxies=NOPROXY)
    if r.status_code != 200:
        r = requests.get(BASE + "/json/new?" + url, timeout=10, proxies=NOPROXY)
    return r.json()["webSocketDebuggerUrl"]


class S:
    def __init__(self):
        self.i = 0

    async def send(self, ws, method, **params):
        self.i += 1
        mid = self.i
        await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})


async def _run(action, arg):
    url = None
    if action == "open":
        url = arg
        ws_url = _new_tab(url)
        await asyncio.sleep(0.5)
    else:
        ws_url = _page_ws()

    st = S()
    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        await st.send(ws, "Page.enable")
        await st.send(ws, "Runtime.enable")
        if action == "open":
            await st.send(ws, "Page.navigate", url=url)
            await asyncio.sleep(2.5)

        if action == "eval":
            r = await st.send(ws, "Runtime.evaluate", expression=arg,
                              returnByValue=True, awaitPromise=True)
            print(json.dumps(r.get("result", {}).get("value"), ensure_ascii=False))
        elif action == "text":
            r = await st.send(ws, "Runtime.evaluate",
                              expression="document.body.innerText", returnByValue=True)
            print(r.get("result", {}).get("value") or "")
        elif action == "shot":
            r = await st.send(ws, "Page.captureScreenshot", format="png")
            open(arg, "wb").write(base64.b64decode(r["data"]))
            print("saved", arg)
        elif action == "type":
            await st.send(ws, "Input.insertText", text=arg)
            print("typed", len(arg), "chars")
        elif action == "key":
            # arg 形如 "Enter" / "Control+a"
            parts = arg.split("+")
            code = parts[-1]
            mods = 0
            for m in parts[:-1]:
                mods |= {"Alt": 1, "Control": 2, "Meta": 4, "Shift": 8}[m]
            keymap = {"Enter": (13, "Enter", "\r"), "Tab": (9, "Tab", "\t"),
                      "Backspace": (8, "Backspace", ""), "Escape": (27, "Escape", "")}
            vk, k, txt = keymap.get(code, (0, code, ""))
            for t in ("keyDown", "keyUp"):
                p = dict(type=t, modifiers=mods, key=k, windowsVirtualKeyCode=vk,
                         nativeVirtualKeyCode=vk)
                if txt and t == "keyDown":
                    p["text"] = txt
                await st.send(ws, "Input.dispatchKeyEvent", **p)
            print("key", arg)
        elif action == "click":
            js = """(() => {const e=document.querySelector(%s);
                if(!e) return 'notfound'; e.scrollIntoView({block:'center'}); e.click(); return 'ok';})()""" % json.dumps(arg)
            r = await st.send(ws, "Runtime.evaluate", expression=js, returnByValue=True)
            print(r.get("result", {}).get("value"))
        elif action == "url":
            r = await st.send(ws, "Runtime.evaluate",
                              expression="location.href", returnByValue=True)
            print(r.get("result", {}).get("value"))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    act = sys.argv[1]
    a = sys.argv[2] if len(sys.argv) > 2 else ""
    asyncio.run(_run(act, a))
