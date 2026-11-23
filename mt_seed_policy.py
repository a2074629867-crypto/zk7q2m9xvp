# -*- coding: utf-8 -*-
"""mt_seed_policy.py —— 用户指定的分级生成工作流（2026-10-29）

    ① 每条文本用 2 个 seed 各生成一遍（**不加 pitch / rate 标签**）
    ② 检测 → 两个 take 取最佳
    ③ 未达标（韵律平 / 关键重音没读到）→ 再生成 1 个 seed → 再取最佳
    ④ 第 3 遍仍未达标 → 这才允许加 pitch / rate

本脚本不负责生成（生成在云端走 cloud/gen_http.py），只负责三件事：

  1. **plan**：读现有 take 目录，判定每条已走到第几级、下一级该做什么
  2. **measure**：缺 prom 自动补（`_prom_build.py`），再批量测量（`_adv_prom.py`）
  3. **select**：用**同一把尺子**挑赢家（默认 rel_z ≥ 1.6 + 硬缺陷否决），
     并把 attempts（stage / seed / tagged / rel_z / 淘汰理由）落盘

为什么必须同一把尺子：之前出现过「用 A 指标挑赢家、用 B 指标验收」，
结果挑出来的 take 在验收里又不合格，白跑一轮。

用法
----
    # 看现在每条走到哪一级（不生成）
    python mt_seed_policy.py --plan

    # 回算：把已有 seed 当分级用，看第 N 遍的累计通过率
    python mt_seed_policy.py --simulate --seeds 2061,2063,2065,2067

    # 指定阶段推进（第 3 级只对失败项生效）
    python mt_seed_policy.py --plan --stage1 2061,2063 --stage3 2065

产物
----
    _policy_plan.json   每条 uid 的 stage / 候选 / 结论 / 下一步
    _pol_res_<dir>.json 每批测量原始结果（缓存，可复用）
"""
import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = "G:/_setup"
PY = os.path.join(ROOT, "..", "Python310", "python.exe")
PY = "G:/Python310/python.exe"
PASS_Z = 1.6          # 时长轴判据（rel_z）
ABSENT_VOICED = 0.06  # 硬缺陷：根本没出声
STATE = os.path.join(ROOT, "_mt_adv_state.json")
PLAN_OUT = os.path.join(ROOT, "_policy_plan.json")


def log(m):
    print(m, flush=True)


def load_units():
    st = json.load(open(STATE, encoding="utf-8"))
    return st["units"]


def take_dir(seed, tagged=False):
    """tagged=False → _mt_adv_ctl_<seed>；True → _mt_adv_s<seed>（历史命名）。"""
    d = "_mt_adv_s%d" % seed if tagged else "_mt_adv_ctl_%d" % seed
    return d if os.path.isdir(os.path.join(ROOT, d)) else None


def prom_dir(d):
    """_mt_adv_ctl_2061 → _mt_adv_prom_2061（prom 与 wav 目录一一对应）。"""
    return os.path.join(ROOT, "_mt_adv_prom_" + d.split("_")[-1])


def ensure_prom(d, uids):
    """缺 prom 就补（ASR → TextGrid）。返回 {uid: prom 路径}。"""
    pd = prom_dir(d)
    os.makedirs(pd, exist_ok=True)
    have = {}
    need = []
    for u in sorted(uids):
        p = os.path.join(pd, "%s__%s.prom" % (d, u))
        if os.path.exists(p):
            have[u] = p
        else:
            need.append(u)
    if need:
        log("  补 prom %d 条（%s）..." % (len(need), d))
        subprocess.run([PY, os.path.join(ROOT, "_prom_build.py"),
                        "--prefix", d, "--dir", d,
                        "--units", ",".join(need), "--prom-out", pd],
                       cwd=ROOT, capture_output=True, text=True, timeout=3600)
        for u in need:
            p = os.path.join(pd, "%s__%s.prom" % (d, u))
            if os.path.exists(p):
                have[u] = p
    return have


def measure(d, units, uids):
    """对目录 d 测量指定 uid，结果缓存到 _pol_res_<d>.json。"""
    out = os.path.join(ROOT, "_pol_res_%s.json" % d)
    if os.path.exists(out):
        return {str(x["uid"]): x for x in json.load(open(out, encoding="utf-8"))}
    pms = ensure_prom(d, uids)
    items = []
    for u in uids:
        w = os.path.join(ROOT, d, u + ".wav")
        if u not in pms or not os.path.exists(w):
            continue
        x = units[u]
        items.append(dict(uid=u, text=x["text"], wav=w, prom=pms[u],
                          advs=x.get("advs") or [x["adv"]]))
    if not items:
        return {}
    man = os.path.join(ROOT, "_pol_man_%s.json" % d)
    json.dump(items, open(man, "w", encoding="utf-8"), ensure_ascii=False)
    log("  测量 %d 条（%s）..." % (len(items), d))
    subprocess.run([PY, os.path.join(ROOT, "_adv_prom.py"),
                    "--batch", man, "--out", out],
                   cwd=ROOT, capture_output=True, text=True, timeout=3600)
    if not os.path.exists(out):
        log("  !! 测量失败 %s" % d)
        return {}
    return {str(x["uid"]): x for x in json.load(open(out, encoding="utf-8"))}


def verdict(rec):
    """单一判据：硬缺陷否决 → rel_z 过线。返回 (ok, 理由)。"""
    if rec is None:
        return False, "无测量"
    v = rec.get("voiced") or 0
    if v < ABSENT_VOICED:
        return False, "ABSENT 有声仅 %.2fs" % v
    rz = rec.get("rel_z")
    if rz is None:
        return False, "rel_z 不可测"
    if rz >= PASS_Z:
        return True, "rel_z=%.2f ≥ %.1f" % (rz, PASS_Z)
    return False, "rel_z=%.2f < %.1f" % (rz, PASS_Z)


