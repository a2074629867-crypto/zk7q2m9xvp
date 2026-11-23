# -*- coding: utf-8 -*-
"""按 voice 名（Who_emo_N）解析到 _emo_refs_all.json 的下标，检查档是否真的存在。
这是 C 类「档已补齐」结论的直接验证。"""
import json, os, collections

LIB = r"G:/_setup/_emo_refs_all.json"
GATE = r"G:/_setup/_gate_dlg_v27.json"
lib = json.load(open(LIB, encoding="utf-8"))
gate = json.load(open(GATE, encoding="utf-8"))

print("库内档位容量：")
for who in lib:
    row = ", ".join("%s=%d" % (e, len(v)) for e, v in lib[who].items())
    print("  %-9s %s" % (who, row))

codes_of = lambda x: {r["code"] for r in x["reasons"]}
need = [x for x in gate
        if x["verdict"] == "REGEN"
        or codes_of(x) & {"intra_severe", "intra_switch", "intra_drift", "scs_outlier",
                          "nat_fail", "ref_fallback", "ref_poor"}]

print("\n需动音频 %d 条 —— 逐条解析 voice：" % len(need))
bad = []
for x in sorted(need, key=lambda z: z["wav"]):
    v = x.get("voice") or ""
    parts = v.rsplit("_", 1)
    ok, note = False, ""
    if len(parts) == 2 and parts[1].isdigit():
        stem, idx = parts[0], int(parts[1]) - 1
        # stem 形如 Thomas_begging，但 who 可能是多词？按 _ 从左切
        who = None
        for w in lib:
            if stem.startswith(w + "_"):
                who = w
                break
        if who:
            emo = stem[len(who) + 1:]
            arr = lib.get(who, {}).get(emo, [])
            if idx < len(arr):
                p = arr[idx].get("path")
                ok = bool(p and os.path.exists(p))
                note = "%s/%s[%d] %s" % (who, emo, idx, "存在" if ok else "路径缺失")
            else:
                note = "%s/%s[%d] 越界（库内仅 %d 条）" % (who, emo, idx, len(arr))
        else:
            note = "who 解析失败"
    else:
        note = "voice 名不规范"
    if not ok:
        bad.append((x["wav"], v, note))
    print("  %-12s %-22s %s" % (x["wav"], v, note))

print("\n档位不可用：%d 条" % len(bad))
