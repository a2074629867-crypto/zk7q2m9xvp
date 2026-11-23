"""窗口级声纹筛：找出每个字幕 cue 里哪些时间窗是 Charles、哪些是 Thomas。

原理：对 cue 内每个 1.2s 窗算 resnet293 embedding，与两个"语义确凿的纯净种子"比余弦，
取高置信窗作为该 cue 的可靠片段。混人 cue 会出现两类窗交替。

产物：out/sv_windows.jsonl  每行 {cue, t0, win_t, label, conf}
"""
import sys, os, json, argparse
import numpy as np
import torch
from torchaudio.compliance import kaldi

sys.path.insert(0, "G:/_setup")
from sv_onnx import SV, load16

WIN, HOP = 1.2, 0.6
SR = 16000


def win_embed(model, x, s):
    n = int(WIN * SR)
    seg = x[s:s + n]
    if len(seg) < n * 0.55:
        return None, 0.0
    w = torch.from_numpy(seg.astype(np.float32)).unsqueeze(0)
    f = kaldi.fbank(w, num_mel_bins=80, sample_frequency=SR, dither=0.0, energy_floor=0.0)
    f = f - f.mean(0, keepdim=True)
    e = model.s.run([model.oname], {model.iname: f.unsqueeze(0).numpy()})[0][0]
    e = e / (np.linalg.norm(e) + 1e-9)
    rms = float(np.sqrt((seg ** 2).mean()))
    return e.astype(np.float32), rms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="G:/_setup/_sv_seeds.json")
    ap.add_argument("--cues", default="G:/_setup/castle_cues_index.json")
    ap.add_argument("--out", default="G:/_setup/out_sv/sv_windows.jsonl")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    m = SV("r293")
    seeds = json.load(open(a.seeds, encoding="utf-8"))
    proto = {}
    for who, files in seeds.items():
        es = []
        for p in files:
            x = load16(p)
            for s in range(0, max(1, len(x) - int(WIN * SR) + 1), int(HOP * SR)):
                e, rms = win_embed(m, x, s)
                if e is not None and rms > 0.005:
                    es.append(e)
        if es:
            v = np.mean(es, axis=0)
            proto[who] = v / (np.linalg.norm(v) + 1e-9)
        print("seed %s: %d 窗" % (who, len(es)), flush=True)

    cues = json.load(open(a.cues, encoding="utf-8"))
    names = list(proto)
    out = open(a.out, "w", encoding="utf-8")
    for i, c in enumerate(cues):
        try:
            x = load16(c["path"])
        except Exception:
            continue
        recs = []
        for s in range(0, max(1, len(x) - int(WIN * SR) + 1), int(HOP * SR)):
            e, rms = win_embed(m, x, s)
            if e is None or rms < 0.005:
                continue
            sc = {k: float(np.dot(e, proto[k])) for k in names}
            best = max(sc, key=sc.get)
            order = sorted(sc.values(), reverse=True)
            recs.append({"t": round(s / SR + c["t0"], 2), "lab": best,
                         "c": round(sc.get("Charles", 0), 4), "h": round(sc.get("Thomas", 0), 4),
                         "margin": round(order[0] - order[1], 4)})
        for r in recs:
            r.update({"cue": c["i"], "t0": c["t0"], "text": c["text"][:80],
                      "multi": c["multi"], "path": c["path"]})
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
        if (i + 1) % 50 == 0:
            print("cue %d/%d" % (i + 1, len(cues)), flush=True)
    out.close()
    print("done ->", a.out)


if __name__ == "__main__":
    main()
