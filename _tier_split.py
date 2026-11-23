# -*- coding: utf-8 -*-
"""_tier_split.py —— 把每个 (角色, 情绪) 的参考档按**声学强度**切成两档

用户 2026-11-14 23:2x 定调：
  「情绪分档……整一个普通的情绪，然后再整一个更加激烈的情绪，
   这两个档对于有声书来说应该是够了。」
  「等会你要切片的话，就这样按我的这样要求切两个档够用了。」

为什么不按 z 分：z 是「该参考在本角色情绪空间里的位置」，不是强度。
实测 `Thomas calm` 4 档 z = 2.1/2.081/2.071/2.007（跨度 0.09，等于没差），
`Thomas nervous`/`Charles defiant`/`Charles wronged` 的 z 全是 0.0（未标定）。
⇒ z 不能当强度尺，必须用**声学量**。

强度分（角色内标准化，跨角色不比）
  F0 中位（半音，相对本角色全部参考的中位）   权重 0.45  ← 激烈=音高抬升
  voiced RMS（dBFS）                          权重 0.35  ← 激烈=更响
  语速（wpm，词数/时长）                       权重 0.20  ← 激烈=更快

切法：角色内该情绪所有档按强度分排序，前半 normal / 后半 intense。
档数 = 1 的，标 need_split（要补切素材）。
档数 = 2 的，直接低/高。
档数 >= 3 的，取最低档作 normal、最高档作 intense（中间档保留为 fallback）。

产出
  `_ref_tier2.json`   {role: {emo: {normal: {path,name,score}, intense: {...}, ...}}}
  `_ref_tier2.md`     人读报告：每档强度明细 + 需补切的清单

用法：G:/Python310/python.exe _tier_split.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
LIB = "G:/_setup/_emo_refs_all.json"
OUT_JSON = "G:/_setup/_ref_tier2.json"
OUT_MD = "G:/_setup/_ref_tier2.md"

W_ARO, W_F0 = 0.70, 0.30

_VOX = None


def _vox():
    global _VOX
    if _VOX is None:
        # ★ ser.py 在 emo_bench 子目录，不在 _setup 根。只靠外部 PYTHONPATH
        #   在这台机器上会被 shell 引号吃掉（实测 99 条全 null ⇒ 强度分退化成只看 F0）。
        #   必须在代码里显式加路径。
        if "G:/_setup/emo_bench" not in sys.path:
            sys.path.insert(0, "G:/_setup/emo_bench")
        import ser as S
        _VOX = S.VoxDim()
    return _VOX


def feats(p):
    """单条参考的声学特征。

    ★ 强度主尺改用 **vox arousal（唤醒度）**，不是自己拍的 F0/RMS/wpm 加权。
      原因：实测 `Charles angry` 两档 F0 271→312（升）、RMS −23.2→−30.5（降 7.3dB）、
      wpm 127→165（升），三个量方向相反，手工权重一加就抵消成「差 0.00」。
      arousal 是心理学标准的「激烈程度」维度，不需要拍权重。

    ★ 算 arousal 前先归一到 voiced RMS −24dBFS：参考素材本身电平从 −23 到 −48dBFS
      不等（旧切片没统一），不归一会把「录音响」当成「演得激烈」。
    """
    import mt_seg_drift as D
    a, sr = D.read_wav(p)
    dur = len(a) / sr
    S = D.series(a, sr)
    f0 = np.asarray(S["f_p"], dtype=float)
    f0 = f0[f0 > 0]
    cen = np.asarray(S["cen"], dtype=float)
    cen = cen[cen > 0]
    hh = np.asarray(S["h_h"], dtype=float)
    hh = hh[hh > -100]
    # ★ 不能写 `S.get("rms") or []` —— numpy 数组的真值判断会抛
    #   ValueError: truth value of an array is ambiguous，然后被上层 except 记成
    #   「全部不可读」（同型静默兜底第 N 次）。
    _rms = S.get("rms")
    rms_arr = np.asarray(_rms if _rms is not None else [], dtype=float)
    rms_arr = rms_arr[np.isfinite(rms_arr)]
    if len(rms_arr):
        thr = float(np.percentile(rms_arr, 25))
        vr = rms_arr[rms_arr > thr]
        rms = float(np.median(vr if len(vr) else rms_arr))
    else:
        rms = None

    aro = None
    try:
        import soundfile as sf
        tmp_dir = "G:/_setup/_tier_tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        y = a.astype(np.float32)
        if rms is not None:
            y = y * (10 ** ((-24.0 - rms) / 20.0))
        tmp = os.path.join(tmp_dir, os.path.basename(p))
        sf.write(tmp, np.clip(y, -1.0, 1.0), sr, subtype="PCM_16")
        sc = _vox().score(tmp) or {}
        v = sc.get("arousal")
        aro = float(v) if v is not None else None
    except Exception as e:
        print("  arousal 失败 %s: %s" % (os.path.basename(p), e), flush=True)
        aro = None

    return dict(
        dur=round(dur, 2),
        f0=round(float(np.median(f0)), 1) if len(f0) else None,
        cen=round(float(np.median(cen)), 0) if len(cen) else None,
        hnr=round(float(np.median(hh)), 1) if len(hh) else None,
        rms=round(rms, 1) if rms is not None else None,
        arousal=(round(aro, 4) if aro is not None else None),
        n_fr=len(rms_arr),
    )


def main():
    lib = json.load(open(LIB, encoding="utf-8"))

    # 1) 逐条测特征
    rows = []
    for role in sorted(lib):
        for emo in sorted(lib[role]):
            for i, it in enumerate(lib[role][emo]):
                p = it.get("path") if isinstance(it, dict) else it
                if not p or not os.path.exists(p):
                    rows.append(dict(role=role, emo=emo, idx=i + 1, path=p,
                                     name=(it.get("name") if isinstance(it, dict) else ""),
                                     text=(it.get("text") if isinstance(it, dict) else ""),
                                     err="路径不存在"))
                    continue
                try:
                    f = feats(p)
                except Exception as e:
                    rows.append(dict(role=role, emo=emo, idx=i + 1, path=p,
                                     name=(it.get("name") if isinstance(it, dict) else ""),
                                     text=(it.get("text") if isinstance(it, dict) else ""),
                                     err=str(e)[:80]))
                    continue
                words = len((it.get("text") or "").split()) if isinstance(it, dict) else 0
                f["wpm"] = round(words / f["dur"] * 60, 1) if words and f["dur"] else None
                rows.append(dict(role=role, emo=emo, idx=i + 1, path=p,
                                 name=(it.get("name") if isinstance(it, dict) else ""),
                                 text=(it.get("text") if isinstance(it, dict) else ""),
                                 **f))
    ok = [r for r in rows if not r.get("err")]
    print("参考 %d 条，可用 %d 条" % (len(rows), len(ok)))

    # 2) 角色内标准化：arousal 与 ΔF0（半音）各做 z，再按 0.70/0.30 合成
    out = {}
    md = ["# 情绪两档：按**唤醒度**切（普通 / 激烈）", "",
          "> 强度主尺 = vox **arousal**（0.70）+ ΔF0 半音（0.30），**角色内**标准化。",
          "> 不用自己拍的 F0/RMS/wpm 加权：实测 `Charles angry` 三个量方向相反（F0↑ RMS↓ wpm↑），",
          "> 手工权重一加就抵消成「差 0.00」。arousal 是心理学标准的「激烈程度」维度。",
          "> 也不按 z 分：z 是「参考在情绪空间里的位置」，不是强度（Thomas calm 4 档 z 跨度仅 0.09）。",
          "> 算 arousal 前已归一到 voiced RMS −24dBFS（参考素材原始电平 −23~−48dBFS 不等）。", ""]
    need_split = []

    for role in sorted(set(r["role"] for r in ok)):
        rr = [r for r in ok if r["role"] == role]
        f0s = [r["f0"] for r in rr if r["f0"]]
        role_f0 = float(np.median(f0s)) if f0s else None
        for r in rr:
            r["f0_st"] = (round(12 * np.log2(r["f0"] / role_f0), 2)
                          if r["f0"] and role_f0 else None)
        for key in ("arousal", "f0_st"):
            v = [r[key] for r in rr if r.get(key) is not None]
            if not v:
                for r in rr:
                    r["z_" + key] = 0.0
                continue
            mu, sd = float(np.mean(v)), float(np.std(v)) or 1.0
            for r in rr:
                r["z_" + key] = round((r[key] - mu) / sd, 3) if r.get(key) is not None else 0.0
        for r in rr:
            r["score"] = round(W_ARO * r["z_arousal"] + W_F0 * r["z_f0_st"], 3)

    # 3) 每个 (角色,情绪) 切两档
    for role in sorted(lib):
        out[role] = {}
        for emo in sorted(lib[role]):
            rr = [r for r in ok if r["role"] == role and r["emo"] == emo]
            bad = [r for r in rows if r["role"] == role and r["emo"] == emo and r.get("err")]
            if not rr:
                out[role][emo] = dict(normal=None, intense=None, n=0,
                                      note="无可用参考（%d 条不可读）" % len(bad))
                need_split.append((role, emo, 0, "全部不可读"))
                continue
            rr.sort(key=lambda x: x["score"])
            def brief(x):
                nm = x.get("name") or os.path.splitext(os.path.basename(x["path"] or ""))[0]
                return dict(path=x["path"], name=nm, score=x["score"],
                            f0=x["f0"], f0_st=x["f0_st"], rms=x["rms"],
                            arousal=x.get("arousal"), wpm=x["wpm"], hnr=x["hnr"],
                            dur=x["dur"], text=(x["text"] or "")[:60])
            if len(rr) == 1:
                # ★ 单档不等于「缺档」：先在**本角色**其它情绪里找情绪空间最近、
                #   且唤醒度确实更高的那条当代理（`_tier_excited_nn.py`）。
                #   实测 Thomas excited 唯一原生参考 arousal 0.760，池子上限 0.857，
                #   硬门槛 Δaro>=0.08 内最近的是 Thomas_defiant_3（0.844，d=0.10）。
                #   只有本角色池子里也找不出强度差，才真的标「需补切」。
                out[role][emo] = dict(normal=brief(rr[0]), intense=None, n=1,
                                      note="只有 1 档；激烈档待 _tier_excited_nn.py 取最近邻代理")
                need_split.append((role, emo, 1, "只有 1 档（先取最近邻代理，仍不够才补切）"))
            elif len(rr) == 2:
                out[role][emo] = dict(normal=brief(rr[0]), intense=brief(rr[1]), n=2,
                                      mid=[], note="低=普通 / 高=激烈")
            else:
                mid = [brief(x) for x in rr[1:-1]]
                out[role][emo] = dict(normal=brief(rr[0]), intense=brief(rr[-1]),
                                      mid=mid, n=len(rr),
                                      note="取最低=普通 / 最高=激烈；中间 %d 档留作 fallback" % len(mid))

    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", OUT_JSON)

    # 4) 报告
    md.append("## 一、分档结果")
    md.append("")
    md.append("| 角色 | 情绪 | 档数 | 普通档 | 激烈档 | 强度差 |")
    md.append("|---|---|---|---|---|---|")
    for role in sorted(out):
        for emo in sorted(out[role]):
            v = out[role][emo]
            n, i = v.get("normal"), v.get("intense")
            gap = ("%+.2f" % (i["score"] - n["score"])) if n and i else "-"
            md.append("| %s | %s | %d | %s | %s | %s |" % (
                role, emo, v.get("n", 0),
                ("%s (%.2f)" % (n["name"], n["score"])) if n else "-",
                ("%s (%.2f)" % (i["name"], i["score"])) if i else "**缺**",
                gap))
    md.append("")
    md.append("## 二、强度明细（每档的声学量）")
    md.append("")
    for role in sorted(out):
        for emo in sorted(out[role]):
            v = out[role][emo]
            items = [(k, v[k]) for k in ("normal", "intense") if v.get(k)]
            if not items:
                continue
            md.append("### %s / %s（%d 档）" % (role, emo, v.get("n", 0)))
            md.append("")
            md.append("| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |")
            md.append("|---|---|---|---|---|---|---|---|---|---|")
            for lab, x in items:
                md.append("| %s | %s | %.2f | %s | %s | %s | %s | %s | %s | %s |" % (
                    lab, x["name"], x["score"], x.get("arousal"), x["f0"], x["f0_st"],
                    x["rms"], x["wpm"], x["dur"], (x["text"] or "").replace("|", "/")))
            md.append("")

    md.append("## 三、需要补切素材的（缺激烈档或只有 1 档）")
    md.append("")
    if need_split:
        md.append("| 角色 | 情绪 | 现有档数 | 原因 |")
        md.append("|---|---|---|---|")
        for role, emo, n, why in need_split:
            md.append("| %s | %s | %d | %s |" % (role, emo, n, why))
    else:
        md.append("无 —— 全部角色情绪都已有两档。")
    md.append("")
    md.append("## 四、必须如实说的局限")
    md.append("")
    md.append("1. **两档的音色不同**：条间实测换档落差中位 6.4 半音。用激烈档生成同一角色，")
    md.append("   听感会比普通档「更亮/更高」，这是设计层代价，不是 bug。")
    md.append("2. **强度分是相对量**：角色内标准化，只能排「同角色内谁更激烈」，")
    md.append("   不能跨角色比（Thomas 的激烈 ≠ Charles 的激烈）。")
    md.append("3. **档数少时切分不稳**：2 档只能比大小，无法验证「中间没有第三档」。")
    md.append("   3 档以上才有 fallback 余量。")

    open(OUT_MD, "w", encoding="utf-8").write("\n".join(md))
    print("写出", OUT_MD)
    print("\n需补切 %d 项：" % len(need_split))
    for x in need_split:
        print("  %-8s %-8s %d 档  %s" % x)


if __name__ == "__main__":
    main()
