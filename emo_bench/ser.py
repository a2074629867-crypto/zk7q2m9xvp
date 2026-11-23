# -*- coding: utf-8 -*-
"""统一情绪打分接口 —— 三个模型同一入口，输出可比。

模型分工：
  vox_dim   Vox-Profile / wavmask-large MSP-Podcast 维度头（本地权重，2024 级 SOTA 维度模型）
            → arousal / valence / dominance，各 0–1
  e2v       emotion2vec+ large（FunASR / 阿里，2024 社区离散分类标杆）
            → 9 类概率 + 中文标签
  phys      纯物理量（不依赖任何模型，作为域外交叉验证）
            → F0 中位/跨度、能量、语速、HNR、谱倾斜

设计原则：任何模型的单点分数都不当结论，必须三轨交叉。
"""
import os, sys, json, math
import numpy as np

os.environ.setdefault("MODELSCOPE_CACHE", "G:/_setup/models/ms")
os.environ.setdefault("HF_HOME", "G:/_setup/models/hf")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

VOICE_LIB = "G:/voice_lib"
if VOICE_LIB not in sys.path:
    sys.path.insert(0, VOICE_LIB)


# ───────────────────────── 物理量 ─────────────────────────
def phys(path):
    """不依赖神经网络的声学量。用 parselmouth（Praat）拿 F0/HNR，numpy 拿能量。"""
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(path)
    try:
        snd = snd.resample(16000)
    except Exception:
        pass
    y = np.asarray(snd.values, dtype=np.float64).ravel()
    sr = int(snd.sampling_frequency)
    dur = len(y) / sr

    # 能量包络 → 语音段
    hop = int(sr * 0.02)
    n = max(1, len(y) // hop)
    fr = y[: n * hop].reshape(n, hop)
    rms = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    thr = np.percentile(db, 90) - 30
    voiced = db > thr
    if voiced.sum() < 3:
        voiced = db > (db.max() - 40)
    vspeech = float(voiced.mean())
    # 语音段平均能量（dBFS）
    vr = rms[voiced] if voiced.any() else rms
    speech_db = 20 * math.log10(float(np.sqrt((vr ** 2).mean())) + 1e-12)

    # F0（Praat 自相关）
    pitch = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=500)
    f0 = pitch.selected_array["frequency"]
    f0 = f0[f0 > 0]
    # HNR
    # ★ 2026-11-06 修正：原来直接对**整条**音频的 harmonicity 取中位数，
    #   而 Praat 对无周期帧（静音/清音）返回 -200 这个哨兵值。
    #   只要静音帧超过一半，中位数就整块塌成 -200 —— 于是这个指标
    #   量的其实是「静音占比」，不是「气声/嘶哑」。
    #   （实测 E_begging base 被判 -200，但它只是音量低；C_normal base 2.9，
    #     同一 ref 的 sad 却 -200，两者不可能差这么多。）
    #   ⇒ 只在浊音帧（pitch 有值）上取中位，并把哨兵值剔掉。
    try:
        harm = call(snd, "To Harmonicity (cc)", 0.01, 60, 0.1, 1.0)
        hnr = np.asarray(harm.values, dtype=np.float64).ravel()
        f0_full = pitch.selected_array["frequency"]
        m = min(len(hnr), len(f0_full))
        hnr, f0_full = hnr[:m], f0_full[:m]
        keep = (f0_full > 0) & np.isfinite(hnr) & (hnr > -100)
        hnr_voiced = hnr[keep]
        if len(hnr_voiced) >= 3:
            hnr_med = float(np.median(hnr_voiced))
        else:
            good = hnr[np.isfinite(hnr) & (hnr > -100)]
            hnr_med = float(np.median(good)) if len(good) else 0.0
    except Exception:
        hnr_med = 0.0

    return dict(
        dur=round(dur, 3),
        f0_med=round(float(np.median(f0)), 1) if len(f0) else 0.0,
        f0_p10=round(float(np.percentile(f0, 10)), 1) if len(f0) else 0.0,
        f0_p90=round(float(np.percentile(f0, 90)), 1) if len(f0) else 0.0,
        f0_std=round(float(np.std(f0)), 1) if len(f0) else 0.0,
        speech_db=round(speech_db, 1),
        voiced_ratio=round(vspeech, 3),
        hnr=round(hnr_med, 1),
    )


# ───────────────────────── vox_dim ─────────────────────────
class VoxDim:
    name = "vox_dim"

    def __init__(self):
        import vox_profile as V
        self.V = V
        self.m = V.load("dim", "wavlm-large-msp-podcast-emotion-dim")

    def score(self, path):
        import torch
        y = self.V.read16(path, hq=True)
        if len(y) < 1600:
            return None
        x = torch.from_numpy(self.V.norm(self.V.cut(y))).float().unsqueeze(0)
        with torch.no_grad():
            r = self.m(x)
        return {k: round(float(v), 4) for k, v in r.items()}


# ───────────────────────── emotion2vec ─────────────────────────
class E2V:
    name = "e2v"

    def __init__(self, model="iic/emotion2vec_plus_large"):
        import os
        from funasr import AutoModel
        # ★ 本地权重优先：funasr 1.4.22 里 "iic/emotion2vec_plus_large" 没注册，
        #   会去 modelscope 拉一张 png 然后 404，报 "model is not registered"。
        #   权重本来就在本地，直接给目录路径就绕开了整条下载链路。
        local = "G:/_setup/models/ms/" + model
        if os.path.isdir(local) and os.path.exists(os.path.join(local, "model.pt")):
            model = local
        self.m = AutoModel(model=model, disable_update=True, device="cpu")
        self.model_id = model


    def score(self, path):
        r = self.m.generate(path, granularity="utterance", extract_embedding=False)
        if not r:
            return None
        e = r[0]
        labels = e.get("labels") or []
        scores = e.get("scores") or []
        if isinstance(labels, str):
            labels = [labels]
        out = {str(l): round(float(s), 4) for l, s in zip(labels, scores)}
        if not out:
            return None
        top = max(out, key=out.get)
        out["_top"] = top
        return out


# ───────────────────────── 加载器 ─────────────────────────
_CACHE = {}


def get(kind):
    if kind in _CACHE:
        return _CACHE[kind]
    if kind == "vox_dim":
        m = VoxDim()
    elif kind == "e2v":
        m = E2V()
    else:
        raise ValueError(kind)
    _CACHE[kind] = m
    return m


# emotion2vec 的 9 类 → 我们关心的粗粒度
E2V_CN = {
    "angry": "愤怒", "happy": "高兴", "sad": "悲伤", "afraid": "恐惧",
    "disgusted": "厌恶", "surprised": "惊讶", "calm": "平静",
    "melancholic": "忧郁", "neutral": "中性", "other": "其他",
    "<unk>": "未知",
}

# Expresso style → emotion2vec 期望类别（用于算 top-1 命中）
STYLE2E2V = {
    "default": {"neutral", "calm"},
    "happy": {"happy"},
    "sad": {"sad", "melancholic"},
    "confused": {"surprised", "afraid", "other", "neutral"},
    "whisper": {"calm", "neutral", "other"},
    "laughing": {"happy"},
    "enunciated": {"neutral", "calm"},
    "emphasis": {"neutral", "calm", "angry"},
}
