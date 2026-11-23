# -*- coding: utf-8 -*-
"""mt_voice_gate.py —— 音色闸门：产物 vs **它自己那一档**的参考音。

★★★ 为什么不能跨情绪比（2026-10-31 实测）
  CAM++ 声纹在这批素材上**连角色都分不开**：
    同角色不同句子 中位 0.382 / 跨角色不同句子 中位 0.383 / AUC 0.491（=随机）
    同一 ref 不同句子 0.344，同一句不同 seed 0.796
  ⇒ 方差几乎全部来自「内容」，不是「音色」。跨档比（normal vs angry 0.46）
    不是"模型不行"，是**口径本来就错**：拿愤怒去比平静，必然低。
  ⇒ 声纹在本项目**不作验收判据**，只留作同句同档的自洽性参考。

★★ 用什么代替：三个直接可测的声道/发声参数
  F0 中位      —— 情绪档最直接的量（Charles 185/248/395/429，Hooper 203/219/334/245）
  谱质心       —— 声道长度 + 发声紧张度（927~2084 Hz）
  谱倾斜       —— 音色亮暗（-8.4 ~ -0.9 dB/kHz）
  三者都与"内容"弱相关，与"这一档怎么发声"强相关。

★★★ 测量范围必须固定（否则基线自己就是错的）
  E_begging 在 60-700 下中位 486.7，在 100-400 下 243.4 —— 正好 2 倍，八度错误。
  C_angry  在 60-700 下 474.6，在 100-400 下 235.6 —— 同样 2 倍。
  统一用 75-500 Hz，并同时输出「八度跳变率」（浊音帧里 F0 落在 2 倍基频附近的比例），
  跳变率 >25% 的条目 F0 判据作废，只看谱参数。

用法：
  python mt_voice_gate.py --jobs cloud/cuda/jobs_probe.json --dir probe_out --report probe_voice.json
  python mt_voice_gate.py --one some.wav --ref castle_fr_ref/2_charles_soft.wav
"""
import argparse
import glob
import json
import os
import sys
import wave

import numpy as np
import parselmouth
from parselmouth.praat import call

ROOT = os.path.dirname(os.path.abspath(__file__))
REFDIR = os.path.join(ROOT, "castle_fr_ref")

# F0 测量范围：必须按说话人设。这两个角色都是 9~10 岁童声，真实基频 173~395 Hz。
# 用 75-500 会成片锁到 2 倍频（实测 h07 471 / h08 470 / c19 447，实际 242/247/226），
# 而且整条都是 2 倍时「剔除 2x 帧」的规则也救不回来 —— 中位本身就是错的。
# 100-400 覆盖全部真实基频，同时把 2 倍频（>400）挡在外面。
F0_LO, F0_HI = 100.0, 400.0

# 容差：F0 ±3 半音（八档最小档距 5.1 半音，留一半余量）
#       谱质心比值 0.78~1.28；谱倾斜 ±3.0 dB/kHz
TOL_ST = 3.0
TOL_CEN = (0.78, 1.28)
TOL_SLP = 3.0
OCT_SKIP_MAX = 0.25


def read_wav(p):
    w = wave.open(p, "rb")
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    w.close()
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def _robust_f0(f0):
    """剔除八度错帧后返回 (主簇中位, 剔除比例)。

    parselmouth 在童声/尖叫上会成片地抓到 2 倍或 0.5 倍基频（实测 E_begging
    切片跨 106~627 Hz）。做法：以当前中位为参照，剔掉落在 0.5x / 2x 附近的帧，
    迭代到中位稳定。剔除比例过高说明这条本身不可信。
    """
    if len(f0) < 10:
        return None, 1.0, f0
    n0 = len(f0)
    m = float(np.median(f0))
    for _ in range(3):
        ratio = f0 / m
        keep = ~(((ratio > 0.42) & (ratio < 0.58)) | ((ratio > 1.72) & (ratio < 2.28)))
        if keep.sum() < 0.45 * len(f0):
            break
        f2 = f0[keep]
        m2 = float(np.median(f2))
        if abs(m2 - m) < 0.5:
            f0, m = f2, m2
            break
        f0, m = f2, m2
    return m, 1.0 - len(f0) / n0, f0


