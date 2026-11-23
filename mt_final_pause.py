# -*- coding: utf-8 -*-
"""生产链最后一环：标点停顿注入 + 逐条底噪匹配（原子操作）

链路位置
  ch123/*.wav  →  ch123_final_build.py（降速 + 整体增益 −24dBFS）  →  **本脚本**  →  交付

为什么合成一步
  先插数字零、再跑 room_tone.py --match 会读两次盘、做两次增益；
  且 room_tone 的 --match 走 voice_floor_db（对这批文件实测偏高 20dB，见 _noise_probe.py），
  插槽电平会和文件原有静音对不上 —— 反而制造出第二种底噪。

插进插槽的是什么
  噪声床切片，不是零。电平与纹理都取自本文件：
    · 电平 = 20ms 帧里「比中位低 25dB 以上、且不是数字零」的帧的中位数
    · 纹理 = 同一批帧的 Welch 功率谱，随机相位合成（不循环真人片段）
    · 与本批稳健基线相差 > 6dB 时钳到基线上 —— 否则相邻两句底噪能差 20dB，拼接照样假
    · 本文件没有可用静音帧（纯零文件）→ 电平用基线，纹理用 --tone 面板 / 内建粉噪

同时补原有静音
  dots.tts 输出的静音段是数字零（−199.9 dB）。只补插槽会让「新插的有底噪、原有的没有」，
  对比之下更假 ⇒ --fill-existing（默认开）把 < −90dB 的帧也铺上同电平噪声。

用法
  python -u mt_final_pause.py --in G:/_setup/ch123_final --out G:/_setup/ch123_final_pause
  python -u mt_final_pause.py --in ... --out ... --dry          # 只出计划，不写音频
  python -u mt_final_pause.py --in ... --out ... --only L046,L005
"""
import argparse
import glob
import hashlib
import json
import math
import os
import sys

os.environ.setdefault('HF_HOME', r'C:/Users/86178/.cache/huggingface')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
sys.path.insert(0, r'G:/_setup')

import numpy as np
import soundfile as sf

from _wtlib import word_times_cached as word_times
from insert_pauses import plan_from_proto, tail_punct
from mt_pause_rules import TIERS_DEFAULT, TIERS_DIALOG, DIALOG_CAP, plan_from_text
from room_tone import _resample, _rms

BANK_DEFAULT = r'G:/_setup/pause_bank.json'
TIERS_DEFAULT_PATH = r'G:/_setup/pause_tiers.json'
TONE_DEFAULT = r'G:/_setup/room_tone_panel.wav'   # 从 wonder_train.wav 2700 个安静帧提取

# 判定「可用静音帧」的门限
QUIET_BELOW_MED = 25.0     # 比中位低多少 dB 才算安静
ZERO_DB = -90.0            # 低于此视为数字零
NOISE_FLOOR_DB = -85.0     # 低于此视为「没有底噪可测」
MIN_QUIET_FRAMES = 10
LEVEL_CLAMP_DB = 6.0       # 与基线最大偏差
# 统一场景底噪：马修真人原声实测 −55.9 dB，留 2 dB 余量，避免比真人录音更响
SCENE_LEVEL_DB = -58.0
# 峰值 ≤ −1 dBFS（REQUIREMENTS 技术红线，20*log10(0.891) = −1.00）。
# 原来放行到 0.999（−0.01dBFS），比红线高近 1dB。
PEAK_CEIL = 0.891
NO_TRIM_MIN = 0.15     # intent=no 的位置，间隙超过此值才压（低于它听不出来）
NO_KEEP = 0.06         # 压到只剩多少：留一点，别压成完全黏死
OPT_ENOUGH = 0.05      # intent=opt 的位置已有 50ms 间隙就不再塞

# 逐处抖动：同一档位不能给同一个值。
# 依据（2026-10-29 实测）：真人句号 IQR 1.375~1.978，log 标准差 ≈ 0.27；
# 我们处理后的句号 IQR 只有 0.68~0.84（相对跨度 20% vs 真人 34%），
# 因为旧逻辑 add = tgt - cur 会把所有「比目标短」的位置抬到**同一个值**。
VARY_SIGMA = 0.0       # 额外抖动的 σ（默认关：模型自身跨度已够，抖动会打乱先后顺序）
VARY_CLIP = 2.0        # 截到 ±2σ，避免个别位置离谱
SHAPE_ALPHA = 1.0      # 1.0 = 完全保留模型自身的相对长短（按档位中位缩放）
TRIM_SLOP = 0.25       # 比目标长出这么多才值得往回删（否则保留模型的自然长停）
TRIM_CAP = 0.35        # 单处最多删多少
LLM_TRIM_SLOP = 0.10   # LLM 判了绝对值：长出 0.10s 就该收回来（比统计档位更严）
LLM_DEFAULT = r'G:/_setup/pause_llm.json'


def jitter(key, idx, word, sigma):
    """确定性抖动：同一 (文件, 边界下标, 前词) 永远得到同一个因子。

    为什么不用随机数种子整条打乱：要可复现、可回滚、可逐处对照。
    为什么需要它：文本只能预测停顿的一小部分（拟合 R²=0.26），
    真实长短主要由语义与换气决定 ⇒ 与其给常数，不如按真人分布抽一个确定性的值。
    """
    if sigma <= 0:
        return 1.0
    h = hashlib.blake2b(('%s|%d|%s' % (key, idx, word)).encode('utf-8'),
                        digest_size=8).digest()
    u1 = int.from_bytes(h[:4], 'little') / 2 ** 32
    u2 = int.from_bytes(h[4:], 'little') / 2 ** 32
    u1 = min(max(u1, 1e-9), 1 - 1e-9)
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    z = max(-VARY_CLIP, min(VARY_CLIP, z))
    return math.exp(sigma * z)


# ---------------------------------------------------------------- 帧 / 底噪

