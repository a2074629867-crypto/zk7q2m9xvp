# -*- coding: utf-8 -*-
"""校验按 chunk 块标注的旁白 rate plan（对齐 narr_slow_llm.py 的硬约束）。

与 narr_slow_llm.py 的区别：那个按"句索引"切段，本书的生成单位是 chunk 块（bid），
所以这里按块校验，规则值一律沿用 narr_slow_llm.py 的实测标定：
  RATE_HARD_FLOOR 0.72（0.70 会丢整句）
  ADJ_DELTA_MAX 0.06（相邻差大了听感突兀）
  SLOW_COVER_MAX 0.20（整章都慢就没有对比）
  EXTREME_MAX_N 1
"""
import json
import sys

BASE_RATE = 0.80
RATE_MIN, RATE_MAX = 0.72, 0.84
ADJ_DELTA_MAX = 0.06
SLOW_COVER_MAX = 0.20
EXTREME_MAX_N = 1
SEG_WORDS_MIN, SEG_WORDS_MAX = 25, 160


def max_tokens_for(words, rate):
    """减速块要放宽 max_tokens，否则长块必截断（12.7 tok/s 语音，158 wpm@1.0）。"""
    dur = words / 158.0 * 60.0 / max(rate, 0.5)
    return int(-(-dur * 12.7 * 1.08 // 10) * 10)


def main(plan_path, blocks_path):
    plan = json.load(open(plan_path, encoding="utf-8"))
    blocks = {b["bid"]: b for b in json.load(open(blocks_path, encoding="utf-8"))}
    ok = True
    for ch, body in plan.items():
        if ch.startswith("_"):
            continue
        bs = body.get("blocks") or []
        print("== %s  %d 块 / %d 词" % (ch, len(bs), sum(blocks[b["bid"]]["words"] for b in bs)))
        total = slow = 0
        n_ext = 0
        rates = []
        for k, b in enumerate(bs):
            bid = b["bid"]
            if bid not in blocks:
                print("  [FAIL] 未知块 %s" % bid)
                ok = False
                continue
            w = blocks[bid]["words"]
            r = float(b["rate"])
            rates.append(r)
            total += w
            if r < BASE_RATE - 1e-9:
                slow += w
            if r <= 0.72 + 1e-9:
                n_ext += 1
            tags = []
            if r < RATE_MIN - 1e-9:
                tags.append("rate<%.2f（会丢整句）" % RATE_MIN); ok = False
            if r > RATE_MAX + 1e-9:
                tags.append("rate>%.2f" % RATE_MAX); ok = False
            if w < SEG_WORDS_MIN or w > SEG_WORDS_MAX:
                tags.append("词数 %d 越界" % w); ok = False
            if r < BASE_RATE - 1e-9 and not b.get("why"):
                tags.append("减速段缺 why"); ok = False
            flag = "  ← " + " / ".join(tags) if tags else ""
            print("  %s %3d词  rate %.2f  tok≤%4d  %s%s"
                  % (bid, w, r, max_tokens_for(w, r), str(b.get("why", ""))[:40], flag))
        for k in range(len(rates) - 1):
            d = abs(rates[k] - rates[k + 1])
            if d > ADJ_DELTA_MAX + 1e-9:
                print("  [FAIL] %s→%s rate 跳 %.2f（> %.2f）"
                      % (bs[k]["bid"], bs[k + 1]["bid"], d, ADJ_DELTA_MAX))
                ok = False
        if n_ext > EXTREME_MAX_N:
            print("  [FAIL] rate<=0.72 有 %d 段（最多 %d）" % (n_ext, EXTREME_MAX_N))
            ok = False
        cov = slow / total if total else 0.0
        mark = "OK" if cov <= SLOW_COVER_MAX + 1e-9 else "FAIL"
        print("  减速覆盖 %d/%d 词 = %.1f%%  [%s]  (上限 %.0f%%)"
              % (slow, total, cov * 100, mark, SLOW_COVER_MAX * 100))
        if mark == "FAIL":
            ok = False
        print()
    print("=== 总校验 %s ===" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/_narr_rate_plan_castle.json",
                  sys.argv[2] if len(sys.argv) > 2 else "G:/_setup/_narr_blocks.json"))
