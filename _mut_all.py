# -*- coding: utf-8 -*-
"""_mut_all.py —— 句内音色突变检测：多方案对比（有 ground truth 的基准）。

阶段：
  --cache   把每条 wav 按 1.5s/0.25s 滑窗算 embedding，缓存在 _mutbench/emb/<model>/<sid>.npz
  --eval    读缓存，跑多种「打分+定位」方案，输出 AUC / TPR@FPR / 定位误差对比表

方案维度：
  A. embedding 模型：campp_en(现用) / campp_zh / eres2net / r34 / ecapa
  B. 分段策略：silence（现有：按 −45dB 静音切段）/ win（固定滑窗）
  C. 打分：adj（相邻窗最小余弦）/ cp（左右窗口均值对比，变点式）/ silence_min（段间最小余弦）

基线 = campp_en + silence + silence_min，就是线上 `ch123_segcheck.py` 的做法。
"""
import json, os, sys, argparse, subprocess, collections
import numpy as np

sys.path.insert(0, "G:/_setup")
import kaldi_native_fbank as knf
import soundfile as sf
import onnxruntime as ort

BENCH = "G:/_setup/_mutbench"
CACHE = os.path.join(BENCH, "emb")
SR16 = 16000
FF = r"E:/tool/oopz/ffmpeg.exe"

MODELS = {
    "campp_en": ("E:/tts-models/spk/wespeaker_en_voxceleb_CAM++.onnx", False),
    "campp_zh": ("E:/tts-models/spk/3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx", True),
    "eres2net": ("E:/tts-models/spk/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx", True),
    "r34": ("G:/_setup/models/sv_hub/voxceleb_resnet34_LM.onnx", True),
    "r293": ("G:/_setup/models/sv_hub/voxceleb_resnet293_LM.onnx", True),
}

WIN, HOP = 1.5, 0.25
MIN_WIN = 0.60          # 窗内有效帧下限
SIL_DB = -45.0          # 与 ch123_segcheck 一致
GAP_MIN = 0.12
MIN_SEG = 0.25
PAD_TO = 2.0


# ---------------- 基础 ----------------
def to16(path):
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    y = y.mean(1)
    if sr != SR16:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(int(sr), SR16)
        y = resample_poly(y, SR16 // g, sr // g).astype(np.float32)
    return y


def fbank(a, cmn):
    o = knf.FbankOptions()
    o.frame_opts.samp_freq = SR16
    o.frame_opts.frame_length_ms = 25.0
    o.frame_opts.frame_shift_ms = 10.0
    o.frame_opts.dither = 0.0
    o.frame_opts.preemph_coeff = 0.97
    o.frame_opts.remove_dc_offset = True
    o.frame_opts.window_type = "povey"
    o.frame_opts.snip_edges = True
    o.mel_opts.num_bins = 80
    o.mel_opts.low_freq = 20.0
    o.mel_opts.high_freq = -400.0
    o.use_energy = False
    o.use_log_fbank = True
    o.use_power = True
    f = knf.OnlineFbank(o)
    f.accept_waveform(SR16, a.tolist())
    f.input_finished()
    n = f.num_frames_ready
    m = np.empty((n, 80), dtype=np.float32)
    for i in range(n):
        m[i] = f.get_frame(i)
    if cmn:
        m -= m.mean(0, keepdims=True)
    return m


class M:
    _c = {}

    def __init__(self, name):
        self.name = name
        p, self.cmn = MODELS[name]
        if name not in M._c:
            so = ort.SessionOptions()
            so.log_severity_level = 3
            so.intra_op_num_threads = 6
            M._c[name] = ort.InferenceSession(p, so, providers=["CPUExecutionProvider"])
        self.s = M._c[name]
        self.i = self.s.get_inputs()[0].name

    def emb_f(self, feats):
        """feats[T,80] -> L2 归一向量"""
        v = self.s.run(None, {self.i: feats[None].astype(np.float32)})[0][0].astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)


def cos(a, b):
    return float(a @ b)


def nrm(v):
    return v / (np.linalg.norm(v) + 1e-9)


