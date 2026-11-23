# -*- coding: utf-8 -*-
"""对白版漂移判据模拟（不改源码，先用缓存 pairs 验证）
核心改动：
  1. 去掉「孤立 ΔF0」——表演对白语调起伏 5~15 半音是常态，不是音色
  2. 音色判据改为「声道形状双维」：|ln 谱质心| 且 |Δ谱倾斜| 同时超（不看 F0）
  3. 孤立单维 CEN/SLP/RMS 不再报 WARN（元音/重音）
  4. 保留 HNR 塌（气声化 = 音色消失，需求明确要抓）
  5. 声道形状双维需连续 >=2 才 FAIL，孤立降 WARN
"""
import json, os, math, collections

P = "G:/_setup"
cache = json.load(open(os.path.join(P, "_drift_cache.json"), encoding="utf-8"))
gate = {x["wav"][:-4]: x for x in json.load(open(os.path.join(P, "_gate_dlg_v29.json"), encoding="utf-8"))}

CEN_DLG, SLP_DLG = 0.60, 4.0     # 对白版声道形状阈（ln / dB·kHz^-1）
HNR_DROP, HNR_DROP_SOFT = 15.0, 9.0
HNR_EXTREME = 25.0
HOP = 0.25


def judge_dlg(x):
    pairs = x.get("pairs") or []
    if not pairs:
        return x["verdict"], []
    ev = []
    for p in pairs:
        hard, soft = [], []
        ln = abs(math.log(p["dcen"])) if p.get("dcen") else None
        slp = abs(p["dslp"]) if p.get("dslp") is not None else None
        hnr = (-p["dhnr"]) if p.get("dhnr") is not None else None
        # 声道形状双维
        if ln is not None and slp is not None and ln >= CEN_DLG and slp >= SLP_DLG:
            hard.append("声道形状 谱质心×%.2f 谱倾斜%+.1fdB" % (p["dcen"], p["dslp"]))
        # 气声化
        if hnr is not None:
            if hnr >= HNR_DROP:
                hard.append("气声化 HNR-%.1fdB" % hnr)
            elif hnr >= HNR_DROP_SOFT:
                soft.append("HNR-%.1fdB" % hnr)
        if hard:
            ev.append(dict(level="FAIL", t=p["t"], why=hard, hnr=hnr))
        elif soft:
            ev.append(dict(level="WARN", t=p["t"], why=soft, hnr=hnr))
    # 基频丢失沿用原产物（缓存 events 里带）
    for e in (x.get("events") or []):
        if any("基频丢失" in w for w in e["why"]):
            ev.append(dict(level=e["level"], t=e["t"], why=e["why"], hnr=None))
    ev.sort(key=lambda e: e["t"])
    fails = [e for e in ev if e["level"] == "FAIL"]
    if not fails:
        return ("WARN" if ev else "PASS"), ev
    # 声道形状双维要求连续；HNR 极端单次即判
    def extreme(e):
        return (e.get("hnr") or 0) >= HNR_DROP or any("基频丢失" in w and "3 窗" in w for w in e["why"])
    cons = any(abs(fails[i + 1]["t"] - fails[i]["t"]) <= HOP * 1.5 for i in range(len(fails) - 1))
    if cons or any(extreme(e) for e in fails):
        return "FAIL", ev
    for e in fails:
        e["level"] = "WARN"
        e["why"] = ["孤立:" + w for w in e["why"]]
    return "WARN", ev


def band(t):
    if t < 1.2: return "a_<1.2s"
    if t < 3.75: return "b_1.2~3.75s"
    if t < 6: return "c_3.75~6s"
    if t < 10: return "d_6~10s"
    return "e_>=10s"


rows = []
for x in cache:
    sid = os.path.basename(x["file"])[:-4]
    if sid not in gate:
        continue
    v, ev = judge_dlg(x)
    rows.append((sid, x["dur"], x["verdict"], v, ev))

print("=== 旧 vs 新（对白 239 条）===")
print("旧:", dict(collections.Counter(r[2] for r in rows)))
print("新:", dict(collections.Counter(r[3] for r in rows)))
print()
print("%-12s %5s | %-34s | %s" % ("时长档", "n", "旧", "新"))
for b in ["a_<1.2s", "b_1.2~3.75s", "c_3.75~6s", "d_6~10s", "e_>=10s"]:
    sub = [r for r in rows if band(r[1]) == b]
    if not sub: continue
    print("%-12s %5d | %-34s | %s" % (b, len(sub),
          dict(collections.Counter(r[2] for r in sub)), dict(collections.Counter(r[3] for r in sub))))
print()
print("=== 新 FAIL 明细 ===")
for sid, dur, ov, nv, ev in rows:
    if nv == "FAIL":
        print("  %-10s %5.1fs [旧 %s] %s" % (sid, dur, ov, "；".join(
            "%s@%.2f %s" % (e["level"], e["t"], "/".join(e["why"])) for e in ev if e["level"] == "FAIL")[:110]))
print()
print("=== 旧 WARN → 新 PASS（被正确剔除的语调噪声）%d 条 ===" %
      sum(1 for r in rows if r[2] == "WARN" and r[3] == "PASS"))
print(" ".join(r[0] for r in rows if r[2] == "WARN" and r[3] == "PASS"))
print()
print("=== 旧 PASS → 新 WARN/FAIL（新抓到的）%d 条 ===" %
      sum(1 for r in rows if r[2] == "PASS" and r[3] != "PASS"))
for r in rows:
    if r[2] == "PASS" and r[3] != "PASS":
        print("  %-10s %5.1fs -> %s  %s" % (r[0], r[1], r[3],
              "；".join("/".join(e["why"]) for e in r[4])[:100]))
json.dump([dict(id=r[0], dur=round(r[1], 2), old=r[2], new=r[3], events=r[4]) for r in rows],
          open(os.path.join(P, "_drift_dlg_v1.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n写出 _drift_dlg_v1.json")
