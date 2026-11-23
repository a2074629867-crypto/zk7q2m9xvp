# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
ann = {json.loads(l)['sid'] for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8') if l.strip()}
sh = [sum(1 for i in b['ids'] if i in ann) / max(1, len(b['ids'])) for b in B]
tot = sum(b['words'] for b in B)


def runs_of(flags):
    out, cur = [], None
    for k, f in enumerate(flags):
        if f:
            if cur and k - cur[1] <= 1:
                cur[1] = k
            else:
                if cur:
                    out.append(cur)
                cur = [k, k]
    if cur:
        out.append(cur)
    return out


for TH in (0.30, 0.35, 0.40, 0.45):
    flags = [1 if s >= TH else 0 for s in sh]
    for k in range(1, len(flags) - 1):
        if not flags[k] and flags[k - 1] and flags[k + 1]:
            flags[k] = 1
    rr = runs_of(flags)
    cov = 100.0 * sum(b['words'] for b, f in zip(B, flags) if f) / tot
    single = sum(1 for a, b in rr if a == b)
    print('TH %.2f: slow %d/81  words %.1f%%  runs %d  single-block-runs %d  sizes %s'
          % (TH, sum(flags), cov, len(rr), single, [b - a + 1 for a, b in rr]))
