# -*- coding: utf-8 -*-
"""参考音库体检：留一法自证强度（gap）。

为什么不用「动态范围 / 低频占比」这类音频质量指标：
- 全库 70 条 dyn 中位只有 13.9dB，按 25dB 卡会杀掉九成；
- Joseph 是 116Hz 低音男声，low300 中位 0.59，按 55% 卡会整档误杀。
两类指标都区分不出真正失效的那条（Charles/soft 三条的 dyn 是 9.9/11.2/11.3，几乎一样）。

真正有效的判据是 gap：
    gap = 与同角色其他条目的最高余弦  −  与其他所有角色的最高余弦
gap < 0 表示「这条更像别人」，是唯一能直接对应「它是不是这个人」的量。

实测 70 条模板：
    gap 0 分位 -0.092 / 5 分位 +0.097 / 25 分位 +0.255 / 中位 +0.364
    唯一负值就是 Charles/soft 的那条，其余 69 条全正。
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_lib(path):
    lib = json.load(open(path, encoding="utf-8"))
    rows = []
    for role, slots in lib.items():
        for slot, items in slots.items():
            for it in items:
                p = it["path"] if isinstance(it, dict) else it
                if not os.path.exists(p):
                    continue
                rows.append({
                    "role": role,
                    "slot": slot,
                    "path": p,
                    "id": it.get("id", "") if isinstance(it, dict) else "",
                    "text": it.get("text", "") if isinstance(it, dict) else "",
                    "raw": it,
                })
    return lib, rows


def embeddings(paths, model="r34", cache="out_sv/_refqa_cache.npz"):
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    hit = {}
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        hit = dict(zip(list(z["files"]), z["E"]))
    need = [p for p in paths if p not in hit]
    if need:
        from sv_onnx import SV
        sv = SV(name=model)
        for i, p in enumerate(need, 1):
            hit[p] = sv.embed(p)
            if i % 20 == 0:
                print("  embed %d/%d" % (i, len(need)), flush=True)
        np.savez(cache, files=np.array(list(hit.keys()), dtype=object),
                 E=np.array(list(hit.values()), dtype=np.float32))
    E = np.array([hit[p] for p in paths], dtype=np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    return E


def audit(lib_path, model="r34", gap_reject=0.0, gap_warn=0.10):
    lib, rows = load_lib(lib_path)
    print("载入 %d 条模板，%d 个角色" % (len(rows), len(lib)), flush=True)
    E = embeddings([r["path"] for r in rows], model=model)

    out = []
    for i, r in enumerate(rows):
        sims = E @ E[i]
        same = [k for k in range(len(rows)) if rows[k]["role"] == r["role"] and k != i]
        other = [k for k in range(len(rows)) if rows[k]["role"] != r["role"]]
        if not same:
            top1 = top3 = gap = float("nan")
            cross = float(sims[other].max()) if other else float("nan")
        else:
            s = np.sort(sims[same])[::-1]
            top1 = float(s[0])
            top3 = float(s[: min(3, len(s))].mean())
            cross = float(sims[other].max()) if other else 0.0
            gap = top1 - cross
        verdict = ("REJECT" if gap < gap_reject else
                   "WARN" if gap < gap_warn else "OK")
        out.append(dict(r, top1=top1, top3=top3, cross=cross, gap=gap, verdict=verdict))
    return out


def report(out, gap_reject, gap_warn):
    print("\n%-9s %-9s %-7s %6s %6s %6s %6s  %s" %
          ("role", "slot", "verdict", "top1", "top3", "cross", "gap", "text"))
    print("-" * 100)
    for r in sorted(out, key=lambda x: (x["role"], x["slot"], x["gap"])):
        print("%-9s %-9s %-7s %6.3f %6.3f %6.3f %+6.3f  %s" % (
            r["role"], r["slot"], r["verdict"], r["top1"], r["top3"],
            r["cross"], r["gap"], r["text"][:40]))

    print("\n=== 逐角色 ===")
    roles = []
    for r in out:
        if r["role"] not in roles:
            roles.append(r["role"])
    for role in roles:
        sub = [r for r in out if r["role"] == role]
        g = np.array([r["gap"] for r in sub])
        bad = [r for r in sub if r["verdict"] == "REJECT"]
        warn = [r for r in sub if r["verdict"] == "WARN"]
        print("  %-9s n=%2d  gap 中位 %+.3f  最低 %+.3f  REJECT %d  WARN %d" % (
            role, len(sub), np.median(g), g.min(), len(bad), len(warn)))

    print("\n=== 分档健康度（每档 n / gap 最低） ===")
    for role in roles:
        for slot in dict.fromkeys(r["slot"] for r in out if r["role"] == role):
            sub = [r for r in out if r["role"] == role and r["slot"] == slot]
            g = np.array([r["gap"] for r in sub])
            flag = "" if g.min() >= gap_warn else "  <-- 有隐患"
            print("  %-9s %-9s n=%d  gap min %+.3f%s" % (role, slot, len(sub), g.min(), flag))

    n_rej = sum(1 for r in out if r["verdict"] == "REJECT")
    n_warn = sum(1 for r in out if r["verdict"] == "WARN")
    g = np.array([r["gap"] for r in out])
    print("\n=== 汇总 ===")
    print("  通过 %d / WARN %d / REJECT %d   共 %d" % (len(out) - n_rej - n_warn, n_warn, n_rej, len(out)))
    print("  gap 分位: " + "  ".join("%s=%+.3f" % (p, np.percentile(g, p))
                                     for p in (0, 5, 25, 50, 75, 100)))
    return n_rej, n_warn


def write_clean(lib_path, out, drop, dst):
    lib = json.load(open(lib_path, encoding="utf-8"))
    dropset = {(r["role"], r["slot"], r["path"]) for r in drop}
    print("\n=== 清理：删除 %d 条 ===" % len(dropset))
    for role in list(lib.keys()):
        for slot in list(lib[role].keys()):
            kept = []
            for it in lib[role][slot]:
                p = it["path"] if isinstance(it, dict) else it
                if (role, slot, p) in dropset:
                    print("  - %-9s %-9s %s" % (role, slot, it.get("text", "")[:44]))
                    continue
                kept.append(it)
            if kept:
                lib[role][slot] = kept
            else:
                print("  ! %s/%s 全空，整档移除" % (role, slot))
                del lib[role][slot]
    json.dump(lib, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(len(v) for r in lib.values() for v in r.values())
    print("  写出 %s  角色 %d  模板 %d" % (dst, len(lib), n))
    for r, sl in lib.items():
        print("    %-9s %s" % (r, "  ".join("%s:%d" % (k, len(v)) for k, v in sl.items())))
    return lib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True)
    ap.add_argument("--model", default="r34")
    ap.add_argument("--gap-reject", type=float, default=0.0,
                    help="gap 低于此值判 REJECT（默认 0：更像别人）")
    ap.add_argument("--gap-warn", type=float, default=0.10,
                    help="gap 低于此值判 WARN")
    ap.add_argument("--clean", action="store_true", help="按 REJECT 清理并写出")
    ap.add_argument("--out", default="", help="清理后的库路径")
    a = ap.parse_args()

    out = audit(a.lib, model=a.model, gap_reject=a.gap_reject, gap_warn=a.gap_warn)
    report(out, a.gap_reject, a.gap_warn)
    if a.clean:
        dst = a.out or a.lib.replace(".json", "_clean.json")
        write_clean(a.lib, out, [r for r in out if r["verdict"] == "REJECT"], dst)


if __name__ == "__main__":
    main()
