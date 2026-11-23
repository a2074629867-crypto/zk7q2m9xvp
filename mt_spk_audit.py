# -*- coding: utf-8 -*-
"""mt_spk_audit.py —— 音色/电平/F0 审计（回环缺的第二道门）。

背景：`mt_loop.py` + `_gate.py` 只判「主重音落位对不对」，**没有一条测音色**。
2026-10-26 的 0.29 事故就是这么漏的：重音门禁给 PASS，实际换了个人。

这道门不参与「重音好不好」，只回答三个问题：
  1. 还是同一个人吗？（声纹 vs 该角色的 ref.wav）
  2. 音量跟同批一致吗？（voiced RMS 对本批中位）
  3. 有没有压嗓 / 喊？（F0 中位出 [170, 305]）

声纹有个坑必须处理：**它与句长强相关**（实测 ≥8s p50 0.865；2~4s p50 0.387；
同文件切两半自比 2s 只有 0.445）。所以短句的声纹分数不能直接下判决，
本脚本按句长分档，短句标 SHORT 只记录不判 VOID。

用法：
  python mt_spk_audit.py --ch ch2 --seeds 42,1234 --ref G:/_setup/cloud/ref/ref.wav
  python mt_spk_audit.py --ch ch2 --only N0184,N0185

输出 _spkaudit_<ch>.json：[{uid,seed,dur,spk,spk_verdict,rms,f0,flags,verdict}]
verdict ∈ OK / WARN / VOID，VOID 表示「这条 take 不要采用」。
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab")

SPK_OK, SPK_WARN = 0.65, 0.55
RMS_TARGET = -24.0
RMS_TOL = 6.0

# ★ F0 不能用绝对区间。Charles 是童声，基线 72Hz；套成人女声的 [170,305]
#   会把整批判成异常（2026-10-30 实测 13/13 全部误报）。改成相对 ref 的半音偏差。
#   记忆里的口径：F0 跳变用 cent 判，>300c 才算跳；这里放到 500c（约 5 个半音）留余量。
F0_CENTS_MAX = 500.0

SPK_MIN_SEC = 4.0        # 短于这个只记录，不下判决
SPK_STRICT_SEC = 8.0     # 长于这个用严格阈值（阈值本就按长句标定）


def load_mono(path):
    x, sr = sf.read(path)
    if x.ndim > 1:
        x = x.mean(1)
    return x.astype(np.float32), sr


def voiced_rms(x, sr, frame=0.02):
    n = max(1, int(frame * sr))
    k = len(x) // n
    if k < 3:
        return float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9))
    f = x[:k * n].reshape(k, n)
    db = 20 * np.log10(np.sqrt((f ** 2).mean(1)) + 1e-9)
    on = db > (np.percentile(db, 95) - 12.0)
    if not on.any():
        return float(db.max())
    return float(20 * np.log10(np.sqrt((f[on] ** 2).mean()) + 1e-9))


def f0_median(x, sr):
    try:
        import parselmouth
    except Exception:
        return None
    snd = parselmouth.Sound(x, sampling_frequency=sr)
    p = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=400)
    v = p.selected_array["frequency"]
    v = v[v > 0]
    return float(np.median(v)) if len(v) >= 3 else None


def spk_verdict(cos, dur):
    if cos is None:
        return "ERR"
    if dur < SPK_MIN_SEC:
        return "SHORT"
    if cos >= SPK_OK:
        return "OK"
    if cos >= SPK_WARN:
        return "WARN"
    return "VOID"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", required=True)
    ap.add_argument("--seeds", default="42,1234")
    ap.add_argument("--trim-prefix", default="_mt_trim")
    ap.add_argument("--ref", default="G:/_setup/cloud/ref/ref.wav")
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    seeds = [s.strip() for s in a.seeds.split(",") if s.strip()]
    only = {x.strip() for x in a.only.split(",") if x.strip()}

    import spk_embed as S
    ref_vec = S.embed(a.ref) if os.path.exists(a.ref) else None
    if ref_vec is None:
        print("!! 参考音频缺失：%s（声纹列将为空）" % a.ref, file=sys.stderr)

    # ref 的 F0 基线：所有 F0 判据都是相对它的半音偏差
    ref_f0 = None
    if os.path.exists(a.ref):
        rx, rsr = load_mono(a.ref)
        ref_f0 = f0_median(rx, rsr)
    print("ref F0 基线 %s Hz" % (("%.1f" % ref_f0) if ref_f0 else "未测出"))

    rows = []
    for sd in seeds:
        d = "%s_%s_s%s" % (a.trim_prefix, a.ch, sd)
        for p in sorted(glob.glob(os.path.join(d, "*.wav"))):
            uid = os.path.basename(p)[:-4]
            if only and uid not in only:
                continue
            x, sr = load_mono(p)
            dur = len(x) / sr
            cos = None
            if ref_vec is not None and dur >= 2.0:
                try:
                    cos = float(S.cos(ref_vec, S.embed(p)))
                except Exception as e:
                    print("  spk 失败 %s/%s: %s" % (sd, uid, str(e)[:60]))
            sv = spk_verdict(cos, dur)
            rms = voiced_rms(x, sr)
            f0 = f0_median(x, sr)

            flags = []
            if sv == "VOID":
                flags.append("换人")
            elif sv == "WARN":
                flags.append("声纹偏低")
            if f0 is not None and ref_f0:
                cents = 1200.0 * np.log2(f0 / ref_f0)
                if abs(cents) > F0_CENTS_MAX:
                    flags.append("F0%+d" % int(round(cents)))
            rows.append(dict(uid=uid, seed=sd, dur=round(dur, 2),
                             spk=None if cos is None else round(cos, 3),
                             spk_verdict=sv, rms=round(rms, 1),
                             f0=None if f0 is None else round(f0, 1),
                             flags=flags))

    # 电平改用本批中位：单章内部一致比全库绝对值更实用（跨章别直接比）
    if rows:
        m = float(np.median([r["rms"] for r in rows]))
        for r in rows:
            if abs(r["rms"] - m) > RMS_TOL and "电平" not in r["flags"]:
                r["flags"].append("电平")
        print("本批 voiced RMS 中位 %.1fdB（目标 %.0f）" % (m, RMS_TARGET))

    for r in rows:
        v = "VOID" if "换人" in r["flags"] else ("WARN" if r["flags"] else "OK")
        r["verdict"] = v

    out = a.out or "_spkaudit_%s.json" % a.ch
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("\n%-7s %-4s %-5s %-6s %-7s %-6s %s"
          % ("uid", "seed", "秒", "声纹", "RMS", "F0", "判定"))
    for r in rows:
        print("%-7s %-4s %5.1f  %-6s %6.1f  %-6s %s %s"
              % (r["uid"], r["seed"], r["dur"],
                 ("%.3f" % r["spk"]) if r["spk"] is not None else "-",
                 r["rms"], ("%.0f" % r["f0"]) if r["f0"] else "-",
                 r["verdict"], ",".join(r["flags"])))
    nv = sum(1 for r in rows if r["verdict"] == "VOID")
    nw = sum(1 for r in rows if r["verdict"] == "WARN")
    print("\n共 %d 条：OK %d / WARN %d / VOID %d" % (len(rows), len(rows) - nv - nw, nw, nv))
    print("写出 %s" % out)


if __name__ == "__main__":
    main()
