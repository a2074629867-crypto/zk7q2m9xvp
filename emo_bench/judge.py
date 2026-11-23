# -*- coding: utf-8 -*-
"""给生成矩阵打分：三个通道全跑，落 jsonl（断点续跑）。"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

GEN = os.path.join(HERE, "out", "gen")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="phys,vox_dim,e2v")
    ap.add_argument("--e2v-path", default="G:/_setup/models/ms/iic/emotion2vec_plus_large")
    ap.add_argument("--only", default=None, help="只跑某个模型")
    args = ap.parse_args()

    idx = os.path.join(HERE, "out", "gen_index.jsonl")
    items = [json.loads(l) for l in open(idx, encoding="utf-8")]
    print("生成条目", len(items), flush=True)

    models = args.models.split(",")
    import ser as S

    for name in models:
        if args.only and name != args.only:
            continue
        out = os.path.join(HERE, "out", "gen_%s.jsonl" % name)
        done = set()
        if os.path.exists(out):
            for ln in open(out, encoding="utf-8"):
                try:
                    done.add(json.loads(ln)["path"])
                except Exception:
                    pass
        todo = [it for it in items if it["path"] not in done]
        print("\n[%s] 待做 %d / %d" % (name, len(todo), len(items)), flush=True)
        if not todo:
            continue

        if name == "phys":
            fn = S.phys
        elif name == "vox_dim":
            fn = S.VoxDim().score
        elif name == "e2v":
            fn = S.E2V(args.e2v_path).score
        else:
            raise SystemExit(name)

        t0 = time.time()
        ok = 0
        with open(out, "a", encoding="utf-8") as fh:
            for it in todo:
                try:
                    r = fn(it["path"])
                    if r is None:
                        continue
                    fh.write(json.dumps(dict(it, score=r), ensure_ascii=False) + "\n")
                    fh.flush()
                    ok += 1
                    print("  %-34s %.1fs" % (os.path.basename(it["path"]), time.time() - t0), flush=True)
                except Exception as e:
                    print("  FAIL", os.path.basename(it["path"]), repr(e)[:150], flush=True)
        print("[%s] 完成 %d 条，用时 %.0fs" % (name, ok, time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
