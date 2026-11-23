# -*- coding: utf-8 -*-
"""把本地脚本 base64 后粘进云端终端，落地成文件。

用法: python _up.py 本地文件 云端路径
"""
import base64
import sys

sys.path.insert(0, "G:/_setup")
from _bw import send


def main():
    local, remote = sys.argv[1], sys.argv[2]
    raw = open(local, "rb").read()
    b64 = base64.b64encode(raw).decode()
    cmd = "mkdir -p $(dirname %s); echo '%s' | base64 -d > %s && wc -c %s" % (
        remote, b64, remote, remote)
    r = send({"op": "type", "text": cmd})
    print("type:", str(r.get("result"))[:80])
    r = send({"op": "keys", "keys": "Enter"})
    print("enter:", str(r.get("result"))[:80])


if __name__ == "__main__":
    main()
