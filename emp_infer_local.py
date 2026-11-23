# -*- coding: utf-8 -*-
"""_emp_infer.py —— EmphaClass-en 帧级重读判别器推理（在云 GPU 机器上跑）。

模型：facebook/wav2vec2-xls-r-1b + Wav2Vec2ForAudioFrameClassification
      帧级 20ms 二分类；词级规则（论文 §5.2）= 词内 >50% 帧判 emphasized。
权重：/home/aistudio/models/EmphaClass/emphaclass_en（pytorch_model.bin 3,850,269,421 B）

用法（云端）：
    python _emp_infer.py --dir /home/aistudio/in_narr --out /home/aistudio/emp_narr.json --limit 20
自检（先跑 3 条看形状/label 对不对，再放量）：
    python _emp_infer.py --dir /home/aistudio/in_narr --out /home/aistudio/emp_probe.json --limit 3

输出每条：
    {"id":..., "dur":..., "frames":T, "labels":{...},
     "emph_rate": 帧级强调比例,
     "p": [每帧 emphasized 概率，四舍五入 3 位]}

★ 显存：fp32 权重 3.85GB；fp16 加载可减半。长音频一次性前向会炸，所以按 20s 滑窗分段跑。
★ 不要在这台机器上想当然 pip install：先看 env_probe 输出，缺什么再报给用户决定。
"""
import argparse, glob, json, os, sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="G:/_setup/models/EmphaClass/emphaclass_en")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--chunk", type=float, default=20.0)
    ap.add_argument("--fp16", action="store_true", default=False)
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--shard", default="0/1")
    a = ap.parse_args()

    import torch, soundfile as sf
    torch.set_num_threads(torch.get_num_threads())
    from transformers import AutoFeatureExtractor, AutoModelForAudioFrameClassification

    torch.set_num_threads(a.threads)
    print("[cpu] threads = %d" % a.threads)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("[env] torch %s | cuda %s | %s" % (
        torch.__version__, torch.cuda.is_available(),
        torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU"))
    if dev == "cpu":
        print("[warn] 没看到 GPU，跑 1B 模型会非常慢；确认是不是选错实例。")

    fe = AutoFeatureExtractor.from_pretrained(a.model)
    m = AutoModelForAudioFrameClassification.from_pretrained(
        a.model, torch_dtype=torch.float16 if (dev == "cuda" and a.fp16) else torch.float32)
    m = m.to(dev).eval()
    print("[model] labels =", m.config.id2label, "| hidden", m.config.hidden_size)

    files = sorted(glob.glob(os.path.join(a.dir, "*.wav")))
    if a.limit:
        files = files[:a.limit]
    _i, _n = [int(x) for x in a.shard.split("/")]
    if _n > 1:
        files = files[_i::_n]
    print("[shard] %s -> %d files" % (a.shard, len(files)))
    print("[in] %d files" % len(files))

    out = []
    for i, f in enumerate(files, 1):
        y, sr = sf.read(f, dtype="float32", always_2d=True)
        y = y.mean(1)
        if sr != 16000:
            import numpy as np
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(int(sr), 16000)
            y = resample_poly(y, 16000 // g, sr // g).astype("float32")
        step = int(a.chunk * 16000)
        probs = []
        for s in range(0, max(1, len(y)), step):
            seg = y[s:s + step]
            if len(seg) < 1600:
                break
            inp = fe(seg, sampling_rate=16000, return_tensors="pt")
            dt = next(m.parameters()).dtype
            mv = {k: (v.to(dev, dtype=dt) if v.is_floating_point() else v.to(dev))
                  for k, v in inp.items()}
            with torch.no_grad():
                lo = m(**mv).logits
            p = torch.softmax(lo.float(), -1)[0]
            # emphasized 的类下标：优先按 label 文字找，找不到就取 1
            ei = next((k for k, v in m.config.id2label.items()
                       if str(v).lower().startswith("emph")), 1)
            probs.extend(p[:, ei].cpu().numpy().tolist())
        dur = len(y) / 16000.0
        er = float(sum(1 for x in probs if x > 0.5) / max(1, len(probs)))
        out.append(dict(id=os.path.splitext(os.path.basename(f))[0],
                        dur=round(dur, 2), frames=len(probs),
                        labels={str(k): v for k, v in m.config.id2label.items()},
                        emph_rate=round(er, 4),
                        p=[round(x, 3) for x in probs]))
        print("  %d/%d  %s  dur=%.2fs  emph_rate=%.3f  frames=%d" % (
            i, len(files), out[-1]["id"], dur, er, len(probs)), flush=True)
        if i % 5 == 0 or i == len(files):
            json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)

    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("[out] %d 条 -> %s" % (len(out), a.out))
    if out:
        import statistics
        print("[stat] emph_rate 中位 %.3f | p50 %.3f" % (
            statistics.median(x["emph_rate"] for x in out),
            statistics.median(x["emph_rate"] for x in out)))


if __name__ == "__main__":
    main()
