# -*- coding: utf-8 -*-
"""gate_intra.py —— 第 4 道闸：句内音色一致性（防「前面没问题、后面炸了」）。

## 为什么不用原来的做法
原 `ch123_segcheck.py`：CAM++(英文) + 按 −45dB 静音切段 + **0.55 绝对阈值**。
两个问题都被实测证伪，不是猜：
  1. **模型在这套语料上失效**：CAM++ 对 239 条做说话人验证 EER = **44.6%**（接近 50% 随机）。
     换 r34（Wespeaker ResNet34）后 EER 23.2%、AUC 0.59→0.85。
  2. **「段间不像」推不出「换人」**：`_mutbench` 里同角色两条不同句拼接，段间余弦
     中位 0.724，反而比换人拼接（0.700）还低 —— 人内方差压过了跨人差异。
     固定阈值 0.55 在 955 条上判出 44% SEVERE，那不是 44% 都炸了，是尺子不成立。

## 现在的判据（`_mutbench` 189 条有 ground truth 的基准上校准）
  模型 r34；窗 1.5s / 步 0.25s；结构性分离度
      sep(t) = (段内平均余弦_L + 段内平均余弦_R)/2 − 跨段余弦
  「换人」要求**段内自己像自己**且**段间不像**，两者同时成立才给高分；
  情绪起伏 / 短窗噪声会让段内也不像，分数被压回 0 —— 专门用于压误报。
  阈值按 k 分档，取基准 NEG_real（真实整句、无拼接）p95，FPR≈5%：
      k=7 → 0.605   k=5 → 0.701   k=3 → 0.791
  实测（POS_hard 60 条换人样本）：k=7 检出 77%、定位误差 MAE 0.21s、≤0.75s 命中 100%。

## 覆盖上限（如实标注，不许当通过）
sep 需要切点两侧各有 ≥2 个有效窗，最短 k=3 ⇒ 音频 ≥3.8s。
239 条对白里只有 **87 条（36%）** 可测，其余 152 条是 1-3 词的短句，
句内不存在可切分的结构 ⇒ 一律标 `intra_unmeasurable`，不算过、不算坏，人耳抽检。
"""
import json, os
import numpy as np

import sys
sys.path.insert(0, "G:/_setup")
from _mut_all import M, to16, fbank, score_sep, nrm

# ── 路 A：声学阶跃（复用项目里已有的 mt_seg_drift，别重造）
#    它的判据是 F0/谱质心/谱倾斜/HNR/ΔRMS 多参数阶跃，阈值来自 180 条
#    已交付旁白（已知干净）的零分布，MIN_DUR 只要 1.2s ⇒ 覆盖率远高于声纹路。
_DRIFT = {}
DRIFT_CACHE = "G:/_setup/_drift_cache.json"
# ★ 2026-11-14 15:2x：闸 4 只服务对白，用对白版判据（不看 ΔF0，只认声道形状）。
#   缓存条目必须带 profile 字段且与本值一致，否则丢弃重算 —— 旧缓存全是
#   旁白判据算的（把语调当音色），直接复用会得出「长句 WARN 82%」的假结论。
DRIFT_PROFILE = "dlg"


def _drift():
    """懒加载 mt_seg_drift 及既有结果缓存

    ★ 2026-11-14 14:4x 修：缓存必须校验音频没被换过。
    旧实现只按文件名匹配 ⇒ r11~r14 回填重写了 94 条音频后，闸 4 仍然拿 11-12 的
    旧判决当结论（实测重算 94 条里 48 条判决变了，FAIL 从 7 变 10 且只有 3 条重合）。
    缓存条目里本来就存了 `dur`，用它和当前音频时长对一下即可：差 >0.05s 就丢弃、重算。
    """
    global _DRIFT
    if _DRIFT is None:
        return None
    if isinstance(_DRIFT, dict) and _DRIFT:
        return _DRIFT
    try:
        import soundfile as _sf
    except Exception:
        _sf = None
    try:
        from mt_seg_drift import JUDGE_VER
    except Exception:
        JUDGE_VER = None
    try:
        if os.path.exists(DRIFT_CACHE):
            stale = 0
            for x in json.load(open(DRIFT_CACHE, encoding="utf-8")):
                if x.get("profile") != DRIFT_PROFILE:
                    stale += 1
                    continue
                # ★ 判据版本变了就得重算：否则改了 judge 还在看旧判决
                if x.get("ver") != JUDGE_VER:
                    stale += 1
                    continue
                sid = os.path.basename(x["file"])[:-4]
                cd = x.get("dur")
                w = os.path.join(os.path.dirname(x["file"]), sid + ".wav")
                if cd is not None and _sf is not None:
                    try:
                        if abs(float(cd) - _sf.info(w).duration) > 0.05:
                            stale += 1
                            continue
                    except Exception:
                        stale += 1
                        continue
                _DRIFT[sid] = x
            if stale:
                print("[gate_intra] 漂移缓存失效 %d 条（音频已变），改为实时重算" % stale,
                      flush=True)
    except Exception:
        pass
    return _DRIFT

