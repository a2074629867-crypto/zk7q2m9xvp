"""Remote Cloud Command —— 通过 ntfy.sh 双向通道在云端跑命令，结果取回本地。

通道结构（filebin 写额度已满，全程不用它）：
  下发：POST https://ntfy.sh/tts_c7k2mq   body = "b64:<base64(shell)>"
  回传：云端 POST https://ntfy.sh/tts_o7k2mq   正文即 stdout+stderr（≤3.3KB）
  云端常驻执行器：/home/aistudio/w11.py

用法：
  python rcc.py "nvidia-smi"
  python rcc.py -f script.sh --timeout 600
  python rcc.py --put local.bin remote_name        # 上传附件到 ntfy 并给出下载命令
  python rcc.py --shell                            # 交互式
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

CMD_TOPIC = "https://ntfy.sh/tts_c7k2mq"
OUT_TOPIC = "https://ntfy.sh/tts_o7k2mq"
PROXY = "http://127.0.0.1:7897"
CURL = "C:/Windows/System32/curl.exe"

_openers = [
    urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    ),
    urllib.request.build_opener(urllib.request.ProxyHandler({})),
]


def _urlopen(req_or_url, timeout=30):
    """优先走代理；代理没开（7897 掉线很常见）就直接连。"""
    last = None
    for op in _openers:
        try:
            return op.open(req_or_url, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def post(topic, body: bytes, timeout=30):
    """用 curl 发（urllib 对 ntfy.sh 会 SSL handshake timeout，curl 正常）。"""
    import subprocess
    r = subprocess.run([CURL, "-s", "--max-time", str(timeout), "-X", "POST",
                        "--data-binary", "@-", topic],
                       input=body, capture_output=True)
    return 200 if r.returncode == 0 else 0


def fetch_since(topic, since="10m", timeout=25):
    import subprocess
    url = topic + "/json?poll=1&since=" + urllib.parse.quote(since)
    r = subprocess.run([CURL, "-s", "--max-time", str(timeout), url],
                       capture_output=True, text=True, errors="replace")
    return r.stdout or ""


def messages(raw):
    out = []
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
        m = d.get("message") or ""
        if m:
            out.append((d.get("id", ""), m))
    return out


def push(cmd_text):
    jid = "%08x" % (int(time.time() * 1000) & 0xFFFFFFFF)
    wrapped = 'echo "JID=%s"\n%s\n' % (jid, cmd_text)
    b64 = base64.b64encode(wrapped.encode()).decode()
    if len(b64) > 3500:
        raise RuntimeError("命令太长（base64 %d > 3500），请用 --put 传脚本" % len(b64))
    post(CMD_TOPIC, ("b64:" + b64).encode())
    return jid


def wait(jid, timeout):
    t0 = time.time()
    tag = "JID=" + jid
    while time.time() - t0 < timeout:
        time.sleep(6)
        for _mid, m in messages(fetch_since(OUT_TOPIC, "3m")):
            if tag in m:
                body = m.split(tag, 1)[1]
                return body.lstrip("\n"), time.time() - t0
    return None, time.time() - t0


def put_file(local, name=None):
    name = name or os.path.basename(local)
    data = open(local, "rb").read()
    req = urllib.request.Request(OUT_TOPIC, data=data, method="PUT")
    req.add_header("Filename", name)
    req.add_header("Content-Type", "application/octet-stream")
    with _urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode())
    return d["attachment"]["url"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", help="要执行的命令")
    ap.add_argument("-f", "--file", help="从脚本文件读取命令")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--put", nargs=2, metavar=("LOCAL", "REMOTE"), help="上传文件，输出云端下载命令")
    ap.add_argument("--raw", action="store_true", help="不打印耗时行")
    a = ap.parse_args()

    if a.put:
        url = put_file(a.put[0], a.put[1])
        print("URL:", url)
        print("云端下载: curl -sL -o %s '%s'" % (a.put[1], url))
        return

    if a.file:
        cmd = open(a.file, encoding="utf-8").read()
    elif a.cmd:
        cmd = a.cmd
    else:
        print("需要命令或 -f 脚本", file=sys.stderr)
        sys.exit(1)

    try:
        jid = push(cmd)
    except RuntimeError as e:
        print("[err]", e, file=sys.stderr)
        sys.exit(2)
    txt, el = wait(jid, a.timeout)
    if txt is None:
        print("(超时 %ds，无回传)" % a.timeout)
        sys.exit(3)
    print(txt)
    if not a.raw:
        print("[done] %.1fs" % el, file=sys.stderr)


if __name__ == "__main__":
    main()
