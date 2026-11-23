# -*- coding: utf-8 -*-
"""网关探活：区分「网关挂了」/「模型池 502」/「单 id 不通」。
只发极小请求（max_tokens=8），不写任何产物。
"""
import json, time, urllib.request, urllib.error, sys

from _llm_key import get_key
KEY = get_key()
GWS = ["http://127.0.0.1:7864", "http://127.0.0.1:7863"]
LANES = {
    "hy4": "global:hy4free",
    "hy3": "global:hy3",
    "ds":  "global:deepseek-v4.1-flash-sg",
    "ds2": "deepseek-v4.1-flash",
    "mm":  "global:minimax-m3.1-flash",
}

def call(url, payload, timeout=90):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        return "HTTP %s" % e.code, time.time() - t0, (e.read() or b"")[:200].decode("utf-8", "replace")
    except Exception as e:
        return "ERR %s" % type(e).__name__, time.time() - t0, str(e)[:200]
    try:
        d = json.loads(raw)
        c = d["choices"][0]["message"].get("content") or ""
        return "200", time.time() - t0, c[:60].replace("\n", " ")
    except Exception as e:
        return "BADBODY", time.time() - t0, raw[:200]

print("=" * 70)
for gw in GWS:
    print("\n### %s  GET /v1/models" % gw)
    s, dt, extra = call(gw + "/v1/models", None) if False else (None, 0, "")
    try:
        req = urllib.request.Request(gw + "/v1/models", headers={"Authorization": "Bearer " + KEY})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
        ids = [m.get("id") for m in json.loads(raw).get("data", [])]
        print("  models: %d 个  %.1fs" % (len(ids), time.time() - t0))
        for k, v in LANES.items():
            print("    %-4s %-34s %s" % (k, v, "OK" if v in ids else "!! 不在列表"))
    except Exception as e:
        print("  /models 失败: %s" % str(e)[:120])

    print("\n### %s  POST /chat/completions (max_tokens=8)" % gw)
    for k, v in LANES.items():
        for rnd in (1, 2):
            st, dt, extra = call(gw + "/v1/chat/completions", {
                "model": v, "max_tokens": 8, "stream": False, "temperature": 0,
                "messages": [{"role": "user", "content": "只回复两个字：收到"}]})
            print("  %-4s r%d  %-14s %5.1fs  %s" % (k, rnd, st, dt, extra[:80]))
            if st != "200":
                time.sleep(1.0)
