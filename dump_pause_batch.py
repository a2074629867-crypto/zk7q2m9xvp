# -*- coding: utf-8 -*-
"""分批导出停顿边界，压缩成人可判的紧凑格式。

每句打印一次全文（判边界要看整句语流），边界单独一行。
`chunk` 是 0-based 批次，`n` 是每批边界数。
"""
import argparse
import json

CTX = "G:/_setup/_pause_ctx.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=0)
    ap.add_argument("--n", type=int, default=250)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(CTX, encoding="utf-8") if l.strip()]
    part = rows[a.chunk * a.n:(a.chunk + 1) * a.n]
    print("批次 %d：边界 %d 条（%s … %s），总 %d"
          % (a.chunk, len(part), part[0]["bid"] if part else "-",
             part[-1]["bid"] if part else "-", len(rows)))
    cur = None
    for r in part:
        if r["sid"] != cur:
            cur = r["sid"]
            print("\n[%s] %s" % (cur, r["sent"]))
        lw = " ".join(r["left"].split()[-5:])
        rw = " ".join(r["right"].split()[:5])
        print("  %s  %s   %s ‖ %s" % (r["bid"], r["punct"], lw, rw))


if __name__ == "__main__":
    main()
