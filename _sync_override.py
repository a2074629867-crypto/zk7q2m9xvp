# -*- coding: utf-8 -*-
"""按 state 里的 active 字段，重写 mt_post.OVERRIDE。

为什么需要：`cmd_adopt --apply` 会把采纳版写进 `_mt_pick/<uid>.wav`，
但 `mt_repick` / `mt_score` 重跑时会按打分重新挑 take，把采纳版覆盖掉。
`mt_post.OVERRIDE` 就是防这个的。手写容易漏，所以从 state 生成。

用法：
    python _sync_override.py            # 只看
    python _sync_override.py --apply
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STATE = os.path.join(HERE, "_mt_adv_state.json")
POST = os.path.join(HERE, "mt_post.py")


def build():
    st = json.load(open(STATE, encoding="utf-8"))["units"]
    rows = {}
    for u, x in sorted(st.items()):
        act = x.get("active") or {}
        w = act.get("wav")
        if w and os.path.exists(w):
            rows[u] = w
    return rows


def render(rows):
    lines = ["OVERRIDE = {"]
    for u, w in rows.items():
        lines.append('    "%s": os.path.join(ROOT, "%s", "%s.wav"),'
                     % (u, os.path.basename(os.path.dirname(w)), u))
    lines.append("}")
    return "\n".join(lines)


def main():
    rows = build()
    print("state 里 active 的单元：%d" % len(rows))
    for u, w in rows.items():
        print("  %-7s %s" % (u, os.path.relpath(w, HERE)))
    if "--apply" not in sys.argv:
        print("\n[dry-run] 加 --apply 才写 mt_post.py")
        return
    s = io.open(POST, encoding="utf-8").read()
    i = s.index("OVERRIDE = {")
    # 找到与它配对的右花括号
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                j += 1
                break
        j += 1
    s = s[:i] + render(rows) + s[j:]
    io.open(POST, "w", encoding="utf-8").write(s)
    print("\n已重写 mt_post.OVERRIDE（%d 条）" % len(rows))


if __name__ == "__main__":
    main()
