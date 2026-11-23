# -*- coding: utf-8 -*-
"""两个试听页的交付前校验：src 存在性 + 数据统计 + JS 语法。

不做「看起来对」的检查，只报数字：
  - 每个 take 的 src 文件是否真实存在、大小
  - AB 页四列覆盖（A/B/C/D 各几条）
  - ch2 页 fallback / missing 计数
"""
import io
import json
import os
import re
import subprocess
import sys

ROOT = "G:/_setup"
ok = True


def load_data(path):
    t = io.open(path, encoding="utf-8").read()
    m = re.search(r"const DATA = (\{.*?\});\n", t, re.S)
    return t, json.loads(m.group(1))


# ---------- AB 页 ----------
p1 = os.path.join(ROOT, "_listen_page.html")
t1, d1 = load_data(p1)
print("=== _listen_page.html ===")
print("rows", len(d1["rows"]), "title", d1["title"])
cols = {}
bad = []
for r in d1["rows"]:
    for tk in r["takes"]:
        k = tk["key"]
        if tk.get("missing"):
            cols.setdefault(k, [0, 0])[1] += 1
            continue
        cols.setdefault(k, [0, 0])[0] += 1
        fp = os.path.join(ROOT, tk["src"])
        if not os.path.exists(fp):
            bad.append((r["id"], k, tk["src"]))
        elif os.path.getsize(fp) < 20000:
            bad.append((r["id"], k, "TOO_SMALL", os.path.getsize(fp)))
print("列覆盖(有/缺):", {k: "%d/%d" % (v[0], v[1]) for k, v in sorted(cols.items())})
print("坏路径:", bad if bad else "0")
ok = ok and not bad

# D 列 dur 与 pick 摘要一致性
summ = json.load(io.open(os.path.join(ROOT, "_pick54_summary.json"), encoding="utf-8"))
print("D 摘要: %d 条, flag=%s" % (
    len(summ), {f: sum(1 for v in summ.values() if v["flag"] == f) for f in ("OK", "WARN")}))
for r in d1["rows"]:
    dk = [tk for tk in r["takes"] if tk["key"] == "D"][0]
    s = summ.get(r["id"])
    if s and abs((dk.get("dur") or 0) - s["dur"]) > 0.05:
        print("  !! dur 不一致", r["id"], dk.get("dur"), s["dur"])
        ok = False

# ---------- ch2 页 ----------
p2 = os.path.join(ROOT, "_narr_ch2_listen.html")
t2, d2 = load_data(p2)
print("\n=== _narr_ch2_listen.html ===")
st = d2.get("stat") or {}
print("rows", len(d2["rows"]), "stat", json.dumps(st, ensure_ascii=False))
miss = [r["id"] for r in d2["rows"] if not (r["takes"].get("new") or {}).get("src")]
print("无 new 音源:", miss if miss else "0")
badsrc = []
for r in d2["rows"]:
    for key in ("new", "old"):
        tk = r["takes"].get(key) or {}
        s = tk.get("src")
        if s and not os.path.exists(os.path.join(ROOT, s)):
            badsrc.append((r["id"], key, s))
print("坏路径:", badsrc if badsrc else "0")
ok = ok and not badsrc and not miss

# ---------- JS 语法 ----------
for tag, txt in (("ab", t1), ("ch2", t2)):
    js = re.search(r"<script>(.*)</script>", txt, re.S).group(1)
    fp = os.path.join("D:/wb2api-cli", "_chk_%s.js" % tag)
    io.open(fp, "w", encoding="utf-8").write(js)
    r = subprocess.run(["node", "--check", fp], capture_output=True, text=True)
    print("JS %-4s %s" % (tag, "OK" if r.returncode == 0 else "ERR " + (r.stderr or "")[:200]))
    ok = ok and r.returncode == 0

print("\n==> %s" % ("ALL PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
