# -*- coding: utf-8 -*-
"""音色守卫：打标签后音色有没有跑掉。

两条线：
  1) sim(生成, 该档 ref)      —— 绝对身份（跨语言，本来就偏低，只能同 ref 内比）
  2) sim(生成_cond, 生成_base) —— ★ 关键：同一 ref 下，情绪标签是否把音色改掉
     用户口径：≥0.65 可接受，≥0.80 才算没动
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab")
OUT = os.path.join(HERE, "out")
REFDIR = "G:/_setup/cloud/ref"


def main():
    import spk_embed as SE
    idx = os.path.join(HERE, "out", "gen_index.jsonl")
    items = [json.loads(l) for l in open(idx, encoding="utf-8")]
    out = os.path.join(OUT, "gen_spk.jsonl")
    done = set()
    if os.path.exists(out):
        for ln in open(out, encoding="utf-8"):
            try:
                done.add(json.loads(ln)["path"])
            except Exception:
                pass
    todo = [it for it in items if it["path"] not in done]
    print("待测", len(todo), "/", len(items), flush=True)

    # ref 向量缓存
    refv = {}
    with open(out, "a", encoding="utf-8") as fh:
        for i, it in enumerate(todo):
            try:
                v = SE.embed(it["path"])
                rp = os.path.join(REFDIR, it["ref"])
                if rp not in refv:
                    refv[rp] = SE.embed(rp)
                sim_ref = float(SE.cos(v, refv[rp]))
                # 同 ref 的 base 版
                bp = os.path.join(OUT, "gen", "%s__base__s%d.wav" % (it["pid"], it["seed"]))
                sim_base = None
                if it["cond"] != "base" and os.path.exists(bp):
                    if bp not in refv:
                        refv[bp] = SE.embed(bp)
                    sim_base = float(SE.cos(v, refv[bp]))
                rec = dict(path=it["path"], pid=it["pid"], cond=it["cond"],
                           sim_ref=round(sim_ref, 3),
                           sim_base=None if sim_base is None else round(sim_base, 3))
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                print("  %-32s ref=%.3f  base=%s" %
                      (os.path.basename(it["path"]), sim_ref,
                       "-" if sim_base is None else "%.3f" % sim_base), flush=True)
            except Exception as e:
                print("  FAIL", os.path.basename(it["path"]), repr(e)[:120], flush=True)
            if i % 8 == 0:
                refv = {k: v for k, v in refv.items() if os.path.exists(k)}


if __name__ == "__main__":
    main()