WIN, HOP, MIN_WIN = 1.5, 0.25, 0.60
K_THR = {7: 0.605, 5: 0.701, 3: 0.791}
CACHE = "G:/_setup/_mutcache_real"
REFS = "G:/_setup/refs_cast"
_ROLE_REF = {}
_M = {}


def _model():
    if "m" not in _M:
        _M["m"] = M("r34")
    return _M["m"]


def _role_refs():
    """refs_cast 各角色的参考向量（只对 SUSPECT 条目算归属翻转时用）"""
    if not _ROLE_REF:
        m = _model()
        for f in sorted(os.listdir(REFS)):
            if f.endswith(".wav"):
                e = m.emb_f(fbank(to16(os.path.join(REFS, f)), m.cmn))
                _ROLE_REF.setdefault(f.split("_")[0], []).append(e)
        for k in _ROLE_REF:
            _ROLE_REF[k] = np.stack(_ROLE_REF[k])
    return _ROLE_REF


def windows(wav, cache=None):
    """滑窗 embedding，带磁盘缓存（key = 文件名）"""
    sid = os.path.splitext(os.path.basename(wav))[0]
    cp = os.path.join(cache or CACHE, sid + ".npz")
    if cache is not False and os.path.exists(cp):
        z = np.load(cp)
        return z["centers"], z["embs"]
    m = _model()
    a = to16(wav)
    feats = fbank(a, m.cmn)
    T, dur = feats.shape[0], len(a) / 16000
    cs, es, t = [], [], 0.0
    while t + WIN <= dur + 1e-6:
        s, e = int(t * 100), min(int((t + WIN) * 100), T)
        if e - s < MIN_WIN * 100:
            break
        cs.append(t + WIN / 2)
        es.append(m.emb_f(feats[s:e]))
        t += HOP
    cs = np.array(cs)
    E = np.stack(es) if es else np.zeros((0, 256), dtype=np.float32)
    if cache is not False:
        os.makedirs(cache or CACHE, exist_ok=True)
        np.savez(cp, centers=cs, embs=E)
    return cs, E


def pick_k(n):
    for k in (7, 5, 3):
        if n >= 2 * k + 4:
            return k
    return None


def role_flip(cs, E, pos):
    """切点两侧 top-1 角色是否翻转（第二证据）。翻转且 margin 都 >0 → True"""
    refs = _role_refs()
    L = E[(cs >= pos - 2.0) & (cs <= pos - 0.2)]
    R = E[(cs >= pos + 0.2) & (cs <= pos + 2.0)]
    if len(L) < 2 or len(R) < 2:
        return None, None, None

    def top1(e):
        sc = sorted(((w, float(np.max(V @ e))) for w, V in refs.items()), key=lambda x: -x[1])
        return sc[0][0], sc[0][1], sc[1][1]

    a, sa, sa2 = top1(nrm(L.mean(0)))
    b, sb, sb2 = top1(nrm(R.mean(0)))
    return (a != b and sa > sa2 + 0.05 and sb > sb2 + 0.05), a, b


def _drift_check(wav):
    """路 A：声学阶跃。-> (code, why, pos, state)

    state 三值（2026-11-14 02:4x 修：原来只有「命中 / None」两种，把「测过且
    没有阶跃」和「根本测不了」混成一个 None，导致 1.2~3.8s 的句子明明跑出了
    WARN，却被记成「两路都测不了」，报告里覆盖被低估到 37%）：
      hit           —— 判出阶跃（FAIL）
      ok            —— 测过，PASS 或仅孤立事件降级的 WARN（mt_seg_drift 的设计：
                       180 条正常旁白里 FAIL 全部只有 1 个孤立事件，故 WARN≈正常）
      unmeasurable  —— 时长 <1.2s / 无声 / 执行异常
    """
    sid = os.path.splitext(os.path.basename(wav))[0]
    d = _drift()
    r = d.get(sid) if isinstance(d, dict) else None
    # ★ 2026-11-14 22:1x 修（关键，两个层次）：
    #   ① 缓存按文件名命中，候选与现役同名（`_regen_r15_out/c1_0153.wav` vs 交付路径），
    #      候选跑闸会拿到**现役的** drift 结论 —— 位置/判据一模一样，纯假证据。
    #   ② 光靠 dur 断言不够：`c2_0372` 候选时长恰好等于现役（都是 8.64s），
    #      断言通过，照样命中缓存，而候选实际上已经修好了。
    #   ⇒ 只有**交付路径本身**才允许用缓存；其他任何路径一律实时重算。
    if r is not None:
        _deliv = os.path.abspath(os.path.join("G:/_setup/_audio_ch123/out", sid + ".wav"))
        if os.path.abspath(wav).lower() != _deliv.lower():
            r = None
        else:
            cd = r.get("dur")
            try:
                import soundfile as _sf
                if cd is not None and abs(float(cd) - _sf.info(wav).duration) > 0.05:
                    r = None
            except Exception:
                r = None
    if r is None:
        try:
            import mt_seg_drift as D
            r = D.one(wav, profile=DRIFT_PROFILE)
        except Exception as e:
            return None, "漂移检测不可用：%s" % e, None, "unmeasurable"
    v = r.get("verdict")
    if v == "FAIL":
        ev = r.get("events") or []
        hard = [e for e in ev if e.get("level") == "FAIL"]
        why = "；".join("%s@%.2fs %s" % (e["level"], e["t"], "/".join(e["why"])) for e in hard[:2])
        return "intra_drift", "声学阶跃：" + why, (hard[0]["t"] if hard else None), "hit"
    if v in ("INSUFFICIENT", "NO_SPEECH"):
        return None, "漂移判据不成立（%s）" % v, None, "unmeasurable"
    return None, "无阶跃（%s）" % v, None, "ok"


