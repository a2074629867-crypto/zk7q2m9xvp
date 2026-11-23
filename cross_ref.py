#!/usr/bin/env python
"""跨片冷启动验证：换一部完全不相干的片子，从零建 ref 库，再看判定准不准。

为什么这么设计：
  · 城堡之王那片有手工建好的 8 档 ref 库，但那是为那部片调的。换片必须从零建。
  · 本片（Careful, He Might Hear You 1983）的字幕自带 `[PS]` `[Vanessa]` 这类
    角色名标注（69/1243 = 6%），这是**免费真值**，正好能算准确率而不是「看起来对」。
  · ref 用确定性规则挑（每角色按时间均匀取 3 条，不在「最像的」里面挑），
    避免选择偏差把结果做乐观。

用法：
  G:/Python310/python.exe cross_ref.py --cues crosscut/cues/cues.json --per-role 3
"""
import argparse
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/voice_lib")

from chain_check import EmoVoice  # noqa: E402

TAG = re.compile(r"^\s*-?\s*\[([^\]]{2,20})\]\s*")


def load_tagged(path):
    """从 cues.json 里取带 [名字] 标注的 cue，剥掉标注得到纯台词。"""
    cues = json.load(open(path, encoding="utf-8"))
    out = []
    for c in cues:
        m = TAG.match(c["text"])
        if not m:
            continue
        role = m.group(1).strip()
        text = TAG.sub("", c["text"]).lstrip("- ").strip()
        if not text:
            continue
        out.append({"role": role, "text": text, "path": c["path"].replace("\\", "/"),
                    "t0": c["t0"], "dur": c["dur"], "multi": c["multi"], "sfx": c["sfx"]})
    return cues, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cues", default="crosscut/cues/cues.json")
    ap.add_argument("--per-role", type=int, default=3, help="每个角色拿几条建 ref")
    ap.add_argument("--min-n", type=int, default=6, help="角色至少多少条才参与")
    ap.add_argument("--min-dur", type=float, default=1.2,
                    help="ref 候选最短时长。别用建库默认 1.8s —— 冷启动时短句（\"Come in.\"）"
                         "是干净的单人素材，卡 1.8s 会把 Vanessa 11 条挡掉 7 条")
    ap.add_argument("--max-dur", type=float, default=8.0)
    ap.add_argument("--bg-n", type=int, default=300, help="背景集条数（估 Z-norm μ/σ）")
    ap.add_argument("--out-lib", default="crosscut/cross_lib.json")
    ap.add_argument("--out-bg", default="crosscut/cross_bg.json")
    ap.add_argument("--out", default="out/cross_eval.json")
    a = ap.parse_args()

    allcues, tagged = load_tagged(a.cues)
    roles = {}
    for r in tagged:
        roles.setdefault(r["role"], []).append(r)
    print("带标注 %d 条，角色:" % len(tagged))
    for k, v in sorted(roles.items(), key=lambda x: -len(x[1])):
        print("   %-12s %d" % (k, len(v)))

    # 只取条数够的主角色；时长/多人过滤
    main_roles = {k: [r for r in v if not r["multi"] and not r["sfx"]
                      and a.min_dur <= r["dur"] <= a.max_dur]
                  for k, v in roles.items() if len(v) >= a.min_n}
    main_roles = {k: v for k, v in main_roles.items() if len(v) >= a.per_role + 2}
    print("\n参与验证的角色（干净且够数）:")
    for k, v in sorted(main_roles.items(), key=lambda x: -len(x[1])):
        print("   %-12s %d" % (k, len(v)))
    if not main_roles:
        sys.exit("没有角色满足条件，放宽 --min-n 或 --per-role")

    # ref：按时间均匀取，避免「挑最像的」造成乐观偏差
    lib, tests = {}, []
    for role, items in main_roles.items():
        items = sorted(items, key=lambda r: r["t0"])
        idx = np.linspace(0, len(items) - 1, a.per_role).astype(int)
        refs = [items[i] for i in idx]
        lib[role] = {"neutral": [{"path": r["path"], "text": r["text"]} for r in refs]}
        rest = [r for j, r in enumerate(items) if j not in set(idx.tolist())]
        tests += [dict(r, gt=role) for r in rest]

    os.makedirs(os.path.dirname(a.out_lib), exist_ok=True)
    json.dump(lib, open(a.out_lib, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nref 库 %d 角色 / %d 条 -> %s" % (
        len(lib), sum(len(v["neutral"]) for v in lib.values()), a.out_lib))
    for role, v in lib.items():
        print("  %-12s" % role, [os.path.basename(x["path"]) for x in v["neutral"]])

    # 背景集：用本片自己的对白估 μ/σ（不能借别片的，片源/语言/录音全不同）
    clean = [c for c in allcues if 1.0 <= c["dur"] <= 10.0]
    idx = np.linspace(0, len(clean) - 1, min(a.bg_n, len(clean))).astype(int)
    bg = [{"path": clean[i]["path"].replace("\\", "/")} for i in idx]
    json.dump(bg, open(a.out_bg, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("背景集 %d 条 -> %s" % (len(bg), a.out_bg))

    print("\n建库中（%d 模板 + %d 背景，首次要算 μ/σ）…" % (
        sum(len(v["neutral"]) for v in lib.values()), len(bg)), flush=True)
    ev = EmoVoice(model="r34", lib=a.out_lib, bg=a.out_bg)

    # 建库自检：同角色不同句子之间的余弦 —— 这是「声纹在这批音频上到底有没有用」
    # 的直接证据。实测城堡片（现代 WEB-DL）同角色 0.495，Careful（1983 DVD 转录）
    # 只有 0.245，而那片的判定 AUC 是 0.482（等于随机）。低于 0.35 就别往下判了，
    # 判出来的数字没有意义。
    by_role = {}
    for role, v in lib.items():
        by_role[role] = [ev.m.embed(it["path"]) for it in v["neutral"]]
    selfcos = []
    for role, es in by_role.items():
        for i in range(len(es)):
            for j in range(i + 1, len(es)):
                selfcos.append(float(es[i] @ es[j]))
    same_med = float(np.median(selfcos)) if selfcos else 0.0
    print("\n=== 建库自检：同角色不同句子的余弦中位 %.3f ===" % same_med)
    if same_med < 0.35:
        print("  ⚠ 低于 0.35 —— 声纹模型在这批音频上不可靠（实测这种片子的判定 AUC≈0.48，等于随机）。")
        print("    常见原因是片源太老 / 码率太低 / 高频缺失。继续判只能得到假结论，")
        print("    这一片请改人工判定，或换更好的片源。")
    else:
        print("  ✓ 模型可用（城堡片现代 WEB-DL 为 0.495）")

    print("判定 %d 条测试音频 …" % len(tests), flush=True)
    rows = []
    for i, t in enumerate(tests):
        r = ev.check(t["path"])
        rows.append({"file": os.path.basename(t["path"]), "gt": t["gt"], "pred": r["role"],
                     "ok": r["role"] == t["gt"], "z1": r["z1"], "margin": r["margin"],
                     "role_z": r["role_z"], "text": t["text"][:70]})
        if (i + 1) % 10 == 0:
            print("  %d/%d" % (i + 1, len(tests)), flush=True)

    n = len(rows)
    acc = sum(r["ok"] for r in rows) / n
    print("\n=== 跨片冷启动 准确率 %d/%d = %.0f%% ===" % (sum(r["ok"] for r in rows), n, 100 * acc))
    print("\n分角色:")
    for role in sorted(main_roles):
        sub = [r for r in rows if r["gt"] == role]
        if sub:
            print("  %-12s %2d 条  判对 %2d  (%.0f%%)" % (
                role, len(sub), sum(r["ok"] for r in sub), 100 * sum(r["ok"] for r in sub) / len(sub)))

    # 用 |role_z| 做拒识：分不开的就该说分不开，而不是硬判
    print("\n=== 加拒识（|role_z| 阈值）后的精度/覆盖率 ===")
    for T in (0.4, 0.6, 0.8, 1.0):
        keep = [r for r in rows if abs(r["role_z"]) >= T]
        if not keep:
            print("  >=%.1f 无" % T)
            continue
        right = sum(r["ok"] for r in keep)
        print("  |role_z|>=%.1f  放行 %2d/%d (%.0f%%)  精度 %.0f%%" % (
            T, len(keep), n, 100 * len(keep) / n, 100 * right / len(keep)))

    wrong = [r for r in rows if not r["ok"]]
    if wrong:
        print("\n=== 判错 %d 条 ===" % len(wrong))
        for r in wrong:
            print("  真值 %-10s 判成 %-10s role_z %+5.2f  %s" % (
                r["gt"], r["pred"], r["role_z"], r["text"][:52]))

    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写 ->", a.out)


if __name__ == "__main__":
    main()
