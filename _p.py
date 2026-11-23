# -*- coding: utf-8 -*-
"""_p.py —— 云端状态轮询器：发一条写状态文件的命令，再从 filebin 读回来。

背景：filebin 同名 PUT 不覆盖（GET 永远返回第一版），
      所以每次换新文件名 s<N>.txt。用法: python _p.py 3
"""
import sys
import time
import urllib.request

sys.path.insert(0, "G:/_setup")
from _bw import send

BIN = "https://filebin.net/acpp7f3k9x"
ROOT = "/mnt/workspace/cloudstack"


def main(n):
    name = "s%s.txt" % n
    inner = (
        "date +%%T; tail -6 boot.log; "
        "echo V=$(du -sh venv 2>/dev/null|cut -f1); "
        "echo A=$(du -sh asr_venv 2>/dev/null|cut -f1); "
        "echo W=$(du -sh models 2>/dev/null|cut -f1)"
    ) % ()
    cmd = ("cd %s; { %s; } > %s; "
           "curl -s -o /dev/null -X PUT --data-binary @%s %s/%s"
           % (ROOT, inner, name, name, BIN, name))

    send({"op": "click", "x": 700, "y": 500})
    time.sleep(0.8)
    send({"op": "type", "text": cmd})
    time.sleep(1.5)
    send({"op": "keys", "keys": "Enter"})
    time.sleep(9)

    try:
        req = urllib.request.Request("%s/%s" % (BIN, name),
                                     headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            print(r.read().decode("utf-8", "replace").strip())
    except Exception as e:
        print("READ_FAIL %s: %s" % (type(e).__name__, e))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "0")
