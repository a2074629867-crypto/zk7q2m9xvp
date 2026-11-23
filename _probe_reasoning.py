# -*- coding: utf-8 -*-
"""探测：hy3 / ds 能否关掉思维链（reasoning）。同一题不同参数对比 completion_tokens。"""
import json, time, urllib.request, urllib.error

from _llm_key import get_key
KEY = get_key()
GW = "http://127.0.0.1:7864/v1/chat/completions"
Q = "数一下 1 到 30 之间有几个质数，只回答数字。"

VARIANTS = [
    ("baseline", {}),
    ("reasoning_effort=none", {"reasoning_effort": "none"}),
    ("reasoning_effort=minimal", {"reasoning_effort": "minimal"}),
    ("thinking.disabled", {"thinking": {"type": "disabled"}}),
    ("enable_thinking=false", {"enable_thinking": False}),
    ("chat_template_kwargs", {"chat_template_kwargs": {"thinking": False}}),
]
MODELS = [("hy3", "global:hy3"), ("ds", "global:deepseek-v4.1-flash-sg")]

def post(model, extra, timeout=180):
    body = {"model": model, "max_tokens": 64, "stream": False, "temperature": 0,
            "messages": [{"role": "user", "content": Q}]}
    body.update(extra)
    req = urllib.request.Request(GW, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        u = d.get("usage") or {}
        c = (d["choices"][0]["message"].get("content") or "").strip().replace("\n", " ")
        return "%.1fs" % (time.time() - t0), u.get("completion_tokens"), u.get("total_tokens"), c[:40]
    except urllib.error.HTTPError as e:
        return "HTTP %s" % e.code, None, None, (e.read() or b"")[:90].decode("utf-8", "replace")
    except Exception as e:
        return type(e).__name__, None, None, str(e)[:80]

for name, mid in MODELS:
    print("\n### %s (%s)" % (name, mid))
    print("  %-24s %8s %7s %7s  %s" % ("variant", "latency", "comp", "total", "content"))
    for vn, extra in VARIANTS:
        dt, comp, tot, c = post(mid, extra)
        print("  %-24s %8s %7s %7s  %s" % (vn, dt, comp, tot, c))
