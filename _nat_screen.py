# -*- coding: utf-8 -*-
"""整体韵律自然度多指标筛（known-answer 标定用）。

对同一批 take 同时算：
  A. 模型分（黑盒）：SQUIM-SUBJ MOS、NISQA 四维、DNSMOS OVRL
  B. 韵律统计（可解释、有真人锚点）：F0 跨度(semitone)、F0 斜率中位、
     有声占比、句内最长静音、能量包络粗糙度、语速(wps)

用法：
  python _nat_screen.py --sets known      # 已知好坏对照（标定）
  python _nat_screen.py --sets all        # 全库 take 池
  python _nat_screen.py --wavs a.wav,b.wav --out x.json
"""
import argparse
import json
import os
import shutil
import statistics as st
import sys
import tempfile

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, "G:/_setup")

SR = 16000
NISQA_MODEL = "D:/eval_models/nisqa/nisqa.tar"

_SQ = None


# ---------------------------------------------------------------- 模型分
def _load16(path, sec=None):
    import torchaudio
    wav, sr = torchaudio.load(path)
    if wav.shape[0] > 1:
        wav = wav.mean(0, keepdim=True)
    if sr != SR:
        wav = torchaudio.functional.resample(wav, sr, SR)
    if sec:
        wav = wav[:, : int(sec * SR)]
    return wav


def squim_mos(path, ref_path):
    """torchaudio SQUIM-SUBJECTIVE：forward(waveform, reference)，reference 是
    「非同一内容的干净参考」，输出 5 − 预测劣化。★ 不是纯非侵入 MOS。"""
    global _SQ
    import torchaudio
    if _SQ is None:
        _SQ = torchaudio.pipelines.SQUIM_SUBJECTIVE.get_model().eval()
    w = _load16(path)
    r = _load16(ref_path)
    with torch.no_grad():
        v = _SQ(w, r)
    return float(v.reshape(-1)[0])


def dnsmos(path):
    from speechmos import dnsmos as D
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(1)
    if sr != SR:
        import librosa
        x = librosa.resample(x, orig_sr=sr, target_sr=SR)
    return D.run(x, SR)


def trim_silence(path, out, keep=0.03, thr_db=-42.0, min_gap=0.22):
    """剪掉 >min_gap 的静音段（只留 keep 边缘）。★ 我们插入的逗号/句号停顿会
    把 NISQA-DIS 拉低，必须在评测前剪掉，否则测的是停顿占比不是自然度。"""
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(1)
    step = max(1, int(0.005 * sr))
    n = len(x) // step
    fr = x[: n * step].reshape(n, step)
    r = 20 * np.log10(np.sqrt(np.mean(fr ** 2, axis=1)) + 1e-12)
    loud = r > thr_db
    segs = []
    i = 0
    while i < n:
        if loud[i]:
            j = i
            while j < n and loud[j]:
                j += 1
            segs.append((i * step, (j - 1) * step + step))
            i = j
        else:
            i += 1
    if not segs:
        shutil.copy(path, out)
        return out
    # 合并间隔 < min_gap 的相邻段
    merged = [list(segs[0])]
    for a, b in segs[1:]:
        if a - merged[-1][1] < min_gap * sr:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    pad = int(keep * sr)
    ys = []
    for a, b in merged:
        ys.append(x[max(0, a - pad): min(len(x), b + pad)])
    y = np.concatenate(ys) if ys else x
    sf.write(out, y, sr)
    return out


def nisqa_batch(paths):
    """NISQA 一次跑一个目录。★ 同一单元的多条 take 同名，必须重命名去重。"""
    import ch123_nisqa as N
    d = tempfile.mkdtemp(prefix="nisqa_")
    try:
        amap = {}
        for i, p in enumerate(paths):
            nn = "t%04d.wav" % i
            shutil.copy(p, os.path.join(d, nn))
            amap[nn] = p
        df = N.run(d, NISQA_MODEL, out_dir=os.path.join(d, "out"))
        out = {}
        for _, r in df.iterrows():
            out[amap.get(r["deg"], r["deg"])] = dict(
                mos=float(r["mos_pred"]), noi=float(r["noi_pred"]),
                dis=float(r["dis_pred"]), col=float(r["col_pred"]),
                loud=float(r["loud_pred"]))
        return out
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------- 韵律统计
def prosody_stats(path, gap_thr=0.10):
    """整体韵律统计。★ 必须在完整帧网格上算有声占比/停顿，
    track_ex 只返回有声帧，会算出 share=1.0、gap=0。"""
    import parselmouth
    snd = parselmouth.Sound(path)
    dur_all = snd.duration
    pit = snd.to_pitch(time_step=0.005, pitch_floor=60, pitch_ceiling=500)
    f = np.asarray(pit.selected_array["frequency"])
    v = f > 0
    if v.sum() < 20:
        return {}
    dt = 0.005
    f0 = f[v]
    med = float(np.median(f0))
    lo, hi = np.percentile(f0, 5), np.percentile(f0, 95)
    st_range = float(12 * np.log2(hi / max(lo, 1e-6))) if lo > 0 else 0.0
    d = np.diff(12 * np.log2(np.maximum(f0, 1e-6)))
    slope = float(np.median(np.abs(d))) / (dt * 10) if len(d) else 0.0
    voiced_share = float(v.mean())
    # 词内断裂：只统计 >=gap_thr 的静音段
    best = cur = 0
    for t in (~v):
        cur = cur + 1 if t else 0
        best = max(best, cur)
    gap = best * dt
    ngap = 0
    cur = 0
    for t in (~v):
        cur = cur + 1 if t else 0
        if not t and cur * dt >= gap_thr:
            ngap += 1
        if not t:
            cur = 0
    # 能量包络粗糙度：5ms 帧 RMS 的二阶差分（越大越"抖"）
    x, xsr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(1)
    step = max(1, int(0.005 * xsr))
    n = len(x) // step
    r = np.sqrt(np.mean(x[: n * step].reshape(n, step) ** 2, axis=1) + 1e-12)
    if len(r) > 3:
        r2 = np.abs(np.diff(r, n=2))
        rough = float(np.median(r2) / max(np.median(r), 1e-9))
    else:
        rough = 0.0
    return dict(f0_med=round(med, 1), st_range=round(float(st_range), 2),
                slope=round(slope, 3), voiced_share=round(voiced_share, 3),
                gap_max=round(float(gap), 2), ngap=ngap,
                rough=round(rough, 4), dur=round(float(dur_all), 2))


