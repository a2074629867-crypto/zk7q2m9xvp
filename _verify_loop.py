# -*- coding: utf-8 -*-
"""_verify_loop.py —— 回环全链体检（不真生成）。

检查四段是否接得上：
  ① 决策：collect_todo 挑出哪些单元该重生
  ② 选种：next_seed 给的下一个 seed 是否与已有候选不重复
  ③ 生成命令：gen_batch 的 argv 是否合法（只打印，不执行）
  ④ 挑优：pick_best 是否排除了 VOID（换人）的候选

用法：
    G:/Python310/python.exe _verify_loop.py
    G:/Python310/python.exe _verify_loop.py --units N0184,N0187
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mt_loop as L  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", default=None)
    ap.add_argument("--ch", default="ch2")
    a = ap.parse_args()

    L.load_audit()
    st = L.load_state()
    units = {x.strip() for x in a.units.split(",")} if a.units else None

    print("=" * 72)
    print("① 决策：collect_todo")
    todo = L.collect_todo(st, units=units, max_new=None, max_cand=L.MAX_CAND)
    print("   选中 %d 个单元需要重生：%s" % (len(todo), ",".join(todo[:12]) or "（无）"))

    print("\n② 选种：next_seed")
    bad = 0
    for uid in todo[:10]:
        have = [t["seed"] for t in st["units"][uid].get("tries", [])]
        s = L.next_seed(st, uid)
        ok = s is not None and str(s) not in have
        if not ok:
            bad += 1
        print("   %-6s 已有 seed=%-16s -> 下一个 %s  %s"
              % (uid, ",".join(have), s, "OK" if ok else "!! 与已有重复"))
    if not todo:
        print("   （无待重生单元，跳过）")

    print("\n③ 生成命令（只构造，不执行）")
    if todo:
        uid = todo[0]
        u = st["units"][uid]
        items = [(uid, u["text"], 1.0)]
        print("   gen_batch(items, tag='loop_s%s_%s', outdir=_mt_raw_s%s, seed=%s)"
              % (L.next_seed(st, uid), uid, L.next_seed(st, uid), L.next_seed(st, uid)))
        print("   文本：%s" % u["text"][:70])
        print("   注意：mt_gen.gen_batch 走本机 audiocpp(Vulkan)，8G 显存必 OOM；")
        print("        云端生成走 cloud/cuda/bootstrap4.sh gen，两条路径尚未打通。")
    else:
        print("   （无待重生单元）")

    print("\n④ 挑优：pick_best 是否排除 VOID")
    n_void = n_skip = 0
    for uid in (units or []):
        u = st["units"].get(uid)
        if not u:
            continue
        pick = u.get("pick")
        tries = u.get("tries", [])
        void_seeds = [t["seed"] for t in tries if L.spk_void(uid, t["seed"])]
        if void_seeds:
            n_void += 1
            chosen = pick.get("seed") if pick else None
            state = u.get("state")
            ok = chosen not in void_seeds
            # 单元本身是 ARTIFACT（全部候选换人）时，pick 只是"最不坏的记录"，
            # 不会拿去交付；真正要报警的是「状态可交付、却选中了换人候选」
            deliverable = state in ("PASS", "SKIP")
            flag = "" if ok else ("!! 选中了换人候选（但单元是 %s，不会交付）" % state
                                  if not deliverable else "!! 可交付却选中换人候选")
            if flag.startswith("!!") and deliverable:
                n_skip += 1
            print("   %-6s state=%-8s VOID=%-12s 选中=%s  %s"
                  % (uid, state, ",".join(void_seeds), chosen, flag))
    if not units:
        print("   （未指定 --units，跳过逐条检查）")

    print("\n" + "=" * 72)
    print("结论：")
    print("  ① 决策  %s" % ("OK" if todo is not None else "FAIL"))
    print("  ② 选种  %s" % ("OK" if bad == 0 else "FAIL（%d 条重复）" % bad))
    print("  ③ 生成  命令可构造；**本地/云端两条生成路径未打通**")
    print("  ④ 挑优  %s" % ("OK" if n_skip == 0 else "FAIL（%d 条选中换人）" % n_skip))


if __name__ == "__main__":
    main()
