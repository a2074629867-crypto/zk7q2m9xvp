# -*- coding: utf-8 -*-
"""TTSDS2 的 MPM 韵律表示 → 逐句「韵律自然度」偏离度。

依据
----
TTSDS2（ICLR 2026，github.com/ttsds/daisy；PyPI 包名 `ttsds`）是 16 个指标里
唯一在全部 14 种语言、全部主观分项上 Spearman > 0.50 的客观指标。
它的 prosody 维度由 5 个 benchmark 组成，其中 MPM（Masked Prosody Model，
cdminix/masked_prosody_model）把 (pitch, energy, VAD) 三路逐帧离散化后过
Conformer，取第 7 层隐状态作为**韵律表示**。

TTSDS2 原文是拿整批生成的分布去比参考分布。我们要判**单条**，所以改成：
  1) 用 55 条已交付（人耳接受过）算参考帧集合 R
  2) 候选的每一帧，算它到 R 的最近邻余弦距离
  3) 留一法：R 里每条也这么算一遍，得到「自己人」的零分布
  4) outlier_rate = 落在零分布 p95 之外的帧占比 —— 越高越不像这本书的韵律

注意：MPM 的 pitch 归一化区间是 50~300 Hz，本书旁白基线约 74 Hz，贴近下界，
这是已知局限，写进报告里。

本模块只负责「算」，不负责「判」。判定阈值必须先用已知好坏样本验证。
"""
import os
import sys
import json
import hashlib
import argparse
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_ttsds_cache")
os.makedirs(CACHE, exist_ok=True)
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

SR_MPM = 22050


def _stub(name):
    """给缺失的可选依赖打桩，只为让 ttsds 的 __init__ 通过。"""
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        mod = ".".join(parts[:i])
        if mod in sys.modules:
            continue
        m = types.ModuleType(mod)
        m.__path__ = []
        sys.modules[mod] = m
        if i > 1:
            setattr(sys.modules[".".join(parts[:i - 1])], parts[i - 1], m)


def load_mpm():
    """反复尝试导入，缺什么桩什么。返回 MPMBenchmark 实例。"""
    for _ in range(30):
        try:
            from ttsds.benchmarks.prosody.mpm import MPMBenchmark
            return MPMBenchmark()
        except ModuleNotFoundError as e:
            n = e.name
            if not n or n.startswith("ttsds"):
                raise
            _stub(n)
    raise RuntimeError("依赖桩化失败")


def _md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


_b = None


def frames(path, use_cache=True):
    """一条音频的 MPM 韵律帧 [T, D]，L2 归一化。"""
    global _b
    key = os.path.join(CACHE, _md5(path) + ".npy")
    if use_cache and os.path.exists(key):
        return np.load(key)
    import librosa
    import torch
    if _b is None:
        _b = load_mpm()
    wav, sr = librosa.load(path, sr=SR_MPM, mono=True)
    pitch = _b.pitch_measure(wav, np.array([1000]))["measure"]
    energy = _b.energy_measure(wav, np.array([1000]))["measure"]
    vad = _b.voice_activity_measure(wav, np.array([1000]))["measure"]
    t = lambda x: torch.tensor(np.asarray(x, dtype=np.float32))
    pitch, energy, vad = t(pitch), t(energy), t(vad)
    for z in (pitch, energy, vad):
        z[torch.isnan(z)] = -1000
    pitch = torch.clip(pitch, _b.pitch_min, _b.pitch_max) / (_b.pitch_max - _b.pitch_min)
    energy = torch.clip(energy, _b.energy_min, _b.energy_max) / (_b.energy_max - _b.energy_min)
    vad = torch.clip(vad, _b.vad_min, _b.vad_max) / (_b.vad_max - _b.vad_min)
    pb = torch.bucketize(pitch, _b.bins)
    eb = torch.bucketize(energy, _b.bins)
    vb = torch.bucketize(vad, torch.linspace(0, 1, 2))
    n = min(len(pb), len(eb), len(vb))
    inp = torch.stack([pb[:n], eb[:n], vb[:n]]).unsqueeze(0)
    with torch.no_grad():
        rep = _b.model(inp, return_layer=_b.mpm_layer)["representations"]
    f = rep.detach().cpu().numpy()[0].astype(np.float32)
    nn = np.linalg.norm(f, axis=1, keepdims=True)
    nn[nn < 1e-9] = 1e-9
    f = f / nn
    np.save(key, f)
    return f


