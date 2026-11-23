# -*- coding: utf-8 -*-
"""mt_hard_check.py —— 四项硬检测（用户 2026-10-29 指定）

检测项（顺序即优先级）：
  1) ASR 吞字   —— Parakeet 词表 vs 原文，**内容词缺失**就算吞字（不是看 rms）
  2) 声纹       —— CAM++ 嵌入；同单元跨 seed 余弦（同一个人？）+ 角色参考余弦（谁）
  3) 电平       —— 有声帧 RMS(dBFS)，跨 take 是否一致
  4) F0         —— 中位/区间/半音跨度/HNR（喊、塌、断裂）

口径来源：
  - 声纹 0.65 是用户红线，但**跨锚点不可比**（跨语言参考 cos≈0.38）。
    所以主判据用「同单元跨 seed 余弦」（同一句话、同一个人的两个 take），
    参考余弦只做旁证与尾部排查。
  - 电平：用户要求「振幅统一，不许一会大一会小」⇒ 判「同单元跨 take 差」优先于绝对带。
  - F0：>305Hz 是喊（既有结论）；塌/断裂看半音跨度。

用法：
  # 一次性喂全部目录，跨 seed 的对齐才有得算
  G:/Python310/python.exe mt_hard_check.py --dirs _mt_adv_ctl_2061,_mt_adv_ctl_2063,... \
      --out _hard_all.json
  # 只跑某几批做标定
  ... --limit 8
"""
import argparse
import glob
import json
import os
import re
import statistics as st
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab")

STATE = os.path.join(HERE, "_mt_adv_state.json")
REF = os.path.join(HERE, "castle_fr_ref", "1_charles_normal.wav")

STOP = set("""a an the and or but if of to in on at by for with from as is are was were be been
being do does did done have has had having will would shall should can could may might must
not no nor so than then that this these those there here it its he she they them his her their
we you i me my your our us who whom which what when where why how all any both each few more
most other some such only own same too very just also again ever never now""".split())

WORD_RE = re.compile(r"[A-Za-z']+")


def norm(w):
    w = w.lower().strip("'")
    w = w.replace("'", "")
    return w


def content_words(text):
    ws = [norm(x) for x in WORD_RE.findall(text)]
    return [w for w in ws if w and w not in STOP]


def load_state():
    d = json.load(open(STATE, encoding="utf-8"))
    u = d["units"] if isinstance(d, dict) else d
    out = {}
    for k, v in (u.items() if isinstance(u, dict) else [(x["id"], x) for x in u]):
        out[str(k)] = v
    return out


