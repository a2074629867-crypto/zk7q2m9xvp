# -*- coding: utf-8 -*-
"""cwb.py —— 云端常驻执行器（ntfy 双向通道），配合本机 G:/_setup/rcc.py。

协议（与 rcc.py 完全一致，不要改单边）：
  下发  https://ntfy.sh/tts_c7k2mq   body = "b64:" + base64(shell)
        shell 首行是 echo "JID=xxxxxxxx"（rcc.py 自动包）
  回传  https://ntfy.sh/tts_o7k2mq   body = "JID=xxxxxxxx\n" + 输出尾巴(≤3000字)

启动（云端）：
  setsid nohup python3 /home/aistudio/cwb.py > /home/aistudio/cwb.log 2>&1 </dev/null &

铁律：
  - 不回显就重发 JID，否则 rcc.py 认不出来（输出被截尾时 JID 行会掉）
  - 单条输出只回最后 3000 字，长任务自己 nohup 到日志再用 tail 取
"""
import base64
import json
import os
import re
import subprocess
import time
import urllib.request

CMD = "https://ntfy.sh/tts_c7k2mq"
OUT = "https://ntfy.sh/tts_o7k2mq"
CWD = "/home/aistudio"
TAIL = 3000


def post(url, body):
    for _ in range(3):
        try:
            req = urllib.request.Request(url, data=body, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status
        except Exception as e:
            sys_err("post fail: %r" % (e,))
            time.sleep(3)
    return None


def sys_err(msg):
    with open("/home/aistudio/cwb.log", "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))


def poll(since):
    url = CMD + "/json?poll=1&since=" + str(since)
    try:
        with urllib.request.urlopen(url, timeout=45) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        sys_err("poll fail: %r" % (e,))
        return ""


def run_shell(sh):
    m = re.search(r"JID=([0-9a-fA-F]{6,16})", sh)
    jid = m.group(1) if m else "unknown"
    try:
        p = subprocess.run(
            ["bash", "-lc", sh], cwd=CWD, capture_output=True, text=True, timeout=900
        )
        out = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        out, rc = "[cwb] TIMEOUT 900s", -9
    except Exception as e:
        out, rc = "[cwb] EXC %r" % (e,), -1
    if len(out) > TAIL:
        out = "...[truncated]...\n" + out[-TAIL:]
    body = "JID=%s rc=%s\n%s" % (jid, rc, out)
    post(OUT, body.encode("utf-8"))
    sys_err("ran JID=%s rc=%s len=%d" % (jid, rc, len(out)))


def main():
    sys_err("cwb start pid=%d" % os.getpid())
    last = int(time.time())
    while True:
        raw = poll(last)
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("event") != "message":
                continue
            t = int(d.get("time") or 0)
            if t <= last:
                continue
            last = max(last, t)
            msg = d.get("message") or ""
            if not msg.startswith("b64:"):
                continue
            try:
                sh = base64.b64decode(msg[4:]).decode("utf-8", "replace")
            except Exception as e:
                sys_err("b64 decode fail: %r" % (e,))
                continue
            sys_err("got cmd time=%d bytes=%d" % (t, len(sh)))
            run_shell(sh)
        time.sleep(2)


if __name__ == "__main__":
    main()