def check(wav, cache=None):
    """-> (verdict, note_dict)；verdict ∈ PASS / MANUAL / NA

    两路并联，各管一个维度（实测 239 条上交集只有 1 条，说明确实互补）：
      A 声学阶跃（drift）：F0/谱质心/HNR/能量 有没有阶跃 —— 回答「怎么变的」
      B 声纹换人（sep）  ：切点两侧是不是两个人       —— 回答「变成了谁」
    """
    dcode, dwhy, dpos, dstate = _drift_check(wav)
    cs, E = windows(wav, cache=cache)
    k = pick_k(len(E))
    s, p, flip, a, b = None, None, None, None, None
    if k is not None:
        s, p = score_sep(cs, E, k, 0.25)
        if s is not None and s >= K_THR[k]:
            flip, a, b = role_flip(cs, E, p)

    sep_hit = bool(s is not None and k is not None and s >= K_THR[k])
    drift_hit = dcode == "intra_drift"

    info = {"drift": dwhy, "sep": (round(float(s), 3) if s is not None else None),
            "k": k, "flip": bool(flip), "role_lr": [a, b] if flip else None,
            "drift_state": dstate,
            "pos": (round(float(p), 2) if sep_hit else dpos)}

    if sep_hit and drift_hit:
        info["code"] = "intra_severe"
        info["score"] = round(float(s), 3)
        return "MANUAL", dict(info, why="句内音色突变（两类证据同时命中）：%s；sep=%.2f≥%.2f(k=%d)@%.2fs%s"
                              % (dwhy, s, K_THR[k], k, p,
                                 "，角色翻转 %s→%s" % (a, b) if flip else ""))
    if sep_hit:
        info["code"] = "intra_switch"
        info["score"] = round(float(s), 3)
        # 2026-11-14 15:3x：sep 单独命中保留判决（漏检比误报贵），但必须标出「flip 未确认」。
        # 依据：189 条基准上 sep 单独召回 77.5%，代价是 NEG_emo（同人跨情绪）误报 38.5%；
        # sep∧flip 的 AND 规则召回掉到 66.7% —— 那是「降检测能力」，与项目目标相反。
        # 所以不降级，改成「判决 + 复核优先级」：flip 没确认的排在人耳队列前面。
        hint = ("，top-1 角色翻转 %s→%s" % (a, b)) if flip else \
               "，角色翻转**未确认**（跨情绪误报率 38.5%，优先人耳）"
        return "MANUAL", dict(info, why="句内换人嫌疑：sep=%.2f≥%.2f(k=%d)@%.2fs%s；%s"
                              % (s, K_THR[k], k, p, hint, dwhy))
    if drift_hit:
        info["code"] = "intra_drift"
        info["score"] = round(float(s), 3) if s is not None else None
        return "MANUAL", dict(info, why=dwhy)
    if k is None and dstate == "unmeasurable":
        return "NA", dict(info, code="intra_unmeasurable",
                          why="两路都测不了（声纹需≥3.8s；漂移 %s）" % dwhy)
    if k is None:
        # 声纹路需要 ≥3.8s，短句测不了；漂移路已实测且无阶跃 ⇒ 判过，
        # 但必须标清「只有一路证据」，不许冒充双路通过。
        return "PASS", dict(info, code="intra_drift_ok",
                            why="句内一致（仅漂移通道：%s；声纹需≥3.8s 未测）" % dwhy)
    return "PASS", dict(info, code="intra_ok",
                        why="句内一致（sep=%s；%s）" % (
                            ("%.2f" % s) if s is not None else "不可算", dwhy))


if __name__ == "__main__":
    import sys
    for w in sys.argv[1:]:
        print(w, check(w))