def read_wav(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    if sw != 2:
        raise ValueError("expect 16bit, got %d" % sw)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


# ---------------------------------------------------------------- 1) ASR 吞字
def asr_map(prom_asr_json):
    """_prom_asr_*.json → {uid: {text, words}}（键是 prom_stage 里的 wav 路径）"""
    if not os.path.exists(prom_asr_json):
        return {}
    d = json.load(open(prom_asr_json, encoding="utf-8"))
    out = {}
    for k, v in d.items():
        base = os.path.basename(k.replace("\\", "/"))
        m = re.search(r"__(.+)\.wav$", base)
        if m and isinstance(v, dict):
            out[m.group(1)] = v
    return out


def swallow_check(text, asr):
    """返回 (verdict, missing_content, missing_any, asr_text)

    MISSING  内容词全没读到（≥50% 内容词缺）
    DROP     内容词缺 1 个以上（吞字）
    SOFT     只缺功能词（弱读，可接受，记 SOFT）
    OK       内容词齐
    NOASR    没有 ASR 结果
    """
    if not asr or not asr.get("words"):
        return "NOASR", [], [], ""
    got = [norm(x["w"]) for x in asr["words"]]
    gotset = set(got)
    want_c = content_words(text)
    want_a = [norm(x) for x in WORD_RE.findall(text)]
    miss_c = [w for w in want_c if w not in gotset]
    miss_a = [w for w in want_a if w not in gotset and w not in STOP]
    txt = asr.get("text", "")
    if not want_c:
        return "OK", [], miss_a, txt
    if len(miss_c) >= max(2, int(0.5 * len(want_c) + 0.5)):
        return "MISSING", miss_c, miss_a, txt
    if miss_c:
        return "DROP", miss_c, miss_a, txt
    if miss_a:
        return "SOFT", miss_c, miss_a, txt
    return "OK", [], [], txt


# ---------------------------------------------------------------- 3) 电平
def level_check(a, sr):
    """有声帧 RMS（dBFS）+ 峰值。有声帧 = 帧 RMS > 峰值帧 -25dB。"""
    n = int(0.025 * sr)
    if len(a) < n * 2:
        r = float(np.sqrt(np.mean(a ** 2)) + 1e-12)
        db = 20 * np.log10(r + 1e-12)
        return dict(rms=round(db, 2), peak=round(20 * np.log10(np.max(np.abs(a)) + 1e-12), 2),
                    voiced_frac=1.0)
    fr = a[: len(a) // n * n].reshape(-1, n)
    rms = np.sqrt(np.mean(fr ** 2, axis=1) + 1e-20)
    db = 20 * np.log10(rms + 1e-20)
    top = np.percentile(db, 95)
    sel = db > (top - 25.0)
    v = float(np.mean(rms[sel] ** 2)) if sel.any() else float(np.mean(rms ** 2))
    return dict(rms=round(20 * float(np.log10(np.sqrt(v) + 1e-12)), 2),
                peak=round(float(20 * np.log10(np.max(np.abs(a)) + 1e-12)), 2),
                voiced_frac=round(float(sel.mean()), 3))


# ---------------------------------------------------------------- 4) F0
def f0_check(p, floor=60.0, ceil=400.0, vt=0.20):
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(p)
    pit = snd.to_pitch(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceil,
                       voicing_threshold=vt)
    vals = pit.selected_array["frequency"]
    v = vals[vals > 0]
    if len(v) < 5:
        return dict(f0=None, f0_p10=None, f0_p90=None, span_st=None, hnr=None,
                    voiced=round(len(v) * 0.01, 3))
    med = float(np.median(v))
    p10, p90 = float(np.percentile(v, 10)), float(np.percentile(v, 90))
    span = 12 * np.log2(max(p90, 1) / max(p10, 1))
    hnr = float(call(snd, "To Harmonicity (cc)", 0.01, 75.0, 0.1, 1.0).values[0][0])
    return dict(f0=round(med, 1), f0_p10=round(p10, 1), f0_p90=round(p90, 1),
                span_st=round(float(span), 2),
                hnr=None if not np.isfinite(hnr) else round(hnr, 1),
                voiced=round(len(v) * 0.01, 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", required=True, help="逗号分隔的 take 目录")
    ap.add_argument("--out", default="_hard_all.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-spk", action="store_true")
    a = ap.parse_args()

    dirs = [d.strip() for d in a.dirs.split(",") if d.strip()]
    state = load_state()

    import spk_embed as S
    ref_e = None if a.no_spk else S.embed(REF)

    res = {}
    embs = {}          # (dir, uid) -> vector
    for d in dirs:
        full = d if os.path.isabs(d) else os.path.join(HERE, d)
        base = os.path.basename(full.rstrip("/\\"))
        tag = base.replace("_mt_adv_", "")
        amap = asr_map(os.path.join(HERE, "_prom_asr_%s.json" % base))
        wavs = sorted(glob.glob(os.path.join(full, "*.wav")))
        if a.limit:
            wavs = wavs[: a.limit]
        res[tag] = {}
        print("== %s  %d 条  asr=%d" % (tag, len(wavs), len(amap)), flush=True)
        for i, w in enumerate(wavs):
            uid = os.path.basename(w)[:-4]
            text = (state.get(uid) or {}).get("text", "")
            try:
                sig, sr = read_wav(w)
                lv = level_check(sig, sr)
                f0 = f0_check(w)
                sv, mc, ma, atxt = swallow_check(text, amap.get(uid))
                rec = dict(uid=uid, text=text, dur=round(len(sig) / float(sr), 2),
                           asr=sv, miss=ma, asr_text=atxt[:120], **lv, **f0)
                if not a.no_spk:
                    e = S.embed(w)
                    embs[(tag, uid)] = e
                    rec["spk_ref"] = round(float(S.cos(e, ref_e)), 3)
                res[tag][uid] = rec
            except Exception as ex:
                res[tag][uid] = dict(uid=uid, text=text, err="%s: %s" % (type(ex).__name__, str(ex)[:80]))
            if (i + 1) % 10 == 0:
                print("   %d/%d" % (i + 1, len(wavs)), flush=True)

    # 同单元跨 seed 余弦
    if not a.no_spk:
        print("== 同单元跨 seed 声纹", flush=True)
        by_uid = {}
        for (tag, uid), e in embs.items():
            by_uid.setdefault(uid, []).append((tag, e))
        for uid, lst in by_uid.items():
            if len(lst) < 2:
                continue
            for tag, e in lst:
                cs = [float(S.cos(e, e2)) for t2, e2 in lst if t2 != tag]
                res[tag][uid]["spk_peer"] = round(max(cs), 3)
                res[tag][uid]["spk_peer_min"] = round(min(cs), 3)

    json.dump(res, open(os.path.join(HERE, a.out), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    n = sum(len(v) for v in res.values())
    print("写出 %s（%d 条 / %d 批）" % (a.out, n, len(res)))


if __name__ == "__main__":
    main()