def measure(p):
    """返回 dict(f0, span, cen, slp, oct_skip, dur)。"""
    a, sr = read_wav(p)
    dur = len(a) / sr
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)

    pitch = call(snd, "To Pitch", 0.0, F0_LO, F0_HI)
    f0 = pitch.selected_array["frequency"]
    f0 = f0[f0 > 0]
    if len(f0) < 10:
        return dict(dur=dur, f0=None, span=None, cen=None, slp=None, oct_skip=1.0)
    med, oct_skip, f0c = _robust_f0(f0)
    if med is None:
        return dict(dur=dur, f0=None, span=None, cen=None, slp=None, oct_skip=1.0)

    nfft, hop = 1024, 256
    win = np.hanning(nfft)
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    band = freqs < 4000
    cen, slp = [], []
    for i in range(0, len(a) - nfft, hop):
        seg = a[i:i + nfft]
        if np.sqrt((seg ** 2).mean()) < 0.01:
            continue
        S = np.abs(np.fft.rfft(seg * win))
        if S.sum() <= 0:
            continue
        cen.append(float((freqs * S).sum() / S.sum()))
        L = 20 * np.log10(S + 1e-10)
        slp.append(float(np.polyfit(freqs[band] / 1000.0, L[band], 1)[0]))
    return dict(dur=dur, f0=med,
                span=float(np.percentile(f0c, 95) - np.percentile(f0c, 5)),
                cen=float(np.median(cen)) if cen else None,
                slp=float(np.median(slp)) if slp else None,
                oct_skip=oct_skip)


def st_diff(a, b):
    """半音差。"""
    if not a or not b:
        return None
    return 12.0 * np.log2(a / b)


def load_baseline(path=None):
    """读 _voice_baseline.json：每档自己的 F0/谱质心/谱倾斜带。

    ★ 这是「四把尺子」的落地：每一档的容差来自**它自己**的切片分布，
      不是全局固定值。C_soft 的带 163~217 与 E_loud 的 282~377 互不相干。
    """
    p = path or os.path.join(ROOT, "_voice_baseline.json")
    if not os.path.exists(p):
        return {}
    return json.load(open(p, encoding="utf-8"))


def judge_band(m, band):
    """产物 m 是否落在它自己那一档的带内。返回 (verdict, reasons, 数值)。

    ★ 判据是「3 个参数里至少 2 个在带内」，不是「全部在带内」。
      原因：三个参数各自 p10-p90 只覆盖 80%，要求同时命中就只剩 0.8³≈51%
      （实测 C_normal 对角线 50%）。而我们要回答的是「这条还是不是这一档的声音」，
      不是「三个维度同时完美」——后者会把正常产物判成不合格。
    """
    bad = []
    info = {}
    n_in = n_tot = 0

    if m["f0"] is None:
        bad.append("F0缺失")
    else:
        st = 12 * np.log2(m["f0"] / band["f0"]["med"])
        info["st"] = round(float(st), 2)
        n_tot += 1
        if band["f0"]["lo"] <= m["f0"] <= band["f0"]["hi"]:
            n_in += 1
        elif m["oct_skip"] > OCT_SKIP_MAX:
            bad.append("F0跳变%.0f%%(不作判)" % (100 * m["oct_skip"]))
            n_tot -= 1
        else:
            bad.append("F0 %+.1f半音 出带" % st)

    if m["cen"] and band["cen"]["med"]:
        ratio = m["cen"] / band["cen"]["med"]
        info["cen_ratio"] = round(float(ratio), 2)
        n_tot += 1
        if band["cen"]["lo"] <= m["cen"] <= band["cen"]["hi"]:
            n_in += 1
        else:
            bad.append("谱质心×%.2f 出带" % ratio)

    if m["slp"] is not None and band["slp"]["med"] is not None:
        d = m["slp"] - band["slp"]["med"]
        info["slp_d"] = round(float(d), 2)
        n_tot += 1
        if band["slp"]["lo"] <= m["slp"] <= band["slp"]["hi"]:
            n_in += 1
        else:
            bad.append("谱倾斜%+.1f 出带" % d)

    info["n_in"] = "%d/%d" % (n_in, n_tot)
    if n_tot == 0:
        return "WARN", bad + ["无可判参数"], info
    if n_in == n_tot:
        return "PASS", [], info
    if n_in >= max(2, n_tot - 1):
        return "PASS", bad, info          # 2/3 在带内 -> 认
    if n_in >= 1:
        return "WARN", bad, info
    return "FAIL", bad, info