# ---------------- 缓存滑窗 embedding ----------------
def do_cache(names):
    idx = json.load(open(os.path.join(BENCH, "index.json"), encoding="utf-8"))
    for name in names:
        outdir = os.path.join(CACHE, name)
        os.makedirs(outdir, exist_ok=True)
        m = M(name)
        for k, it in enumerate(idx, 1):
            dst = os.path.join(outdir, it["sid"] + ".npz")
            if os.path.exists(dst):
                continue
            a = to16(os.path.join(BENCH, "wav", it["sid"] + ".wav"))
            feats = fbank(a, m.cmn)
            T = feats.shape[0]
            dur = len(a) / SR16
            # 滑窗
            centers, embs, rms = [], [], []
            t = 0.0
            while t + WIN <= dur + 1e-6:
                s, e = int(t * 100), int((t + WIN) * 100)
                e = min(e, T)
                if e - s < MIN_WIN * 100:
                    break
                seg = a[int(t * SR16):int((t + WIN) * SR16)]
                r = float(np.sqrt(np.mean(seg ** 2)) + 1e-12)
                centers.append(t + WIN / 2)
                embs.append(m.emb_f(feats[s:e]))
                rms.append(20 * np.log10(r))
                t += HOP
            np.savez(dst, centers=np.array(centers), embs=np.stack(embs),
                     rms=np.array(rms), dur=np.array([dur]))
            if k % 40 == 0:
                print("  %s %d/%d" % (name, k, len(idx)), flush=True)


# ---------------- 打分方案 ----------------
def score_sep(centers, embs, k=5, guard=0.25):
    """结构性分离度：段内要「自己像自己」，段间要「不像」，才算真变点。

    separation = mean(intra_L, intra_R) − cross(L,R)
      · 换人：段内像（intra≈0.6+）、段间不像（cross 低） ⇒ 大正数
      · 情绪起伏 / 短窗噪声：段内自己就不像（intra 也低） ⇒ 分数被压回 0 附近
    这一项专门用来压掉「同人不同情绪」的误报（实测那组 segment 间余弦与换人组完全重叠）。
    """
    n = len(embs)
    best, bt = -9.0, None
    for i in range(k, n - k + 1):
        t = (centers[i - 1] + centers[i]) / 2
        # 过渡带：距切点 < guard 的窗可能混了两个人的声音，两侧都剔掉
        li = [j for j in range(i - k, i) if abs(centers[j] - t) >= guard]
        ri = [j for j in range(i, i + k) if abs(centers[j] - t) >= guard]
        if len(li) < 2 or len(ri) < 2:
            continue
        L, R = embs[li], embs[ri]

        def intra(X):
            c = X @ X.T
            m = len(X)
            return float((c.sum() - np.trace(c)) / (m * (m - 1)))

        cross = float(nrm(L.mean(0)) @ nrm(R.mean(0)))
        s = (intra(L) + intra(R)) / 2 - cross
        if s > best:
            best, bt = s, t
    if bt is None:
        return None, None
    return best, bt


def score_cp(centers, embs, k=3):
    """变点式：对每个步点 i，左 k 窗均值 vs 右 k 窗均值 的余弦（1-cos = 突变强度）"""
    n = len(embs)
    best, bt = 1.0, None
    for i in range(k, n - k + 1):
        L = nrm(embs[max(0, i - k):i].mean(0))
        R = nrm(embs[i:i + k].mean(0))
        c = cos(L, R)
        if c < best:
            best, bt = c, (centers[i - 1] + centers[i]) / 2
    if bt is None:
        return None, None
    return 1.0 - best, bt


def score_adj(centers, embs):
    n = len(embs)
    if n < 2:
        return None, None
    cs = [cos(embs[i], embs[i + 1]) for i in range(n - 1)]
    j = int(np.argmin(cs))
    return 1.0 - cs[j], (centers[j] + centers[j + 1]) / 2


def score_silence(a, m):
    """复现 ch123_segcheck：−45dB 静音切段 → 每段循环补长到 2s → 段间两两余弦最小值"""
    sr = SR16
    win, hop = int(0.02 * sr), int(0.01 * sr)
    db = []
    for i in range(0, max(1, len(a) - win), hop):
        s = a[i:i + win]
        db.append(20 * np.log10(np.sqrt((s ** 2).mean()) + 1e-12))
    db = np.array(db)
    if not len(db):
        return None, None
    thr = max(db.max() - 35.0, SIL_DB)
    voiced = db > thr
    # 连续有声区 -> 段
    segs, s = [], None
    for i, v in enumerate(voiced):
        if v and s is None:
            s = i
        elif not v and s is not None:
            segs.append((s * 0.01, i * 0.01))
            s = None
    if s is not None:
        segs.append((s * 0.01, len(voiced) * 0.01))
    # 合并间隔小的
    merged = []
    for t0, t1 in segs:
        if merged and t0 - merged[-1][1] < GAP_MIN:
            merged[-1] = (merged[-1][0], t1)
        else:
            merged.append((t0, t1))
    merged = [(t0, t1) for t0, t1 in merged if t1 - t0 >= MIN_SEG and t1 - t0 > 0.08]
    if len(merged) < 2:
        return None, None
    feats = fbank(a, m.cmn)
    T = feats.shape[0]
    embs = []
    for t0, t1 in merged:
        s0, e0 = int(t0 * 100), min(int(t1 * 100), T)
        if e0 - s0 < 30:
            embs.append(None)
            continue
        f = feats[s0:e0]
        reps = max(1, int(round(PAD_TO / max(0.05, (t1 - t0)))))
        f = np.tile(f, (reps, 1))[:int(PAD_TO * 100)]
        embs.append(m.emb_f(f))
    valid = [e for e in embs if e is not None]
    if len(valid) < 2:
        return None, None
    sims, worst = [], None
    for i, e in enumerate(embs):
        if e is None:
            continue
        others = [embs[j] for j in range(len(embs)) if j != i and embs[j] is not None]
        msim = float(np.mean([cos(e, o) for o in others]))
        sims.append(msim)
        if worst is None or msim < worst[0]:
            worst = (msim, merged[i][0])
    return 1.0 - min(sims), worst[1]


