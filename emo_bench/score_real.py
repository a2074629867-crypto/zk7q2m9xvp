# -*- coding: utf-8 -*-
"""对任意标签 jsonl 批量跑引擎，落盘可续跑。

用法：
  python score_real.py --labels out/labels_expresso_full.jsonl --engine e2v --out out/real_full_e2v.jsonl
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--engine", required=True, choices=["e2v", "vox_dim", "phys", "deear"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    items = [json.loads(l) for l in open(a.labels, encoding="utf-8")]
    items = [it for it in items if os.path.exists(it["path"])]
    if a.limit:
        items = items[:a.limit]
    done = set()
    if os.path.exists(a.out):
        for ln in open(a.out, encoding="utf-8"):
            try:
                done.add(json.loads(ln)["path"])
            except Exception:
                pass
    todo = [it for it in items if it["path"] not in done]
    print("[%s] 总 %d，已完成 %d，待做 %d" % (a.engine, len(items), len(done), len(todo)), flush=True)

    if not todo:
        return

    import ser as S
    if a.engine == "phys":
        fn = S.phys
    elif a.engine == "vox_dim":
        fn = S.VoxDim().score
    elif a.engine == "e2v":
        fn = S.E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large").score
    else:
        import deear
        D = deear.DeEAR()
        fn = None

    t0 = time.time()
    ok = 0
    with open(a.out, "a", encoding="utf-8") as fh:
        if a.engine == "deear":
            files = [it["path"] for it in todo]
            rows = D.score(files, batch_size=8)
            m = {os.path.normcase(r["path"]): r for r in rows}
            for it in todo:
                r = m.get(os.path.normcase(it["path"]))
                if not r:
                    continue
                out = {k: v for k, v in r.items() if k != "path"}
                fh.write(json.dumps(dict(it, score=out), ensure_ascii=False) + "\n")
                fh.flush()
                ok += 1
        else:
            for it in todo:
                try:
                    r = fn(it["path"])
                    if r is None:
                        continue
                    fh.write(json.dumps(dict(it, score=r), ensure_ascii=False) + "\n")
                    fh.flush()
                    ok += 1
                except Exception as e:
                    print("  FAIL", os.path.basename(it["path"]), repr(e)[:120], flush=True)
                if ok % 200 == 0:
                    print("  %d/%d  %.0fs" % (ok, len(todo), time.time() - t0), flush=True)
    print("[%s] 完成 %d 条，用时 %.0fs" % (a.engine, ok, time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