def judge(m, r):
    """兜底：没有基线时，产物 m 对参考 r 用固定容差判。"""
    bad = []
    st = st_diff(m["f0"], r["f0"])
    if st is None:
        bad.append("F0缺失")
    elif abs(st) > TOL_ST:
        if m["oct_skip"] > OCT_SKIP_MAX:
            bad.append("F0跳变%.0f%%(不作判)" % (100 * m["oct_skip"]))
        else:
            bad.append("F0偏%.1f半音" % st)
    if m["cen"] and r["cen"]:
        ratio = m["cen"] / r["cen"]
        if not (TOL_CEN[0] <= ratio <= TOL_CEN[1]):
            bad.append("谱质心×%.2f" % ratio)
    if m["slp"] is not None and r["slp"] is not None:
        d = m["slp"] - r["slp"]
        if abs(d) > TOL_SLP:
            bad.append("谱倾斜%+.1f" % d)
    hard = [x for x in bad if "不作判" not in x]
    if not hard:
        return "PASS", bad
    return ("WARN" if len(hard) == 1 else "FAIL"), bad


def load_refs():
    """从 cast.json 取每个音色档的 ref，算基线。"""
    cast = json.load(open(os.path.join(ROOT, "cloud", "ref", "cast.json"), encoding="utf-8"))
    refs = {}
    for who, c in cast.items():
        if who.startswith("_"):
            continue
        for emo, ev in (c.get("emotions") or {}).items():
            key = "%s_%s" % (who, emo)
            p = os.path.join(ROOT, "cloud", ev["ref"].replace("../", ""))
            if os.path.exists(p):
                refs[key] = dict(path=p, who=who, emo=emo,
                                 name="%s · %s" % (c["name"], ev.get("zh", emo)),
                                 m=measure(p))
    return refs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", help="jobs json（含 who/emo/ref 与 out）")
    ap.add_argument("--dir", help="产物根目录")
    ap.add_argument("--one", help="单条产物")
    ap.add_argument("--ref", help="--one 时用的参考音")
    ap.add_argument("--report", default="")
    a = ap.parse_args()

    refs = load_refs()
    bands = load_baseline()
    print("每档独立基线（F0 %g-%g Hz，按童声设；带来自该档自己的切片）：" % (F0_LO, F0_HI))
    print("%-11s %-22s %6s %14s %14s %12s"
          % ("档", "名称", "n", "F0 带", "谱质心带", "谱倾斜带"))
    for k, v in refs.items():
        b = bands.get(k)
        if b:
            print("%-11s %-22s %6d %14s %14s %12s"
                  % (k, v["name"], b["n_clips"],
                     "%.0f~%.0f" % (b["f0"]["lo"], b["f0"]["hi"]),
                     "%.0f~%.0f" % (b["cen"]["lo"], b["cen"]["hi"]),
                     "%.1f~%.1f" % (b["slp"]["lo"], b["slp"]["hi"])))
        else:
            print("%-11s %-22s %6s %14s" % (k, v["name"], "-", "无基线"))

    if a.one:
        m = measure(a.one)
        if a.ref:
            r = measure(a.ref)
        else:
            key = os.path.basename(a.one).split("_p")[0]
            r = refs[key]["m"] if key in refs else None
        if not r:
            print("!! 找不到参考音，用 --ref 指定", file=sys.stderr)
            return 2
        v, why = judge(m, r)
        print("\n%s  F0 %.1f (Δ%+.1f半音)  谱质心 %.0f (×%.2f)  谱倾斜 %.1f (Δ%+.1f)"
              % (os.path.basename(a.one), m["f0"] or 0, st_diff(m["f0"], r["f0"]) or 0,
                 m["cen"] or 0, (m["cen"] / r["cen"]) if m["cen"] and r["cen"] else 0,
                 m["slp"] or 0, (m["slp"] - r["slp"]) if m["slp"] is not None and r["slp"] is not None else 0))
        print("判定 %s %s" % (v, " ".join(why)))
        return 0 if v == "PASS" else 1

    if not a.jobs:
        print("需要 --jobs 或 --one", file=sys.stderr)
        return 2
    jobs = json.load(open(a.jobs, encoding="utf-8"))["jobs"]
    base = a.dir or ROOT
    rows, cnt = [], {}
    for j in jobs:
        p = os.path.join(base, j["out"])
        if not os.path.exists(p):
            continue
        key = j.get("who") or ""
        m = measure(p)
        # ★ 只跟它自己那一档比：有该档基线就用基线带，否则退回 ref 固定容差
        if key in bands:
            v, why, info = judge_band(m, bands[key])
            st = info.get("st")
            cr = info.get("cen_ratio")
        elif key in refs:
            v, why = judge(m, refs[key]["m"])
            st = st_diff(m["f0"], refs[key]["m"]["f0"])
            cr = (m["cen"] / refs[key]["m"]["cen"]
                  if m["cen"] and refs[key]["m"]["cen"] else None)
        else:
            continue
        cnt[v] = cnt.get(v, 0) + 1
        rows.append(dict(uid=j["uid"], key=key, seed=j.get("seed"), file=j["out"],
                         verdict=v, why=why,
                         f0=m["f0"], st=st,
                         cen=m["cen"], cen_ratio=cr,
                         slp=m["slp"], oct_skip=m["oct_skip"], dur=m["dur"]))
    if not rows:
        print("没有可判定的产物（检查 --dir 与 jobs 的 out 路径）", file=sys.stderr)
        return 2

    print("\n%-16s %-5s %-6s %8s %8s %8s %6s  %s"
          % ("uid", "seed", "判定", "Δ半音", "谱质心×", "谱倾斜", "跳变", "原因"))
    for r in sorted(rows, key=lambda x: (x["key"], x["uid"])):
        print("%-16s %-5s %-6s %8s %8s %8s %5.0f%%  %s"
              % (r["uid"], r["seed"], r["verdict"],
                 "%+.1f" % r["st"] if r["st"] is not None else "-",
                 "%.2f" % r["cen_ratio"] if r["cen_ratio"] else "-",
                 "%+.1f" % r["slp"] if r["slp"] is not None else "-",
                 100 * r["oct_skip"], " ".join(r["why"]) or "-"))
    print("\n汇总 %s（共 %d 条）" % (cnt, len(rows)))
    # 分档汇总：每档自己的通过率，不跨档比较
    print("\n分档通过率（每档独立，互不参照）：")
    by = {}
    for r in rows:
        by.setdefault(r["key"], []).append(r["verdict"])
    for k in sorted(by):
        vs = by[k]
        npass = sum(1 for x in vs if x == "PASS")
        print("  %-11s %d/%d PASS%s" % (k, npass, len(vs),
                                        "" if npass == len(vs) else "  ← 需查"))
    if a.report:
        json.dump(dict(refs={k: v["m"] for k, v in refs.items()},
                       bands=bands, rows=rows,
                       summary=cnt, tol=dict(st=TOL_ST, cen=TOL_CEN, slp=TOL_SLP)),
                  open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("报告 ->", a.report)
    return 0 if cnt.get("FAIL", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