def _nn_dist(cand, ref, block=2048):
    """cand 每帧到 ref 的最近邻余弦距离（1 - cos）。分块省内存。"""
    out = np.empty(len(cand), dtype=np.float32)
    for i in range(0, len(cand), block):
        c = cand[i:i + block]
        s = c @ ref.T
        out[i:i + block] = 1.0 - s.max(axis=1)
    return out


def build_reference(paths, out=None, verbose=True):
    """参考集合：所有帧拼起来 + 留一法的零分布。"""
    frames_by = {}
    for k, p in enumerate(paths, 1):
        try:
            frames_by[p] = frames(p)
        except Exception as e:
            print("  !! %s %s" % (os.path.basename(p), str(e)[:80]))
        if verbose and k % 10 == 0:
            print("  参考 %d/%d" % (k, len(paths)), flush=True)
    allf = np.vstack(list(frames_by.values()))
    nn = np.linalg.norm(allf, axis=1, keepdims=True)
    nn[nn < 1e-9] = 1e-9
    allf = allf / nn

    # 留一法：每条用「去掉自己」的参考集算 NN 距离，得到自己人的零分布
    loo = []
    for p, f in frames_by.items():
        others = [v for q, v in frames_by.items() if q != p]
        if not others:
            continue
        ref = np.vstack(others)
        ref = ref / np.maximum(np.linalg.norm(ref, axis=1, keepdims=True), 1e-9)
        loo.append(_nn_dist(f, ref))
    loo = np.concatenate(loo) if loo else np.array([0.0], dtype=np.float32)

    out_d = dict(
        n_utts=len(frames_by), n_frames=int(len(allf)),
        loo_p50=round(float(np.median(loo)), 4),
        loo_p95=round(float(np.percentile(loo, 95)), 4),
        loo_p99=round(float(np.percentile(loo, 99)), 4),
        thr_p95=round(float(np.percentile(loo, 95)), 4),
    )
    if out:
        np.save(out, allf)
        json.dump(out_d, open(out + ".json", "w", encoding="utf-8"), indent=1)
        print("参考集：%d 条 / %d 帧，留一法 p50 %.4f p95 %.4f"
              % (out_d["n_utts"], out_d["n_frames"], out_d["loo_p50"], out_d["loo_p95"]))
    return allf, out_d


def score(path, ref, thr):
    """单条的韵律离群率。"""
    f = frames(path)
    d = _nn_dist(f, ref)
    return dict(
        n_frames=int(len(f)),
        nn_p50=round(float(np.median(d)), 4),
        nn_p95=round(float(np.percentile(d, 95)), 4),
        outlier_rate=round(float((d > thr).mean()), 4),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", nargs="*", help="建参考集（给一批 wav）")
    ap.add_argument("--ref", default=os.path.join(HERE, "_ttsds_ref.npy"))
    ap.add_argument("--thr", type=float, default=None)
    ap.add_argument("--score", nargs="*", help="给一批 wav 打分")
    a = ap.parse_args()

    if a.build:
        build_reference(a.build, out=a.ref)
        return
    if a.score:
        ref = np.load(a.ref)
        meta = json.load(open(a.ref + ".json", encoding="utf-8"))
        thr = a.thr if a.thr is not None else meta["thr_p95"]
        for p in a.score:
            print(os.path.basename(p), json.dumps(score(p, ref, thr), ensure_ascii=False))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
