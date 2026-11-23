# -*- coding: utf-8 -*-
"""音色稳定性链路 —— 阳性/阴性对照实测（2026-11-14 14:0x）

用户问：链路里会不会有环节没接上、或以前做好的丢了，导致检测不出音色不稳。
这个脚本不看代码，直接拿 189 条有 ground truth 的拼接样本打当前生产判据
（`gate_intra.check`，就是 dialog_gate 第 4 闸调的那一个）：

  POS_hard 60 / POS_soft 60  —— 换人拼接，**必须检出**（漏检 = 链路有洞）
  NEG_emo  39 / NEG_real 30  —— 同人不同情绪 / 真实整句，**不该检出**（误报 = 尺子太松）

输出：分 kind 的检出率、误报率、定位误差，以及漏检清单。
"""
import sys, os, json, collections

sys.path.insert(0, r"G:/_setup")
sys.path.insert(0, r"G:/_setup/emo_bench")
os.chdir(r"G:/_setup")

import gate_intra as G

IDX = json.load(open("_mutbench/index.json", encoding="utf-8"))
out = []
for i, it in enumerate(IDX, 1):
    wav = "_mutbench/wav/%s.wav" % it["sid"]
    if not os.path.exists(wav):
        out.append(dict(sid=it["sid"], kind=it["kind"], err="missing"))
        continue
    try:
        v, info = G.check(wav)
    except Exception as e:
        out.append(dict(sid=it["sid"], kind=it["kind"], err="%s: %s" % (type(e).__name__, e)))
        continue
    hit = bool((info or {}).get("code") in ("intra_severe", "intra_switch", "intra_drift"))
    out.append(dict(sid=it["sid"], kind=it["kind"], verdict=v,
                    code=(info or {}).get("code"),
                    sep=(info or {}).get("sep"), k=(info or {}).get("k"),
                    drift=(info or {}).get("drift_state"),
                    hit=hit, cut=it.get("cut"), pos=(info or {}).get("pos")))
    if i % 20 == 0:
        print("  %d/%d" % (i, len(IDX)), flush=True)

json.dump(out, open("_timbre_verify.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

print("\n=== 分 kind 结果 ===")
print("%-10s %4s %6s %6s %8s" % ("kind", "n", "检出", "漏检", "检出率"))
for kind in ["POS_hard", "POS_soft", "NEG_emo", "NEG_real"]:
    rows = [x for x in out if x.get("kind") == kind and not x.get("err")]
    hit = sum(1 for x in rows if x["hit"])
    print("%-10s %4d %6d %6d %7.1f%%" % (kind, len(rows), hit, len(rows) - hit,
                                         100.0 * hit / max(1, len(rows))))

pos = [x for x in out if x.get("kind", "").startswith("POS") and not x.get("err")]
neg = [x for x in out if x.get("kind", "").startswith("NEG") and not x.get("err")]
print("\n合计：换人检出 %d/%d = %.1f%% ｜ 正常误报 %d/%d = %.1f%%"
      % (sum(1 for x in pos if x["hit"]), len(pos), 100.0 * sum(1 for x in pos if x["hit"]) / max(1, len(pos)),
         sum(1 for x in neg if x["hit"]), len(neg), 100.0 * sum(1 for x in neg if x["hit"]) / max(1, len(neg))))

err = [x for x in out if x.get("err")]
if err:
    print("\n异常 %d 条：%s" % (len(err), err[:3]))

miss = [x for x in pos if not x["hit"]]
print("\n漏检的换人样本 %d 条（前 15）：" % len(miss))
for x in miss[:15]:
    print("  %-14s k=%-4s sep=%-6s drift=%s" % (x["sid"], x.get("k"), x.get("sep"), x.get("drift")))