def sim(units, seeds, tagged=False):
    """把 seeds 依次当作 stage1(前2) / stage3(第3) 回算累计通过率。"""
    d0 = take_dir(seeds[0], tagged)
    if not d0:
        log("无目录 %s" % seeds[0])
        return []
    # 只统计**真的有 wav** 的条目：已交付的 6 条不在回环里，不能算失败
    uids = [u for u in sorted(units)
            if os.path.exists(os.path.join(ROOT, d0, u + ".wav"))]
    cand = {}
    rows = []
    for i, s in enumerate(seeds, 1):
        d = take_dir(s, tagged)
        if not d:
            log("skip seed %s（无目录）" % s)
            continue
        res = measure(d, units, uids)
        for u in uids:
            r = res.get(u)
            if r:
                cand.setdefault(u, []).append((i, s, r))
        # 每加一个 seed 就重算「最佳」
        passed = 0
        for u in uids:
            best = None
            for i2, s2, r in cand.get(u, []):
                if best is None or (r.get("rel_z") or -9) > (best[2].get("rel_z") or -9):
                    best = (i2, s2, r)
            ok, _ = verdict(best[2] if best else None)
            passed += 1 if ok else 0
        rows.append((i, s, len(uids), passed, 100.0 * passed / max(1, len(uids))))
    log("\n分级累计通过率（rel_z ≥ %.1f，%s）" % (PASS_Z, "tag" if tagged else "ctl"))
    log("| 第几遍 | seed | 条数 | 累计通过 | 通过率 |")
    log("|---|---|---|---|---|")
    for i, s, n, p, pct in rows:
        log("| %d | %d | %d | %d | %.1f%% |" % (i, s, n, p, pct))
    if len(rows) >= 2:
        d2 = rows[1][3]
        left = rows[1][2] - d2
        log("\n按用户工作流（2 seed 起跑）：第 3 级需再生 **%d** 条；"
            "第 4 级（加标签）最多 **%d** 条。" % (left, left))
    return rows


def build_plan(units, stage1, stage3, stage4):
    """按 stage 序列逐级推进，产出 _policy_plan.json。"""
    uids = sorted(units)
    plan = {}
    cand = {}
    for tag4, seeds in (("s1", stage1), ("s3", stage3), ("s4", stage4)):
        for s in seeds:
            d = take_dir(s, tagged=(tag4 == "s4"))
            if not d:
                continue
            res = measure(d, units, uids)
            for u in uids:
                r = res.get(u)
                if r:
                    cand.setdefault(u, []).append(dict(stage=tag4, seed=s, rel_z=r.get("rel_z"),
                                                       loc=r.get("loc"), voiced=r.get("voiced")))
    for u in uids:
        att = cand.get(u, [])
        # stage1 只看前两遍；不够再算 stage3；再不够才算 stage4
        s1 = [a for a in att if a["stage"] == "s1"]
        s3 = [a for a in att if a["stage"] == "s3"]
        s4 = [a for a in att if a["stage"] == "s4"]
        best = max(s1, key=lambda a: a["rel_z"] or -9) if s1 else None
        if best and (best["rel_z"] or -9) >= PASS_Z:
            plan[u] = dict(uid=u, stage="s1-pass", best=best, attempts=att, next="收")
            continue
        pool = s1 + s3
        b2 = max(pool, key=lambda a: a["rel_z"] or -9) if pool else None
        if b2 and (b2["rel_z"] or -9) >= PASS_Z:
            plan[u] = dict(uid=u, stage="s3-pass", best=b2, attempts=att, next="收")
            continue
        if not s4:
            plan[u] = dict(uid=u, stage="need-s3" if not s3 else "need-s4",
                           best=b2, attempts=att,
                           next="generate-seed3" if not s3 else "generate-tagged")
            continue
        b3 = max(s1 + s3 + s4, key=lambda a: a["rel_z"] or -9)
        ok = (b3["rel_z"] or -9) >= PASS_Z
        plan[u] = dict(uid=u, stage="s4-pass" if ok else "s4-fail", best=b3,
                       attempts=att, next="收" if ok else "标记轴已到顶")
    json.dump(plan, open(PLAN_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    c = Counter(v["stage"] for v in plan.values())
    log("\n计划（%d 条）→ %s" % (len(plan), PLAN_OUT))
    for k, n in sorted(c.items()):
        log("  %-10s %d" % (k, n))
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--tag", action="store_true", help="simulate 时用 tag 目录")
    ap.add_argument("--seeds", default="", help="逗号分隔，按级顺序")
    ap.add_argument("--stage1", default="")
    ap.add_argument("--stage3", default="")
    ap.add_argument("--stage4", default="")
    a = ap.parse_args()

    units = load_units()
    if a.simulate:
        seeds = [int(x) for x in a.seeds.split(",") if x.strip()]
        if len(seeds) < 2:
            log("simulate 至少给 2 个 seed（第 1 级就是 2 个）")
            return 1
        sim(units, seeds, tagged=a.tag)
        return 0
    if a.plan:
        s1 = [int(x) for x in a.stage1.split(",") if x.strip()]
        s3 = [int(x) for x in a.stage3.split(",") if x.strip()]
        s4 = [int(x) for x in a.stage4.split(",") if x.strip()]
        if len(s1) != 2:
            log("stage1 必须正好 2 个 seed（用户工作流第 ① 步）")
            return 2
        build_plan(units, s1, s3, s4)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
