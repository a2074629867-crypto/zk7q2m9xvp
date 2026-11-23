# -*- coding: utf-8 -*-
"""对真人情绪语料（Expresso）跑 SER，落 jsonl，支持断点续跑。

用法：
  python eval_real.py --model vox_dim
  python eval_real.py --model e2v --e2v-path <dir>
  python eval_real.py --model phys
"""
import argparse, glob, json, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

MANI = os.path.join(HERE, "wav", "expresso", "_manifest.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--e2v-path", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = args.out or os.path.join(HERE, "out", "real_%s.jsonl" % args.model)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    done = set()
    if os.path.exists(out):
        for ln in open(out, encoding="utf-8"):
            try:
                done.add(json.loads(ln)["path"])
            except Exception:
                pass
    print("已做 %d 条，续跑" % len(done), flush=True)

    items = json.load(open(MANI, encoding="utf-8"))
    if args.limit:
        items = items[: args.limit]

    if args.model == "phys":
        import ser as S
        fn = S.phys
    elif args.model == "vox_dim":
        import ser as S
        m = S.VoxDim()
        fn = m.score
    elif args.model == "e2v":
        import ser as S
        m = S.E2V(args.e2v_path) if args.e2v_path else S.E2V()
        fn = m.score
    else:
        raise SystemExit("unknown model")

    t0 = time.time()
    n_ok = n_fail = 0
    with open(out, "a", encoding="utf-8") as fh:
        for i, it in enumerate(items):
            if it["path"] in done:
                continue
            try:
                r = fn(it["path"])
                if r is None:
                    n_fail += 1
                    continue
                rec = dict(it, score=r, model=args.model)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                n_ok += 1
            except Exception as e:
                n_fail += 1
                if n_fail <= 5:
                    print("FAIL", it["path"], repr(e)[:200], flush=True)
            if (i + 1) % 25 == 0:
                el = time.time() - t0
                print("  %d/%d  ok=%d fail=%d  %.1fs/条  已用%.0fs"
                      % (i + 1, len(items), n_ok, n_fail, el / max(1, n_ok + n_fail), el), flush=True)
    print("完成 ok=%d fail=%d 用时%.0fs" % (n_ok, n_fail, time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
