# -*- coding: utf-8 -*-
"""浏览器代理客户端：python _bw.py <tool> '<json>'  或  _bw.py --dom / --shot x.png / --goto URL"""
import base64
import json
import socket
import sys

HOST, PORT = "127.0.0.1", 18777


def send(cmd, timeout=180):
    s = socket.create_connection((HOST, PORT), timeout=timeout)
    try:
        s.sendall((json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8"))
    finally:
        s.close()


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    if a[0] == "--dom":
        cmd = {"op": "dom"}
    elif a[0] == "--shot":
        cmd = {"op": "shot"}
    elif a[0] == "--clip":
        # _bw.py --clip X Y W H [out.png]
        cmd = {"op": "shot", "fmt": "png",
               "clip": {"x": int(a[1]), "y": int(a[2]),
                        "width": int(a[3]), "height": int(a[4])}}
    elif a[0] == "--goto":
        cmd = {"op": "goto", "url": a[1]}
    elif a[0] == "--type":
        cmd = {"op": "type", "text": a[1]}
    elif a[0] == "--keys":
        cmd = {"op": "keys", "keys": a[1]}
    elif a[0] == "--url":
        cmd = {"op": "url"}
    elif a[0] == "--call":
        cmd = {"op": "call", "tool": a[1],
               "args": json.loads(a[2]) if len(a) > 2 else {}}
    elif a[0] == "--click":
        cmd = {"op": "click", "x": int(a[1]), "y": int(a[2])}
    elif a[0] == "--newtab":
        cmd = {"op": "newtab", "url": a[1]}
    else:
        cmd = {"op": "call", "tool": a[0],
               "args": json.loads(a[1]) if len(a) > 1 else {}}

    out = send(cmd)
    if not out.get("ok"):
        print("ERROR:", out.get("error"))
        return 2

    r = out["result"]
    # 截图：把 image content 落盘
    if a[0] in ("--shot", "--clip"):
        path = a[1] if a[0] == "--shot" and len(a) > 1 else (
            a[5] if a[0] == "--clip" and len(a) > 5 else "shot.png")
        blocks = (r or {}).get("content") or []
        saved = 0
        for b in blocks:
            if b.get("type") == "image":
                data = b.get("data") or ""
                with open(path, "wb") as f:
                    f.write(base64.b64decode(data))
                saved += 1
                print("saved", path, len(data) // 1024, "KB(base64)")
        if not saved:
            print(json.dumps(r, ensure_ascii=False)[:1500])
        return 0

    print(json.dumps(r, ensure_ascii=False)[:12000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
