"""帧级声纹 + 全局聚类 = 说话人分离（自实现，不依赖 sherpa/onnx）。

流程：
  1. 每个字幕 cue 切 1.5s 窗（0.75s 步长），能量门限过滤静音
  2. resnet34 embedding（lightning 版，0.25s/窗）
  3. 全局层次聚类（cosine 距离，N 类）
  4. 用语义确凿的种子给簇命名
  5. 输出每个 cue 内"纯 Charles / 纯 Thomas / 混人"的判定与纯净时间段
"""
import os, sys, json, argparse, time
import numpy as np
import torch
from torchaudio.compliance import kaldi
from sklearn.cluster import AgglomerativeClustering

sys.path.insert(0, "G:/_setup")
from sv_onnx import SV, load16

WIN, HOP, SR = 1.5, 0.75, 16000


def emb_win(m, seg):
    w = torch.from_numpy(seg.astype(np.float32)).unsqueeze(0)
    f = kaldi.fbank(w, num_mel_bins=80, sample_frequency=SR, dither=0.0, energy_floor=0.0)
    f = f - f.mean(0, keepdim=True)
    e = m.s.run([m.oname], {m.iname: f.unsqueeze(0).numpy()})[0][0]
    return e / (np.linalg.norm(e) + 1e-9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cues", default="G:/_setup/castle_cues_index.json")
    ap.add_argument("--seeds", default="G:/_setup/_sv_seeds.json")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--model", default="r34")
    ap.add_argument("--out", default="G:/_setup/out_sv/cluster.json")
    a = ap.parse_args()

    m = SV(a.model)
    seeds = json.load(open(a.seeds, encoding="utf-8"))
    seed_emb = {}
    for who, files in seeds.items():
        vs = []
        for p in files:
            x = load16(p)
            n = int(WIN * SR)
            for s in range(0, max(1, len(x) - n + 1), int(HOP * SR)):
                seg = x[s:s + n]
                if len(seg) < n * 0.6:
                    continue
                if np.sqrt((seg ** 2).mean()) < 0.006:
                    continue
                vs.append(emb_win(m, seg))
        if vs:
            v = np.mean(vs, 0)
            seed_emb[who] = v / np.linalg.norm(v)
            print("seed %-8s %d 窗" % (who, len(vs)), flush=True)

    cues = json.load(open(a.cues, encoding="utf-8"))
    W = []   # (cue_idx, t_abs, rms, emb)
    t0 = time.time()
    for i, c in enumerate(cues):
        try:
            x = load16(c["path"])
        except Exception:
            continue
        n = int(WIN * SR)
        for s in range(0, max(1, len(x) - n + 1), int(HOP * SR)):
            seg = x[s:s + n]
            if len(seg) < n * 0.6:
                continue
            rms = float(np.sqrt((seg ** 2).mean()))
            if rms < 0.006:
                continue
            W.append((i, c["t0"] + s / SR, rms, emb_win(m, seg)))
        if (i + 1) % 100 == 0:
            print("cue %d/%d  窗 %d  %.0fs" % (i + 1, len(cues), len(W), time.time() - t0), flush=True)

    E = np.array([w[3] for w in W])
    print("总窗 %d，聚类 N=%d ..." % (len(E), a.n), flush=True)
    lab = AgglomerativeClustering(n_clusters=a.n, metric="cosine", linkage="average").fit_predict(E)

    # 每簇用种子命名
    cent = {}
    for k in range(a.n):
        idx = np.where(lab == k)[0]
        if len(idx) == 0:
            continue
        v = E[idx].mean(0)
        cent[k] = v / np.linalg.norm(v)
    name = {}
    for k, v in cent.items():
        sc = {w: float(np.dot(v, s)) for w, s in seed_emb.items()}
        name[k] = max(sc, key=sc.get)
        print("  簇%d -> %-8s  (C %.3f / T %.3f)  n=%d" %
              (k, name[k], sc.get("Charles", -1), sc.get("Thomas", -1), int((lab == k).sum())), flush=True)
    # 同名冲突时保留相似度高的
    seen = {}
    for k, v in cent.items():
        w = name[k]
        if w in seen and float(np.dot(v, seed_emb[w])) < seen[w][0]:
            name[k] = "spk%d" % k
        else:
            seen[w] = (float(np.dot(v, seed_emb[w])), k)

    out = []
    for (ci, t, rms, _), k in zip(W, lab):
        out.append({"cue": cues[ci]["i"], "t": round(t, 2), "rms": round(rms, 5),
                    "spk": name[k], "cluster": int(k), "t0": cues[ci]["t0"],
                    "text": cues[ci]["text"][:70], "multi": cues[ci]["multi"]})
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("done %.0fs -> %s" % (time.time() - t0, a.out), flush=True)


if __name__ == "__main__":
    main()