# ---------------- 评测 ----------------
def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    if not len(pos) or not len(neg):
        return float("nan")
    s = np.concatenate([pos, neg])
    r = s.argsort().argsort() + 1
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def do_eval(names, plans):
    idx = {x["sid"]: x for x in json.load(open(os.path.join(BENCH, "index.json"), encoding="utf-8"))}
    rows = []
    for name in names:
        cache_dir = os.path.join(CACHE, name)
        if not os.path.isdir(cache_dir):
            print("跳过（无缓存）:", name)
            continue
        for plan in plans:
            res = {}
            for sid, it in idx.items():
                p = os.path.join(cache_dir, sid + ".npz")
                if not os.path.exists(p):
                    continue
                z = np.load(p)
                if plan.startswith("silence"):
                    a = to16(os.path.join(BENCH, "wav", sid + ".wav"))
                    sc, pos = score_silence(a, M(name))
                elif plan == "cp3":
                    sc, pos = score_cp(z["centers"], z["embs"], 3)
                elif plan == "cp5":
                    sc, pos = score_cp(z["centers"], z["embs"], 5)
                elif plan.startswith("sep"):
                    sc, pos = score_sep(z["centers"], z["embs"], int(plan[3:]))
                elif plan == "adj":
                    sc, pos = score_adj(z["centers"], z["embs"])
                else:
                    raise SystemExit("未知方案 " + plan)
                if sc is not None:
                    res[sid] = (sc, pos)
            # 统计
            def grp(kind):
                return [(s, res[s]) for s in res if idx[s]["kind"] == kind]
            pos_h, pos_s = grp("POS_hard"), grp("POS_soft")
            neg_e, neg_r = grp("NEG_emo"), grp("NEG_real")
            neg_all = neg_e + neg_r
            allpos = pos_h + pos_s
            a1 = auc([x[1][0] for x in allpos], [x[1][0] for x in neg_all])
            a2 = auc([x[1][0] for x in pos_h], [x[1][0] for x in neg_all])
            # 阈值：NEG p95
            thr = float(np.percentile([x[1][0] for x in neg_all], 95)) if neg_all else 0
            def tpr(g):
                return sum(1 for _, (s, _) in g if s > thr) / max(1, len(g))
            def loc(g):
                e = [abs(p - idx[sid]["cut"]) for sid, (sc, p) in g
                     if sc > thr and p is not None and idx[sid]["cut"] is not None]
                return (float(np.mean(e)) if e else float("nan"),
                        sum(1 for x in e if x <= 0.75) / max(1, len([1 for sid, (sc, p) in g if sc > thr])))
            rows.append(dict(model=name, plan=plan, auc=a1, auc_hard=a2, thr=round(thr, 4),
                             npos=len(allpos), nneg=len(neg_all),
                             tpr_hard=tpr(pos_h), tpr_soft=tpr(pos_s),
                             tpr_all=tpr(allpos),
                             fpr_emo=tpr(neg_e), fpr_real=tpr(neg_r),
                             loc_mae=loc(pos_h)[0], loc_hit=loc(pos_h)[1]))
            print("  %-9s %-8s AUC %.3f | thr %.3f | TPR hard %.0f%% soft %.0f%% | FPR emo %.0f%% real %.0f%% | 定位MAE %.2fs 命中 %.0f%%"
                  % (name, plan, a1, thr, tpr(pos_h) * 100, tpr(pos_s) * 100,
                     tpr(neg_e) * 100, tpr(neg_r) * 100, loc(pos_h)[0], loc(pos_h)[1] * 100), flush=True)
    json.dump(rows, open(os.path.join(BENCH, "eval.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="")
    ap.add_argument("--eval", default="")
    ap.add_argument("--plans", default="silence,cp3,cp5,adj")
    a = ap.parse_args()
    if a.cache:
        do_cache(a.cache.split(","))
    if a.eval:
        do_eval(a.eval.split(","), a.plans.split(","))
