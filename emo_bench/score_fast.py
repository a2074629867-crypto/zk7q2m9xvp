# -*- coding: utf-8 -*-
"""批量版引擎打分（比逐条快一个数量级）。

e2v : funasr 原生 batch（batch_size_s 按总时长打包）
vox : WavLM-large 维度头，自己拼 batch（pad 到最长，mask 后取池化）

用法：
  python score_fast.py --labels out/labels_subset.jsonl --engine e2v --out out/sub_e2v.jsonl
"""
import argparse, json, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")
os.environ.setdefault("MODELSCOPE_CACHE", "G:/_setup/models/ms")
os.environ.setdefault("HF_HOME", "G:/_setup/models/hf")


def run_e2v(items, out, chunk=24):
    from funasr import AutoModel
    m = AutoModel(model="G:/_setup/models/ms/iic/emotion2vec_plus_large",
                  disable_update=True, device="cpu")
    done = _done(out)
    todo = [it for it in items if it["path"] not in done]
    print("[e2v] 待做 %d" % len(todo), flush=True)
    t0 = time.time()
    with open(out, "a", encoding="utf-8") as fh:
        for i in range(0, len(todo), chunk):
            part = todo[i:i + chunk]
            paths = [p["path"] for p in part]
            try:
                res = m.generate(input=paths, granularity="utterance",
                                 extract_embedding=False, batch_size_s=90)
            except Exception as e:
                print("  chunk fail", repr(e)[:120], flush=True)
                continue
            if not isinstance(res, list):
                res = [res]
            for it, r in zip(part, res):
                labels = r.get("labels") or []
                scores = r.get("scores") or []
                if isinstance(labels, str):
                    labels = [labels]
                sc = {str(l): round(float(s), 4) for l, s in zip(labels, scores)}
                if not sc:
                    continue
                sc["_top"] = max(sc, key=sc.get)
                fh.write(json.dumps(dict(it, score=sc), ensure_ascii=False) + "\n")
            fh.flush()
            print("  %d/%d %.0fs" % (min(i + chunk, len(todo)), len(todo), time.time() - t0), flush=True)
    print("[e2v] done %.0fs" % (time.time() - t0), flush=True)


def run_vox(items, out, batch=16):
    import torch
    import vox_profile as V
    model = V.load("dim", "wavlm-large-msp-podcast-emotion-dim")
    model.eval()
    done = _done(out)
    todo = [it for it in items if it["path"] not in done]
    print("[vox] 待做 %d" % len(todo), flush=True)
    t0 = time.time()
    with open(out, "a", encoding="utf-8") as fh, torch.no_grad():
        for i in range(0, len(todo), batch):
            part = todo[i:i + batch]
            xs, keep = [], []
            for it in part:
                try:
                    y = V.read16(it["path"], hq=True)
                    if len(y) < 1600:
                        continue
                    xs.append(V.norm(V.cut(y)))
                    keep.append(it)
                except Exception:
                    continue
            if not xs:
                continue
            L = max(len(x) for x in xs)
            arr = np.zeros((len(xs), L), dtype=np.float32)
            for j, x in enumerate(xs):
                arr[j, :len(x)] = x
            x = torch.from_numpy(arr).float()
            try:
                r = model(x)
            except Exception as e:
                print("  batch fail", repr(e)[:120], flush=True)
                continue
            for j, it in enumerate(keep):
                sc = {k: round(float(v), 4) for k, v in r.items()} if isinstance(r, dict) else None
                if sc is None:
                    break
                vals = {k: (float(v[j]) if hasattr(v, "__len__") else float(v)) for k, v in r.items()}
                fh.write(json.dumps(dict(it, score={k: round(v, 4) for k, v in vals.items()}),
                                    ensure_ascii=False) + "\n")
            fh.flush()
            print("  %d/%d %.0fs" % (min(i + batch, len(todo)), len(todo), time.time() - t0), flush=True)
    print("[vox] done %.0fs" % (time.time() - t0), flush=True)


def _done(p):
    s = set()
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            try:
                s.add(json.loads(ln)["path"])
            except Exception:
                pass
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--engine", required=True, choices=["e2v", "vox"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    items = [json.loads(l) for l in open(a.labels, encoding="utf-8")]
    items = [it for it in items if os.path.exists(it["path"])]
    if a.limit:
        items = items[:a.limit]
    if a.engine == "e2v":
        run_e2v(items, a.out)
    else:
        run_vox(items, a.out)


if __name__ == "__main__":
    main()