# ---------------------------------------------------------------- 取样
def known_set():
    """已知好坏：audio 闸门 FAIL 的 take（坏）+ 闸门 OK/WARN 的 take（好）"""
    s = json.load(open("G:/_setup/_mt_adv_state.json", encoding="utf-8"))["units"]
    rows = []
    for u, x in s.items():
        for a in (x.get("attempts") or []):
            w = a.get("wav")
            if not w or not os.path.exists(w):
                continue
            g = a.get("guards") or {}
            v = g.get("verdict")
            if v == "FAIL" and "audio" in (g.get("failed") or []):
                lab = "BAD"
            elif v in ("OK", "WARN"):
                lab = "GOOD"
            else:
                continue
            rows.append(dict(uid=u, seed=a.get("seed"), cond=a.get("cond"),
                             wav=w, label=lab, verdict=v,
                             ref=a.get("ctl_wav") or w,
                             failed=g.get("failed") or []))
    return rows


def all_set():
    s = json.load(open("G:/_setup/_mt_adv_state.json", encoding="utf-8"))["units"]
    rows = []
    for u, x in s.items():
        pk = "G:/_setup/_mt_pick/%s.wav" % u
        if os.path.exists(pk):
            rows.append(dict(uid=u, seed="pick", cond="delivered", wav=pk,
                             label="DELIV", verdict="OK", ref=pk, failed=[]))
        for a in (x.get("attempts") or []):
            if a.get("wav") and os.path.exists(a["wav"]):
                g = a.get("guards") or {}
                rows.append(dict(uid=u, seed=a.get("seed"), cond=a.get("cond"),
                                 wav=a["wav"], label=(g.get("verdict") or "?"),
                                 verdict=g.get("verdict"),
                                 ref=a.get("ctl_wav") or a["wav"],
                                 failed=g.get("failed") or []))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="known", choices=["known", "all"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-nisqa", action="store_true")
    ap.add_argument("--manifest", default=None, help="JSON 列表，每项含 wav/label/ref")
    a = ap.parse_args()
    if a.manifest:
        rows = json.load(open(a.manifest, encoding="utf-8"))
    else:
        rows = known_set() if a.sets == "known" else all_set()
    if a.limit:
        rows = rows[:a.limit]
    print("n =", len(rows), file=sys.stderr)

    # ★ 模型分一律在「剪掉插入停顿」的版本上算
    tdir = tempfile.mkdtemp(prefix="nattrim_")
    for i, r in enumerate(rows):
        r["_t"] = trim_silence(r["wav"], os.path.join(tdir, "w%04d.wav" % i))
        if r.get("ref"):
            r["_tr"] = trim_silence(r["ref"], os.path.join(tdir, "r%04d.wav" % i))
    paths = [r["_t"] for r in rows]
    nq = {}
    if not a.no_nisqa:
        print("NISQA ...", file=sys.stderr)
        nq = nisqa_batch(paths)
        print("  got", len(nq), file=sys.stderr)

    for i, r in enumerate(rows):
        p = r["wav"]
        ref = r.get("_tr") or p
        try:
            r["squim"] = round(squim_mos(r["_t"], ref), 3)
        except Exception as e:
            r["squim"] = None
            r["squim_err"] = str(e)[:80]
        try:
            d = dnsmos(r["_t"])
            if d is None:
                raise RuntimeError("dnsmos None")
            r["dns_ovrl"] = round(float(d["ovrl_mos"]), 3)
            r["dns_sig"] = round(float(d["sig_mos"]), 3)
            r["dns_bak"] = round(float(d["bak_mos"]), 3)
        except Exception as e:
            r["dns_ovrl"] = None
            r["dns_err"] = str(e)[:100]
        n = nq.get(r["_t"])
        if n:
            r.update({("nq_" + k): round(v, 3) for k, v in n.items()})
        r.update(prosody_stats(p))
        if (i + 1) % 10 == 0:
            print("  %d/%d" % (i + 1, len(rows)), file=sys.stderr)

    out = a.out or ("G:/_setup/_nat_%s.json" % a.sets)
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("written", out)


if __name__ == "__main__":
    main()