def frame_db(x, sr, fl=0.02, hop=0.01):
    n = max(1, int(fl * sr))
    h = max(1, int(hop * sr))
    k = max(1, (len(x) - n) // h + 1)
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    np.clip(idx, 0, len(x) - 1, out=idx)
    r = np.sqrt((x[idx].astype(np.float64) ** 2).mean(1) + 1e-20)
    return 20 * np.log10(r + 1e-12), n, h


def quiet_mask(db, med):
    return (db < med - QUIET_BELOW_MED) & (db > NOISE_FLOOR_DB)


def noise_psd(x, sr, db, n, h, mask, max_frames=200):
    """用被选中的安静帧估功率谱（Welch 中位）。"""
    from scipy.signal import welch
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return None
    idx = idx[::max(1, len(idx) // max_frames)][:max_frames]
    specs = []
    for i in idx:
        s = int(i * h)
        seg = x[s:s + n].astype(np.float64)
        if len(seg) < n:
            continue
        f, p = welch(seg, fs=sr, nperseg=min(1024, n), nfft=2048)
        specs.append(p)
    if len(specs) < 3:
        return None
    return f, np.median(np.asarray(specs), axis=0)


def bed_from_self(x, sr, target_db=None, min_sec=0.30):
    """从本条音频自己的静音段切一段真实房间声当底噪（纹理天然，不是合成粉噪）。

    为什么需要它：需求 25a 要求「停顿处不许是数字零」，而 2026-10-30 用户明确
    否掉了 synth_bed 的粉噪（−56dBFS 上仍能听到「嘶——」，长停顿处比真空更假）。
    两者唯一的交集就是这条：**用它自己的底噪**。实测我们的 wav 静音段 ≈ −60dBFS、
    716 条里没有一条是数字零，所以这段噪声真实存在，采样即可。

    target_db=None 时保持原始电平；给了就按 RMS 抬/压到该电平（本项目用 −58）。
    找不到合格静音段（如整条都是数字零、或没有 ≥min_sec 的连续静音）返回 None，
    调用方应退回「不铺」并在报告里留痕，不许静默造噪。
    """
    db, n, h = frame_db(x, sr)
    if len(db) < 10:
        return None, None
    # ★ 不能用 quiet_mask(med−25)：那是给「整条找安静段」用的，对底噪较高
    #   （−55 左右、比语音只低 20dB）的条目会一个帧都选不出来。
    #   改成围绕本条的 p5 取一个窄带：把「它自己最安静的那一档」当底噪。
    p5 = float(np.percentile(db, 5))
    lo = max(p5 - 3.0, NOISE_FLOOR_DB)
    hi = p5 + 6.0
    idx = np.flatnonzero((db >= lo) & (db <= hi))
    if len(idx) < max(4, int(min_sec * sr / h)):
        return None, None
    # 取最长连续安静段（连续帧索引差 == 1）
    best = (0, 0)
    s = idx[0]
    prev = idx[0]
    for i in idx[1:]:
        if i - prev > 1:
            if prev - s > best[1] - best[0]:
                best = (s, prev)
            s = i
        prev = i
    if prev - s > best[1] - best[0]:
        best = (s, prev)
    a = int(best[0] * h)
    b = min(len(x), int(best[1] * h) + n)
    if b - a < int(min_sec * sr):
        # 短句里常常没有 0.3s 的**连续**静音（换气只有 0.1~0.2s）。
        # 退一步：把这些短静音帧逐段拼起来当床 —— 纹理仍是它自己的，不造假。
        piece = max(1, int(0.08 * sr))
        parts = []
        need = int(min_sec * sr)
        for i in idx:
            s0 = int(i * h)
            seg = x[s0:s0 + piece]
            if len(seg) >= piece // 2:
                parts.append(seg)
            if sum(len(p_) for p_ in parts) >= need:
                break
        if not parts:
            return None, None
        seg = np.concatenate(parts)
        if len(seg) < int(0.10 * sr):
            return None, None
    else:
        seg = x[a:b].astype(np.float32).copy()
    seg = np.asarray(seg, dtype=np.float32)
    # 两端 5ms 淡变，防止循环接缝咔哒
    nf = max(1, int(0.005 * sr))
    if len(seg) > 2 * nf:
        seg[:nf] *= np.linspace(0.0, 1.0, nf, dtype=np.float32)
        seg[-nf:] *= np.linspace(1.0, 0.0, nf, dtype=np.float32)
    src_db = None
    if target_db is not None:
        r = _rms(seg)
        if r < 1e-12:
            return None, None
        src_db = round(float(20 * __import__('math').log10(r)), 1)
        seg = (seg / r * (10.0 ** (target_db / 20.0))).astype(np.float32)
    return seg, src_db


def flat_psd(sr, nfft=2048, slope_db_per_oct=-3.0):
    """兜底纹理：粉噪型（每倍频程 −3dB），没有可测底噪时用。"""
    f = np.fft.rfftfreq(nfft, 1.0 / sr)
    f[0] = f[1]
    p = (f / 1000.0) ** (slope_db_per_oct / 3.0103)
    p[f < 60] = 0.0
    return f, p


def synth_bed(n, sr, psd, level_db, rng):
    """随机相位合成 n 样本噪声床，RMS 归一到 level_db。"""
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    nfft = int(2 ** np.ceil(np.log2(max(n, 4096))))
    freq = np.fft.rfftfreq(nfft, 1.0 / sr)
    if psd is None:
        f, p = flat_psd(sr, nfft)
        shape = np.sqrt(np.maximum(p, 0))
    else:
        f, p = psd
        # 面板采样率可能低于目标（32k vs 48k）：超出范围按 0 处理，不做端点外推
        shape = np.sqrt(np.maximum(np.interp(freq, f, p, right=0.0), 0))
    shape = shape + 1e-30
    shape[freq < 60] = 0.0
    ph = rng.uniform(0.0, 2.0 * np.pi, len(shape))
    tone = np.fft.irfft(shape * np.exp(1j * ph), nfft)
    r = _rms(tone)
    if r < 1e-12:
        return np.zeros(n, dtype=np.float32)
    tone = tone / r * (10.0 ** (level_db / 20.0))
    return tone[:n].astype(np.float32)


# ---------------------------------------------------------------- 裁剪 / 拼接

def apply_cuts(x, sr, cuts, bed, fade=0.010):
    """cuts=[(cut_sample_idx, add_sec)]，从后往前插噪声切片。"""
    out = x.copy()
    nf = max(1, int(fade * sr))
    for c, add in sorted(cuts, key=lambda p: -p[0]):
        c = int(np.clip(c, 1, len(out) - 1))
        head, tail = out[:c].copy(), out[c:].copy()
        if len(head) > nf and len(tail) > nf:
            head[-nf:] *= np.linspace(1.0, 0.0, nf, dtype=out.dtype)
            tail[:nf] *= np.linspace(0.0, 1.0, nf, dtype=out.dtype)
        ns = max(1, int(add * sr))
        # 噪声片从全长床里循环取；两侧本来就是同电平噪声，只需极短淡变防咔哒
        seg = np.resize(bed, ns) if len(bed) < ns else bed[:ns]
        seg = seg.astype(np.float32, copy=True)
        fd = min(max(1, int(0.005 * sr)), max(1, ns // 2))
        seg[:fd] *= np.linspace(0.0, 1.0, fd)
        seg[-fd:] *= np.linspace(1.0, 0.0, fd)
        out = np.concatenate([head, seg, tail])
    return out


def _voiced_ref(x, sr):
    """该条语音电平参考：20ms 帧能量的 p90。"""
    hop = max(1, int(0.020 * sr))
    n = len(x) // hop
    if n < 3:
        return float('nan')
    d = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop).astype(np.float64) ** 2)
                             .mean(1)) + 1e-12)
    return float(np.percentile(d, 90))


def safe_del_pos(x, sr, t, amt, ref_db, margin=25.0, search=0.20):
    """在 t 附近找「真正安静」的 amt 长度窗口，返回中心样本点；找不到就返回 None。

    为什么必须找：ASR 的 gap 中点是**词边界中点**，不等于静音中点。
    实测 L068 的 `house,` 中点 RMS 只比语音低 7dB（那是换气 + 词尾），
    直接按时间戳删会切掉气口甚至辅音。删之前必须先量能量。
    """
    nd = max(2, int(amt * sr))
    c = int(t * sr)
    lo = max(1, c - int(search * sr) - nd // 2)
    hi = min(len(x) - nd - 1, c + int(search * sr) - nd // 2)
    if hi <= lo:
        lo = max(1, min(c - nd // 2, len(x) - nd - 2))
        hi = lo
    best, best_db = None, 1e9
    step = max(1, int(0.005 * sr))
    for a in range(lo, hi + 1, step):
        seg = x[a:a + nd]
        if len(seg) < nd:
            break
        db = 20 * np.log10(np.sqrt((seg.astype(np.float64) ** 2).mean()) + 1e-12)
        if db < best_db:
            best, best_db = a, db
    if best is None or not np.isfinite(ref_db):
        return None
    return (best + nd // 2, best_db) if best_db < ref_db - margin else None


def apply_edits(x, sr, edits, bed, fade=0.010):
    """edits=[(t_sec, 'ins'|'del', amount_sec, label)]，从后往前执行（索引不偏移）。

    ins  插噪声切片（不是数字零）
    del  只删 gap 中段，且**必须先验证是静音**（safe_del_pos）：
         留 25ms 两头 + 在 ±0.20s 内找最安静的窗口；找不到就跳过并记 'skip'。
         —— 「不该停却停了」比「该停没停」更伤，一句台词会被切成两句，
            例如 L014 `now, [0.36s] then?` / L008 `new, [0.34s] will it?`
    """
    out = x
    nf = max(1, int(fade * sr))
    ref = _voiced_ref(x, sr)
    skipped = []
    for e in sorted(edits, key=lambda e: -e[0]):
        t, kind, amt = e[0], e[1], e[2]
        if kind == 'ins':
            c = int(np.clip(int(t * sr), 1, len(out) - 1))
            head, tail = out[:c].copy(), out[c:].copy()
            if len(head) > nf and len(tail) > nf:
                head[-nf:] *= np.linspace(1.0, 0.0, nf, dtype=out.dtype)
                tail[:nf] *= np.linspace(0.0, 1.0, nf, dtype=out.dtype)
            ns = max(1, int(amt * sr))
            seg = np.resize(bed, ns).astype(np.float32, copy=True)
            fd = min(max(1, int(0.005 * sr)), max(1, ns // 2))
            seg[:fd] *= np.linspace(0.0, 1.0, fd)
            seg[-fd:] *= np.linspace(1.0, 0.0, fd)
            out = np.concatenate([head, seg, tail])
        elif kind == 'del':
            nd = max(1, int(amt * sr))
            hit = safe_del_pos(out, sr, t, amt, ref)
            if hit is None:
                skipped.append((round(t, 3), round(amt, 3)))
                continue          # 附近没有足够安静的窗口，宁可不停也不切气口
            c, _db = hit
            a = max(1, c - nd // 2)
            b = min(len(out) - 1, a + nd)
            if b - a < 2:
                continue
            head, tail = out[:a].copy(), out[b:].copy()
            if len(head) > nf and len(tail) > nf:
                head[-nf:] *= np.linspace(1.0, 0.0, nf, dtype=out.dtype)
                tail[:nf] *= np.linspace(0.0, 1.0, nf, dtype=out.dtype)
            out = np.concatenate([head, tail])
    return out, skipped


def add_bed_all(x, sr, bed):
    """把 bed 整条叠加到 x 上。

    为什么不只填「< −90dB 的零段」：实测只填零段会让底噪在 −58 与 −86 之间跳
    （L046 p05 仍是 −86.6、L053 是 −74.2）—— 语音自然衰减段不在 mask 内，反而更静，
    听起来还是忽有忽无。整条叠加后所有低电平帧都落到 −58 附近：
    零段 −199→−58，衰减段 −86→−58，语音段 −24→−23.99（0.001dB，可忽略）。
    返回 (y, 原文件里的零帧数)，零帧数仅作报告用。"""
    db, _, _ = frame_db(x, sr)
    nzero = int((db < ZERO_DB).sum())
    if len(bed) == 0:
        # 默认路径：不铺底噪，原样返回。零帧数仍回报，用于诊断「真空静音」有多少处。
        return x.astype(np.float32, copy=False), nzero
    return (x.astype(np.float64) + np.resize(bed, len(x))).astype(np.float32), nzero


# ---------------------------------------------------------------- 主流程

def bank_to_proto(path):
    proto = {}
    if path and os.path.exists(path):
        raw = json.load(open(path, encoding='utf-8'))
        for k, v in raw.items():
            proto[k] = float(v['median']) if isinstance(v, dict) else float(v)
    c, p = proto.get(',', 0.55), proto.get('.', 0.85)
    for k, frac in ((';', 0.85), (':', 0.75), ('!', 1.0), ('?', 1.0),
                    ('\u2014', 0.75), ('\u2013', 0.75)):
        proto.setdefault(k, c + (p - c) * frac)
    # ★ 2026-11-11：pause_bank 的 '.' 是 **1.56（条间值，含换气）**。ASR 回退路径
    #   没有句法结构，分不清「条内分句」还是「条末」，若直接取 1.56，条内句号
    #   会膨胀 78~90%（需求 19c 原话：L085 只 10 词却会膨胀 90%）。
    #   条间停顿由拼接器负责，这里统一按 dot_inner 给，宁可短、不许长。
    if '.' in proto:
        proto['.'] = 0.85
    return proto


def measure(x, sr):
    db, n, h = frame_db(x, sr)
    med = float(np.median(db))
    m = quiet_mask(db, med)
    nq = int(m.sum())
    level = float(np.median(db[m])) if nq else float('nan')
    return dict(db=db, n=n, h=h, med=med, mask=m, nq=nq, level=level)


def credible(st, min_n=20, max_iqr=6.0, min_zero=0.03):
    """本文件是否存在「稳态底噪」值得跟随。
    实测：12%~41% 帧是数字零，其余安静帧混着语音衰减尾巴（IQR 到 17dB）
    ⇒ 只有 n 够多、分布够集中、且确实存在零段时才认为它有一个噪声平台。"""
    if st['nq'] < min_n:
        return False, 'quiet_n=%d' % st['nq']
    db = st['db'][st['mask']]
    iqr = float(np.percentile(db, 75) - np.percentile(db, 25))
    if iqr > max_iqr:
        return False, 'IQR=%.1fdB' % iqr
    zero = float((st['db'] < ZERO_DB).mean())
    if zero < min_zero:
        return False, '无零段(%.0f%%)' % (zero * 100)
    return True, ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', default=r'G:/_setup/ch123_final')
    ap.add_argument('--out', default=r'G:/_setup/ch123_final_pause')
    ap.add_argument('--bank', default=BANK_DEFAULT)
    ap.add_argument('--tiers', default=TIERS_DEFAULT_PATH)
    ap.add_argument('--who', default=None,
                    help='强制声道：narr=旁白（马修母带档位）/ dialog=对白（夏尔档，封顶 0.76）。'
                         '不给则按 --texts 里的 speaker 字段自动判，缺失时按旁白处理（保守）')
    ap.add_argument('--no-text', action='store_true',
                    help='不用原文标点（退回 ASR 标点，实测只覆盖 84.3%%）')
    ap.add_argument('--texts', default='',
                    help='外部原文表 jsonl（每行含 id/text），覆盖内建 ch123_plan 表。'
                         '非 Wonder 编号体系（如 c1_xxxx）必须给，否则 LLM/intent 分支不执行')
    ap.add_argument('--intent', default=r'G:/_setup/pause_intent.json',
                    help='语言直觉判定表（must/opt/no），决定该不该停')
    ap.add_argument('--llm', default=LLM_DEFAULT,
                    help='LLM 逐处停顿判定（优先级最高）')
    ap.add_argument('--no-llm', action='store_true',
                    help='不用 LLM 判定，退回档位/统计')
    ap.add_argument('--no-intent', action='store_true',
                    help='不用 intent，一律按分档补停')
    ap.add_argument('--fade', type=float, default=0.010,
                    help='拼接/插入处的淡入淡出时长（秒）。10ms 会在接缝处造成能量阶跃，'
                         '被第 4 闸判 intra_drift（实测 7 条 PASS→MANUAL）')
    ap.add_argument('--expr', default=r'G:/_setup/_punct_expr.json',
                    help='标点表达度实测表（mt_punct_expr.py 产物）')
    ap.add_argument('--no-expr', action='store_true')
    ap.add_argument('--tone', default=TONE_DEFAULT)
    ap.add_argument('--strength', type=float, default=1.0)
    ap.add_argument('--vary', type=float, default=VARY_SIGMA,
                    help='逐处抖动 σ（0=每档固定值，测试旧行为用）')
    ap.add_argument('--shape-alpha', type=float, default=SHAPE_ALPHA,
                    help='保留模型自身相对长短的强度（0=全抖，1=完全照搬模型比例）')
    ap.add_argument('--trim-slop', type=float, default=TRIM_SLOP,
                    help='比目标长出多少才往回删')
    ap.add_argument('--trim-cap', type=float, default=TRIM_CAP,
                    help='单处最多删多少秒')
    ap.add_argument('--level-db', type=float, default=None,
                    help='强制统一底噪电平（默认 %.0f dBFS）' % SCENE_LEVEL_DB)
    ap.add_argument('--auto', action='store_true',
                    help='逐条跟随本文件底噪（仅当存在稳态噪声平台时生效，默认关）')
    ap.add_argument('--baseline', type=float, default=None,
                    help='统一电平的别名，默认 %.0f' % SCENE_LEVEL_DB)
    ap.add_argument('--clamp', type=float, default=LEVEL_CLAMP_DB)
    ap.add_argument('--no-fill-existing', action='store_true')
    # ★ 2026-10-30 用户明确要求：停顿处不要铺合成底噪。
    #   实测 synth_bed 的粉噪型纹理在 −56dBFS 上仍是可听的「嘶——」，
    #   尤其插入的长停顿处（1.1~1.7s）非常明显，比真空静音更假。
    #   默认关闭；确需铺底噪时用 --bed 显式开启（并优先 --bed-self 从本音频静音段取真实底噪）。
    ap.add_argument('--bed', action='store_true',
                    help='在停顿处铺合成底噪（默认关闭）')
    ap.add_argument('--bed-self', action='store_true',
                    help='从本音频自身的静音段提取底噪（比合成纹理自然，需配合 --bed）')
    ap.add_argument('--only', default='')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--report', default='')
    a = ap.parse_args()

    proto = bank_to_proto(a.bank)
    tiers = dict(TIERS_DEFAULT)
    if a.tiers and os.path.exists(a.tiers):
        raw = json.load(open(a.tiers, encoding='utf-8'))
        tiers.update({k: float(v) for k, v in raw.items()
                      if not k.startswith('_') and isinstance(v, (int, float))})

    # ★ 分声道档位（2026-11-11）。tiers 与 pause_tiers.json 里那套 1.16/1.53 是
    #   马修**旁白**母带的实测量；给情绪化对白用会长出 2.70 倍（夏尔真人中位 0.43、
    #   本人最大 0.76）。所以对白必须有自己的一套，并且硬封顶 0.76。
    T_NARR = dict(tiers)
    T_DLG = dict(TIERS_DIALOG)
    # ASR 回退路径的对白版：直接按夏尔档位给，不经过旁白 bank
    PROTO_DLG = {',': T_DLG['mid'], '.': T_DLG['dot_inner'], ';': T_DLG['short'],
                 ':': T_DLG['short'], '!': T_DLG['long'], '?': T_DLG['?'],
                 '\u2014': T_DLG['short'], '\u2013': T_DLG['short']}

    def tiers_of(k):
        """返回 (档位表, 是否对白)。旁白/未知 → 旁白档；其余角色 → 对白档。"""
        who = a.who
        if who is None:
            who = SPEAKERS.get(k, '')
        w = str(who or '').lower()
        is_narr = (w in ('', 'narr', 'narrator', 'narr_sliced')) or w.startswith('narr')
        return (T_NARR, False) if is_narr else (T_DLG, True)
    TEXTS = {}
    SPEAKERS = {}
    if a.texts and os.path.exists(a.texts):
        # 外部原文表（jsonl，每行至少含 id/text）：给非 Wonder 编号体系的书用。
        # 不加这个参数时，下面的内建表只认 L%03d / I%02d，本书的 c1_xxxx 不命中
        # ⇒ k in TEXTS 为假 ⇒ LLM 逐处判定与 pause_intent 分支都不执行（标注等于没喂）。
        _n = 0
        for _ln in open(a.texts, encoding='utf-8'):
            _ln = _ln.strip()
            if not _ln:
                continue
            _r = json.loads(_ln)
            if _r.get('id') and _r.get('text'):
                TEXTS[str(_r['id'])] = _r['text']
                SPEAKERS[str(_r['id'])] = str(_r.get('speaker') or '')
                _n += 1
        print('原文表（--texts）: %d 条 <- %s'
              % (_n, os.path.basename(a.texts)), flush=True)
    elif not a.no_text:
        try:
            from ch123_plan import INNER, PLAN
            TEXTS = {'L%03d' % i: t for i, _, _, t in PLAN}
            TEXTS.update({'I%02d' % i: t for i, (_, _, _, t) in enumerate(INNER)})
        except Exception as e:
            print('[warn] 原文表不可用（%s），退回 ASR 标点' % e, flush=True)

    # 语言直觉判定（pause_intent.json）：决定「该不该停」，不是「停没停」
    INTENT = {}
    if not a.no_intent and a.intent and os.path.exists(a.intent):
        INTENT = {k: v for k, v in json.load(open(a.intent, encoding='utf-8')).items()
                  if not k.startswith('_')}

    # LLM 逐处判定（pause_llm.json）：按角色情绪与语言自然度给绝对值
    LLM_ALL = {}
    if not a.no_llm and a.llm and os.path.exists(a.llm):
        try:
            LLM_ALL = json.load(open(a.llm, encoding='utf-8'))
            LLM_ALL.pop('_meta', None)
            print('LLM 判定: %s（%d 条台词 / %d 处）'
                  % (os.path.basename(a.llm), len(LLM_ALL),
                     sum(len(v) for v in LLM_ALL.values())), flush=True)
        except Exception as e:
            print('[warn] LLM 判定读不了（%s），退回档位' % e, flush=True)

    # 标点表达度（mt_punct_expr.py 的产物）：决定「该不该塞静音」
    EXPR = {}
    if not a.no_expr and a.expr and os.path.exists(a.expr):
        raw = json.load(open(a.expr, encoding='utf-8'))
        for k, rows in raw.items():
            EXPR[k] = {r['i']: r for r in rows if r.get('status') != 'unaligned'}
    files = sorted(glob.glob(os.path.join(a.inp, '*.wav')))
    if a.only:
        keep = set(a.only.split(','))
        files = [f for f in files if os.path.basename(f)[:-4] in keep]
    if not files:
        raise SystemExit('没有输入文件: %s' % a.inp)
    os.makedirs(a.out, exist_ok=True)

    # 全库面板（仅在单条无法测底噪时用）
    panel = None
    if a.tone and os.path.exists(a.tone):
        t, tsr = sf.read(a.tone, dtype='float32')
        if t.ndim > 1:
            t = t.mean(1)
        t = _resample(t.astype(np.float64), tsr, 48000)
        db_t, n_t, h_t = frame_db(t, 48000)
        m_t = db_t > NOISE_FLOOR_DB
        if m_t.sum() >= MIN_QUIET_FRAMES:
            panel = noise_psd(t, 48000, db_t, n_t, h_t, m_t)

    # 先测一遍（每条的实际静音/衰减情况）
    info = {}
    for f in files:
        x, sr = sf.read(f, dtype='float32')
        if x.ndim > 1:
            x = x.mean(1)
        info[f] = (x, sr, measure(np.ascontiguousarray(x, dtype=np.float32), sr))

    cred_n = sum(1 for v in info.values() if credible(v[2])[0])
    print('底噪策略: %s | 可以逐条跟随的条目 %d/%d'
          % ('固定 %.1f dB' % a.level_db if a.level_db is not None
             else ('逐条跟随（可信者）' if a.auto else '统一 %.1f dB' % SCENE_LEVEL_DB),
             cred_n, len(info)), flush=True)
    print('标点目标: ' + '  '.join('%s=%.3fs' % (k, v) for k, v in sorted(proto.items())),
          flush=True)
    print('', flush=True)

    rows = []
    for f in files:
        k = os.path.basename(f)[:-4]
        x, sr, st = info[f]
        x = np.ascontiguousarray(x, dtype=np.float32)
        nq, lv0, med = st['nq'], st['level'], st['med']

        # ---- 定电平
        # 这批文件里 12%~41% 的帧是数字零，其余「安静帧」是语音衰减尾巴（IQR 到 17dB），
        # 不存在稳态底噪 ⇒ 默认铺统一场景电平，不用逐条估计值（否则跟着衰减跑）。
        ok, why = credible(st)
        if a.level_db is not None:
            level, src = float(a.level_db), 'fixed'
        elif a.auto and ok:
            level, src = lv0, 'self'
        else:
            level, src = a.baseline if a.baseline is not None else SCENE_LEVEL_DB, (
                'scene' if a.auto else 'scene')

        # ---- 定纹理：同一场景只该有一个房间
        psd, tsrc = panel, ('panel' if panel is not None else 'pink')
        if a.auto and ok:
            p2 = noise_psd(x, sr, st['db'], st['n'], st['h'], st['mask'])
            if p2 is not None:
                psd, tsrc = p2, 'self'

        rng = np.random.default_rng(abs(hash(k)) % (2 ** 32))
        if a.bed_self:
            # ★ 2026-11-11：--bed-self 之前是**死参数**（只在 375 行定义，全文无引用），
            #   于是「要铺底噪用 --bed --bed-self」这句写了等于没写，默认仍插数字零。
            #   现在真正生效：从本条音频自己的静音段取纹理（实测我们的 wav 底噪
            #   ≈ −60dBFS、无一条是数字零），再抬到 SCENE_LEVEL_DB=−58 统一电平。
            #   这样既满足需求 25a（停顿处不许数字零），也不违反 2026-10-30 的
            #   「不铺合成粉噪」——纹理是它自己的房间声，不是 synth_bed 造的。
            b2, b2_db = bed_from_self(x, sr, target_db=SCENE_LEVEL_DB)
            # ★ --clamp：这条原本是死参数（`LEVEL_CLAMP_DB=6.0` 只定义不读）。
            #   语义 = 「取到的源底噪与目标电平偏差超过 clamp 就不采信它的纹理」。
            #   为什么必须判：源底噪 −80dB 时抬到 −58 是把几乎听不见的量化噪声放大 22dB，
            #   会变成明显的「嘶」；而那正是 2026-10-30 否掉合成粉噪的同一个听感问题。
            #   超限时退回批纹理（panel，若有）或粉噪兜底，并在报告里记 fallback。
            if b2 is not None and b2_db is not None and abs(b2_db - SCENE_LEVEL_DB) > a.clamp:
                print('   [clamp] %s 自底噪 %.1fdB 与目标 %.1f 差超 %.1f，改走批纹理'
                      % (k, b2_db, SCENE_LEVEL_DB, a.clamp), flush=True)
                b2 = None
                if panel is not None:
                    bed, tsrc, level = synth_bed(len(x) + int(12 * sr), sr,
                                                 panel, SCENE_LEVEL_DB, rng), 'panel', SCENE_LEVEL_DB
                else:
                    bed, tsrc, level = synth_bed(len(x) + int(12 * sr), sr,
                                                 flat_psd(sr), SCENE_LEVEL_DB, rng), 'pink', SCENE_LEVEL_DB
                src = 'fallback'
            elif b2 is not None:
                bed, tsrc, level = b2, 'self', SCENE_LEVEL_DB
            else:
                # ★ 2026-11-16 02:5x：本条测不出真实底噪（句子太短凑不够 0.30s 安静帧、
                #   或整条近乎数字零）时，原来退回「不铺」= 插数字零，直接违反 REQUIREMENTS 25a
                #   （停顿处不许数字零）。实测旁白 716 条里约 16% 会走到这里。
                #   改铺 room_tone_panel.wav —— 从本库母带 wonder_train.wav 的 2700 个安静帧
                #   提取的真实房间声，不是 synth_bed 造的粉噪（2026-10-30 否掉的是后者）。
                psd2 = panel if panel is not None else flat_psd(sr)
                bed = synth_bed(len(x) + int(12 * sr), sr, psd2,
                                SCENE_LEVEL_DB, rng)
                tsrc = 'panel' if panel is not None else 'pink'
                level = SCENE_LEVEL_DB
                src = 'fallback'
        elif not a.bed:
            # 显式不用底噪：bed 全零 ⇒ apply_edits/add_bed_all 等于纯零填充。
            # 这与需求 25a 冲突，所以报告里必须留痕（level=-120 一眼可查）。
            bed = np.zeros(0, dtype=np.float32)
            tsrc, level = 'none', -120.0
        else:
            bed = synth_bed(len(x) + int(12 * sr), sr, psd, level, rng)

        rw = word_times(f)
        LL = LLM_ALL.get(k, {})
        tl, is_dlg = tiers_of(k)
        cap = DIALOG_CAP if is_dlg else 9.0
        plan, psrc, trims = [], 'none', []
        swallow, skipped_expr = [], []      # 19f：none=真吞了 / weak=已用延长代替
        if len(rw) >= 2:
            if k in TEXTS:
                raw_plan, _ = plan_from_text(rw, TEXTS[k], tl)
                INT = INTENT.get(k, {})
                # 同档位参照：本句里该档已有 gap 的中位，用来保留模型自己的相对长短。
                # 实测 L063 模型给 0.64 / 0.38（第一处更长），如果只按档位补，
                # 两处都会被抬到同一个值；如果只抖动，又会把模型的先后顺序打乱。
                _by = {}
                for _t, _a, _w, _tg, _cur, _tr, _wh, _i in raw_plan:
                    _by.setdefault(_tr, []).append(_cur)
                _med = {t: float(np.median(v)) for t, v in _by.items() if v}
                for t, _add, w, tgt, cur, tier, why, i in raw_plan:
                    # ★ 第零优先：标点表达度（REQUIREMENTS 19f）。必须先于 LLM 判定，
                    #   因为它描述的是「这个标点在模型输出里到底念出来没有」，
                    #   而 LLM 判定只描述「这里按语义该停多久」——后者不知道前者。
                    #   weak：模型用延长/音高变化代替了停顿，这是对的表达，
                    #         **再塞静音会变成断两次**（实测 10/70 处）。
                    #   none：三项痕迹全无 = 真吞了。塞静音只会掩盖吞字，
                    #         补不回 pitch reset 与边界前延长 ⇒ 进重生成清单。
                    ex = (EXPR.get(k) or {}).get(i)
                    # ★ 但 weak 的语义只在**对白**成立。19f 的语境是"夏尔这类情绪化短句"
                    #   （19e 说的 70 处标点全来自 60 条对白），判据 GAP_STRONG=0.30
                    #   也是按对白目标 0.43 定的。旁白 bound 要 1.135s，
                    #   模型给 0.25s 的延长根本不是"用了正确的表达方式"，就是短了 0.9s
                    #   ⇒ 旁白必须照档位补插，不能因为 weak 就跳过。
                    #   none（三项痕迹全无 = 真吞了）两条轨道一样处理：不塞静音掩盖，进重生成清单。
                    if ex is not None and ex.get('status') == 'none':
                        swallow.append(dict(k=k, i=i, word=ex.get('word'),
                                            punct=ex.get('punct'),
                                            gap=ex.get('gap'), cur=round(cur, 2)))
                        skipped_expr.append((t, cur, 'none'))
                        continue
                    if ex is not None and ex.get('status') == 'weak' and is_dlg:
                        skipped_expr.append((t, cur, 'weak'))
                        continue
                    # ★ 第一优先：LLM 逐处判定（按夏尔这个角色的情绪与语言自然度）
                    #   它不是统计值，是「这句话在这一刻该不该顿、顿多久」的语义决定。
                    ll = LL.get(str(i))
                    if ll is not None:
                        tgt = min(float(ll.get('d', 0.0)), cap)   # 对白封顶 0.76
                        tier = 'llm:' + str(ll.get('kind', ''))
                        why = str(ll.get('why', ''))
                        if tgt <= 0:
                            if cur > NO_TRIM_MIN:
                                trims.append((t, 'del', cur - NO_KEEP, w, 'LLM 判无停顿'))
                            continue
                        d = tgt - cur
                        if d < -LLM_TRIM_SLOP:
                            cut = min(-d, max(0.0, cur - NO_KEEP), a.trim_cap)
                            if cut >= 0.05:
                                trims.append((t, 'del', cut, w,
                                              'LLM %.2f 过长' % tgt))
                            continue
                        if d < 0.03:
                            continue
                        plan.append((t, d, w, tgt, cur, tier, why))
                        continue

                    it = INT.get(str(i), '') if INT else ''
                    if it == 'no':
                        # 语言直觉上不该停：已经停了就压回去（删静音），不再加
                        if cur > NO_TRIM_MIN:
                            trims.append((t, 'del', cur - NO_KEEP, w, 'intent=no'))
                        continue
                    if it == 'opt' and cur >= OPT_ENOUGH:
                        continue          # 已有一点间隙，够了，不塞
                    # ★ 形状保持：按档位内中位缩放，而不是每处补到同一个目标。
                    #   实测模型自身的相对跨度 0.27，真人 0.34 —— 已经很接近，
                    #   额外抖动反而把 L063 的先后顺序打乱（0.64/0.38 → 0.70/0.76）。
                    #   模型根本没给间隙（<0.10s）时比例无意义，按标准档位补。
                    m = _med.get(tier, 0.0)
                    if m > 1e-6 and a.shape_alpha > 0 and cur >= 0.10:
                        ratio = min(max(cur / m, 0.55), 1.80) ** a.shape_alpha
                    else:
                        ratio = 1.0
                    tgt = min(tgt * ratio * jitter(k, i, w, a.vary), cap)
                    d = tgt * a.strength - cur
                    if d < -a.trim_slop:
                        # 模型自己停太长：只删 gap 中段（两端各留 25ms），不碰语音
                        cut = min(-d, max(0.0, cur - NO_KEEP), a.trim_cap)
                        if cut >= 0.05:
                            trims.append((t, 'del', cut, w, '档位 %.2f 过长' % tgt))
                        continue
                    if d < 0.03:
                        continue
                    plan.append((t, d, w, tgt, cur, tier,
                                 why + ('' if it else ' [未判intent]')))
                psrc = 'llm' if LL else ('text+intent' if INT else 'text')
            else:
                plan = []
                _pr = PROTO_DLG if is_dlg else proto
                for n, (t, add, w, tgt, cur) in enumerate(plan_from_proto(rw, _pr, a.strength)):
                    tgt = min(tgt * jitter(k, n, w, a.vary), cap)
                    d = tgt * a.strength - cur
                    if d < -a.trim_slop:
                        cut = min(-d, max(0.0, cur - NO_KEEP), a.trim_cap)
                        if cut >= 0.05:
                            trims.append((t, 'del', cut, w, 'asr 档位过长'))
                        continue
                    if d < 0.03:
                        continue
                    plan.append((t, d, w, tgt, cur, 'asr', ''))
                psrc = 'asr'
        got = [(i, tail_punct(w[2])) for i, w in enumerate(rw)]
        got = [p for i, p in got if p and i < len(rw) - 1]

        d0 = len(x) / sr
        tl = [p[5] for p in plan]
        # 逐处留痕：改前 gap / 目标 / 改后 gap，用来核对「不是同一个值」
        bounds = [dict(t=round(t, 3), w=w, tier=tier, op='ins',
                       cur=round(cur, 3), tgt=round(tgt, 3),
                       after=round(cur + add, 3))
                  for t, add, w, tgt, cur, tier, _why in plan]
        bounds += [dict(t=round(t, 3), w=w, tier='del', op='del',
                        cur=None, tgt=None, after=None, cut=round(d, 3))
                   for t, _, d, w, _r in trims]
        bounds.sort(key=lambda b: b['t'])
        if a.dry:
            add = sum(p[1] for p in plan)
            cut = sum(p[2] for p in trims)
            print('%-5s %5.2fs 底噪%6.1f(%s) 纹理%-6s %s 插%2d处 +%.2fs 压%2d处 -%.2fs → %.2fs'
                  % (k, d0, level, src, tsrc, psrc, len(plan), add, len(trims), cut,
                     d0 + add - cut),
                  flush=True)
            rows.append(dict(k=k, dur=d0, level=level, level_src=src, psd=tsrc,
                             punct_got=len(got), plan=len(plan), add=add,
                             trims=[dict(t=t, d=d, w=w, why=_r) for t, _, d, w, _r in trims],
                             bounds=bounds, psrc=psrc, tiers=tl, per_punct=got))
            continue

        y = x
        filled = 0
        skipped = []
        if not a.no_fill_existing:
            y, filled = add_bed_all(y, sr, bed)
        if plan or trims:
            edits = [(t, 'ins', add, w) for t, add, w, *_ in plan] + list(trims)
            y, skipped = apply_edits(y, sr, edits, bed, fade=a.fade)
            if skipped:
                print('   [skip] %s 有 %d 处删除没找到安静窗口，已跳过: %s'
                      % (k, len(skipped), ' '.join('%.2f@%.2fs' % (a, t) for t, a in skipped)),
                      flush=True)
        pk = float(np.abs(y).max())
        pk_trim = 0.0
        if pk > PEAK_CEIL:
            # 账本：crest 23dB 时 −24dBFS voiced RMS 的峰值天然落 −1dBFS，
            # 正常条不该触发。触发了说明这条波峰因数异常（多半是插停顿后瞬态叠高），
            # 记进报告供复核，而不是悄悄放行到 0.999。
            pk_trim = round(20 * np.log10(PEAK_CEIL / pk), 2)
            y = y * (PEAK_CEIL / pk)
            print('   [peak] %s 峰值 %.3f 超 −1dBFS，整体回退 %+.1fdB（voiced RMS 会低于 −24）'
                  % (k, pk, pk_trim), flush=True)
        sf.write(os.path.join(a.out, k + '.wav'), y, sr, subtype='PCM_16')

        # 实测：插槽电平 vs 文件原底噪
        db2, _, _ = frame_db(y, sr)
        rows.append(dict(k=k, dur=d0, out_dur=len(y) / sr, level=level, level_src=src,
                         peak=round(float(np.abs(y).max()), 3), pk_trim=pk_trim,
                         psd=tsrc, nq=nq, med=med, self_level=lv0, filled=filled,
                         punct_got=len(got), plan=len(plan), psrc=psrc, tiers=tl,
                         trims=[dict(t=t, d=d, w=w, why=_r) for t, _, d, w, _r in trims],
                         skipped=[dict(t=t, d=d) for t, d in skipped],
                         expr_swallow=swallow,
                         expr_skip=[dict(t=round(t, 2), gap=round(g, 2), st=s)
                                    for t, g, s in skipped_expr],
                         bounds=bounds,
                         add=sum(p[1] for p in plan), per_punct=got,
                         out_p05=float(np.percentile(db2, 5))))
        print('%-5s %5.2fs→%5.2fs  底噪%6.1f(%s) 纹理%-6s 原零帧%5d 插%2d处 +%.2fs 压%2d处 -%.2fs'
              % (k, d0, len(y) / sr, level, src, tsrc, filled, len(plan),
                 sum(p[1] for p in plan), len(trims), sum(p[2] for p in trims)), flush=True)

    out = a.report or os.path.join(a.out, '_pause_report.json')
    # ★ 2026-11-15 12:4x：`--only` 只跑几条时，原来会**整体覆盖**报告 ——
    #   实测把 239 行的全量报告写成了 2 行，后面所有「插入了几处、在哪」的追溯全丢。
    #   改成按 k 合并：本次跑过的条目覆盖旧行，没跑的原样保留。
    merged = {}
    if os.path.exists(out):
        try:
            for r in json.load(open(out, encoding="utf-8")):
                merged[r.get("k")] = r
        except Exception:  # noqa: BLE001
            merged = {}
    for r in rows:
        merged[r.get("k")] = r
    rows_out = [merged[k] for k in merged]
    json.dump(rows_out, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('\n===== 汇总 =====')
    n = len(rows)
    if n:
        print('文件 %d 条  插入 %d 处  总补时 %.2fs  平均每句 +%.2fs'
              % (n, sum(r['plan'] for r in rows), sum(r['add'] for r in rows),
                 sum(r['add'] for r in rows) / n))
        nt = sum(len(r.get('trims') or []) for r in rows)
        ct = sum(t['d'] for r in rows for t in (r.get('trims') or []))
        if nt:
            print('压缩多余停顿 %d 处  总减时 %.2fs' % (nt, ct))
            for r in rows:
                for t in (r.get('trims') or []):
                    print('  %-5s %-12s 压 %.2fs（%s）'
                          % (r['k'], t['w'], t['d'], t.get('why', '')))
        d0 = sum(r['dur'] for r in rows)
        d1 = sum(r.get('out_dur', r['dur'] + r['add']) for r in rows)
        print('总时长 %.1fs → %.1fs（+%.1f%%）' % (d0, d1, 100 * (d1 - d0) / d0))
        by = {}
        for r in rows:
            for p in r['per_punct']:
                by[p] = by.get(p, 0) + 1
        print('标点命中: ' + '  '.join('%s=%d' % (k2, v2) for k2, v2 in sorted(by.items())))
        lv = [r['level'] for r in rows]
        print('底噪电平 %.1f ~ %.1f dB（跨度 %.1f）' % (min(lv), max(lv), max(lv) - min(lv)))
        fb = [r['k'] for r in rows if 'fallback' in r['level_src']]
        print('走批回退的条目 %d 条: %s' % (len(fb), ' '.join(fb) if fb else '-'))

        # 19f：两种「没停」分开报，不许一视同仁
        nw = sum(1 for r in rows for e in (r.get('expr_skip') or []) if e['st'] == 'weak')
        sw = [(r['k'], e['word'], e['punct'], e['gap'])
              for r in rows for e in (r.get('expr_swallow') or [])]
        if nw or sw:
            print('标点表达度：weak %d 处（模型用延长代替停顿，未塞静音）' % nw)
            if sw:
                print('  ★ 真吞字 %d 处，须进重生成清单（插静音补不回 pitch reset）:' % len(sw))
                for k2, w2, p2, g2 in sw:
                    print('    %-5s 第 %-10s 处 gap %.3fs  %s' % (k2, repr(w2), g2, p2))
    print('报告: %s' % out)


if __name__ == '__main__':
    main()
