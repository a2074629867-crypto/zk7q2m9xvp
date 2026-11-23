# -*- coding: utf-8 -*-
"""swap_narr_batch.py -- 按 716 名单替换旁白，其余文件一个字节不动。

为什么不能整目录覆盖：
  _audio_ch123/out = 955 条（旁白 726 + 对白 229）
  注入产物（out_paused_narr*）只含 716 条旁白
  ⇒ 整目录覆盖会删掉 229 条对白和 10 条引语旁白句。

用法：
  G:/Python310/python.exe swap_narr_batch.py --src G:/_setup/_audio_ch123/out_paused_narr2
  # 默认 dst = G:/_setup/_audio_ch123/out，先备份到 _bak_swap_<时间>
  # --dry 只报计划不改文件
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time

HERE = r"G:/_setup"
DST = os.path.join(HERE, "_audio_ch123", "out")
IDS = os.path.join(HERE, "_narr_ids716.json")


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", default=DST)
    ap.add_argument("--ids", default=IDS)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    ids = json.load(open(a.ids, encoding="utf-8"))
    missing = [k for k in ids if not os.path.exists(os.path.join(a.src, k + ".wav"))]
    if missing:
        print("src 缺 %d 条，拒绝替换：%s" % (len(missing), missing[:10]))
        sys.exit(1)

    allf = sorted(f for f in os.listdir(a.dst) if f.endswith(".wav"))
    others = [f for f in allf if f[:-4] not in set(ids)]
    print("dst=%s  wav=%d  要换=%d  不动=%d" % (a.dst, len(allf), len(ids), len(others)))
    print("不动的样本：%s" % others[:6])

    before_others = {f: md5(os.path.join(a.dst, f)) for f in others}
    before_swap = {k: md5(os.path.join(a.dst, k + ".wav")) for k in ids}

    if a.dry:
        print("dry：只报计划，未动文件")
        return

    bak = os.path.join(HERE, "_bak_swap_" + time.strftime("%m%d_%H%M"))
    os.makedirs(bak, exist_ok=True)
    for k in ids:
        shutil.copy2(os.path.join(a.dst, k + ".wav"), os.path.join(bak, k + ".wav"))
    print("备份 %d 条 -> %s" % (len(ids), bak))

    changed = 0
    for k in ids:
        shutil.copy2(os.path.join(a.src, k + ".wav"), os.path.join(a.dst, k + ".wav"))
        if md5(os.path.join(a.dst, k + ".wav")) != before_swap[k]:
            changed += 1

    bad_others = [f for f in others
                  if md5(os.path.join(a.dst, f)) != before_others[f]]
    print("替换完成：716 名单里 %d 条 md5 变化；不动文件被改动 %d 条 %s"
          % (changed, len(bad_others), bad_others[:5]))

    rep = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "src": a.src, "dst": a.dst, "ids": len(ids),
        "changed": changed, "untouched": len(others),
        "untouched_changed": bad_others, "backup": bak,
    }
    p = os.path.join(HERE, "_swap_narr_report.json")
    json.dump(rep, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("report -> %s" % p)
    if bad_others:
        sys.exit(2)


if __name__ == "__main__":
    main()
