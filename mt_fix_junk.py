# -*- coding: utf-8 -*-
"""mt_fix_junk.py —— 清除混进正文的 EPUB 分节标记（只改 text，绝不动 id/顺序）。

源文里的分节标记长这样：
    === ch002.xhtml ===
    第 2 节
    第 2 节
共 44 处，其中 12 处落在句子中间，被当成正文念了出来。

⚠ 关键：**不重排版、不重切句**，只把 text 里的标记抠掉，
这样已生成的 N####.wav 与 id 的对应关系不会错位。
清理后为空的单元整条删除，它的停顿并入前一条。

用法：
    python mt_fix_junk.py --plan mt_plan2.json --scene mt_plan3.json
    python mt_fix_junk.py --dry          # 只看会改什么
"""
import argparse
import json
import os
import re
import shutil

ROOT = "G:/_setup"
JUNK = re.compile(r"\s*===\s*ch\d+\.xhtml\s*===\s*(?:第\s*\d+\s*节\s*)+")


def clean(t):
    t = JUNK.sub(" ", t)
    t = re.sub(r"^\s*=+\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    return t


def fix(path, dry):
    plan = json.load(open(path, encoding="utf-8"))
    changed, dropped, out = [], [], []
    for p in plan:
        nt = clean(p["text"])
        if not nt:
            dropped.append(p)
            if out:                       # 停顿并入前一条
                out[-1]["gap"] = round(out[-1]["gap"] + p["gap"], 2)
            continue
        if nt != p["text"]:
            changed.append((p["id"], p["text"], nt))
            p["text"] = nt
        out.append(p)
    print("%-18s 共 %d → %d 条；改文本 %d 条；删除空条 %d 条"
          % (path.split("/")[-1], len(plan), len(out), len(changed), len(dropped)))
    for i, a, b in changed:
        print("   %s\n     旧: %s\n     新: %s" % (i, a[:110], b[:110]))
    for p in dropped:
        print("   %s 删除（清理后为空）: %s" % (p["id"], p["text"][:60]))
    if changed or dropped:
        if not dry:
            shutil.copy2(os.path.join(ROOT, path), os.path.join(ROOT, path + ".bak"))
            json.dump(out, open(os.path.join(ROOT, path), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
    return [c[0] for c in changed] + [p["id"] for p in dropped]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=None)
    ap.add_argument("--scene", default=None)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    ids = []
    for f in [a.plan, a.scene]:
        if f:
            ids += fix(f, a.dry)
    print("\n需要重新生成的 id：%s" % ",".join(ids))
