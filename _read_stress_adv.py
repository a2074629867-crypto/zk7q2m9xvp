# -*- coding: utf-8 -*-
import io, json, sys
p = sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/_stress_adv_before.json"
d = json.load(io.open(p, encoding="utf-8"))
print("== 严格口径（强调副词 = 方式/频率副词）==")
for k in ["tag", "n_sent", "n_word", "n_adv", "auc_adv", "adv_z_mean",
          "adv_z_median", "non_z_mean", "adv_pct_mean", "non_pct_mean",
          "adv_ge_16", "adv_lt_0", "top1_adv_rate", "top3_adv_rate"]:
    print("  %-14s %s" % (k, d.get(k)))
w = d.get("wide") or {}
print("\n== 宽口径（所有 -ly + 无-ly 副词，含弱读虚词）==")
for k, v in w.items():
    print("  %-14s %s" % (k, v))
print("\n读得最重的强调副词:")
for t in d.get("top_adv", [])[:12]:
    print("   %-12s n=%-3d z=%+.2f" % (t[0], t[1], t[2]))
print("\n读得最轻的强调副词:")
for t in d.get("weak_adv", [])[:12]:
    print("   %-12s n=%-3d z=%+.2f" % (t[0], t[1], t[2]))
print("\n系统性没被强调的副词（按均值升序）:")
for t in d.get("miss_rank", [])[:12]:
    print("   %-12s n=%-3d z=%+.2f" % (t[0], t[1], t[2]))
print("\n单句样例:")
for m in d.get("miss_sample", [])[:12]:
    print("   %-9s %-10s z=%+.2f pct=%.2f" % (m["sid"], m["w"], m["z"], m["pct"]))
