# -*- coding: utf-8 -*-
"""把某一章的 TTS 单元对齐到原书段落，判定「段末」。

用法：G:/Python310/python.exe _ch1_para_align.py --chapter 2

原文 castle_full.txt 是「每行一段 + 空行分隔」。旁白单元 = 段落剔除对话后的碎片，
所以一个段落可能产出 1~N 个单元。对齐只在词序列上做（去标点、小写），
用贪心最长匹配把单元逐个钉到原文词流上。
"""
import argparse
import json
import re
import sys
sys.path.insert(0, "G:/_setup")

ap = argparse.ArgumentParser()
ap.add_argument("--chapter", type=int, default=1)
ap.add_argument("--txt", default="G:/_setup/castle_full.txt")
ap.add_argument("--state", default="G:/_setup/_mt_loop_state.json")
ap.add_argument("--out", default=None)
A = ap.parse_args()
N = A.chapter
TXT = A.txt
STATE = A.state
OUT = A.out or ("G:/_setup/_ch%d_unit_para.json" % N)

def words(s):
    return re.findall(r"[A-Za-z][A-Za-z'\-]*", s)

t = open(TXT, encoding="utf-8", errors="replace").read()
i = t.find("Chapter %d" % N)
j = t.find("Chapter %d" % (N + 1), i + 10)
if i < 0:
    raise SystemExit("找不到 Chapter %d" % N)
if j < 0:
    j = len(t)
    print("⚠ 未找到 Chapter %d，按到文末处理" % (N + 1))
seg = t[i:j]
lines = [l.strip() for l in seg.split("\n")]
paras = [l for l in lines if l and not l.startswith("Chapter")]
print("原文章段数", len(paras))

# 词流：[(word, para_id)]
flow = []
for pid, p in enumerate(paras):
    for w in words(p):
        flow.append((w.lower(), pid))
print("原文词数", len(flow))

S = json.load(open(STATE, encoding="utf-8"))["units"]
ks = sorted(k for k, v in S.items() if v.get("ch") == "ch%d" % N)

cur = 0
rows = []
miss = 0
for k in ks:
    uw = [w.lower() for w in words(S[k]["text"])]
    if not uw:
        rows.append({"uid": k, "pid": None, "end": None})
        continue
    # 贪心：从 cur 起找 uw 的完整连续匹配，允许跳过对话词
    best = None
    for start in range(cur, min(len(flow), cur + 400)):
        if flow[start][0] != uw[0]:
            continue
        # 尝试连续匹配
        p = start
        ok = 0
        for w in uw:
            q = p
            while q < len(flow) and q < p + 6 and flow[q][0] != w:
                q += 1
            if q < len(flow) and q < p + 6 and flow[q][0] == w:
                ok += 1
                p = q + 1
            else:
                break
        if ok == len(uw):
            best = (start, p - 1)
            break
    if best is None:
        miss += 1
        rows.append({"uid": k, "pid": None, "end": None})
        continue
    a, b = best
    cur = b + 1
    rows.append({"uid": k, "pid": flow[a][1], "end": flow[b][1],
                 "w0": flow[a][0], "w1": flow[b][0]})

print("未匹配单元", miss, "/", len(ks))
ok = [r for r in rows if r["pid"] is not None]
bad = [r for r in ok if r["pid"] != r["end"]]
print("跨段单元", len(bad), [r["uid"] for r in bad][:10])

# 段末判定：本单元结束段 id 与下一单元开始段 id 不同
for n, r in enumerate(rows):
    nxt = rows[n + 1] if n + 1 < len(rows) else None
    r["para_end"] = bool(r["pid"] is not None and nxt is not None
                         and nxt["pid"] is not None and nxt["pid"] != r["end"])
pe = sum(1 for r in rows if r.get("para_end"))
print("段末单元", pe, "段内单元", len(rows) - pe)
json.dump(rows, open(OUT, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
# 抽检
for r in rows[:8]:
    print(r["uid"], "pid", r["pid"], "end", r["end"], "para_end", r.get("para_end"))
