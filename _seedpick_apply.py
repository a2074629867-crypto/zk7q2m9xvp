# -*- coding: utf-8 -*-
"""_seedpick_apply.py —— 把 seed 择优选中的 take 落地：统一底噪 → 复检 → 备份回填。

流程
  1. 读 `_seedpick_summary.json`，只取 `pick` 非空的条目
  2. 复制 `_seedpick/<id>/s<pick>.wav` → `_elong_pick/<id>.wav`（供批量归一）
  3. `_dn_uniform.py --mode fill`：底噪统一到 −72dBFS、voiced RMS −24、48k/PCM_24
  4. 复检：G1 技术闸 + 句内音色一致 + 声纹 + 电平 + 时长比
  5. 全过 → 原文件备份到 `_bak_elong_1125/` → 覆盖 `out/<id>.wav`
     任一不过 → 只报告，不动文件

用法
  python _seedpick_apply.py              # 只体检，不写
  python _seedpick_apply.py --apply      # 体检通过的回填
  python _seedpick_apply.py --ids c1_0015,c2_0368 --apply
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
os.chdir("G:/_setup")

import dialog_gate as D          # noqa: E402
import gate_intra as G           # noqa: E402
import _dn_uniform as DU         # noqa: E402


def voiced_rms_db(path):
    """与 `_dn_uniform.norm_rms` 同口径的 voiced RMS（帧 p70 以上帧的 RMS）。

    ★ 不能用 `D.audio_stats()['rms_db']`：那是**全文件** RMS。
      含 `...` 长停顿的条目会被静音段拉低 —— c2_0368 全文件 −29.0，
      voiced 其实正好 −24，用全文件口径会误判 FAIL。
    """
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    db, h, w = DU.frame_db(y, sr)
    m = db > np.percentile(db, 70)
    cnt = 1 + max(0, (len(y) - w) // h)
    idx = np.clip(np.arange(w)[None, :] + h * np.arange(cnt)[:, None], 0, len(y) - 1)
    seg = y[idx][m]
    return float(20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-12))

OUTD = "G:/_setup/_audio_ch123/out"
SRC = "G:/_setup/_seedpick"
TMP = "G:/_setup/_elong_pick"
NRM = "G:/_setup/_elong_pick_norm"
BAK = "G:/_setup/_bak_elong_1125"
PY = "G:/Python310/python.exe"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--src", default="")
    ap.add_argument("--flat", action="store_true", help="源为 <src>/<id>.wav（裁剪输出）")
    ap.add_argument("--user-accepted", action="store_true",
                    help="用户逐条认可版本：不再要求「目标词必须延长」，只保技术闸")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    summ = {x["id"]: x for x in json.load(open("G:/_setup/_seedpick_summary.json",
                                              encoding="utf-8"))}
    if a.ids:
        want = {x.strip() for x in a.ids.split(",") if x.strip()}
        summ = {k: v for k, v in summ.items() if k in want}

    todo = []
    for rid, e in summ.items():
        if not e.get("pick"):
            print("%-9s 跳过（%s）" % (rid, e.get("reason") or "无候选"))
            continue
        # ★ 守卫：ratio <1.5 说明选中的 take 目标词并不比现役长，
        #   回填等于把一个本来就够长的拖音改短（c2_0299 就踩过：基线 well 550ms，
        #   候选最好 380ms，旧逻辑照样写 pick=44）。
        pr = e.get("pick_ratio")
        pk = next((r for r in (e.get("seeds") or []) if r["seed"] == e["pick"]), {})
        pt = pk.get("target") or 0
        # ★ 2026-11-25：用户逐条认可的 6 条里，c2_0309（look 290→200，0.69x）和
        #   c2_0372（it's 50→50，1.0x）本来就**不是**为了延长，而是语调/整体更自然。
        #   所以「必须 ≥1.5x」只对自动择优生效，用户点名时不能拿它卡。
        if pr is not None and pr < 1.5 and not a.user_accepted:
            print("%-9s 跳过（选中 take 只有 %.2fx，不算延长）" % (rid, pr))
            continue
        # ★ 上限看**绝对值**不看倍数：c3_0853 的 `I` 基线只有 20ms，290ms 就是 14.5x，
        #   但 290ms 是完全正常的拖音长度。c1_0035 的 well 1920ms 才是真的过头。
        if pt > 600:
            print("%-9s 跳过（目标词 %.0fms，单词语音超 600ms，一个词吃半句）" % (rid, pt))
            continue
        if a.flat:
            src = os.path.join(a.src or SRC, rid + ".wav")
        else:
            src = os.path.join(a.src or SRC, rid, "s%s.wav" % e["pick"])
        if not os.path.exists(src):
            print("%-9s 跳过（源缺失 %s）" % (rid, src))
            continue
        todo.append((rid, e, src))

    if not todo:
        print("没有可落地的条目")
        return
    os.makedirs(TMP, exist_ok=True)
    os.makedirs(NRM, exist_ok=True)
    for rid, e, src in todo:
        shutil.copy2(src, os.path.join(TMP, "%s.wav" % rid))

    ids = ",".join(rid for rid, _, _ in todo)
    print("\n[1/3] 统一底噪 / 电平 / 格式（%d 条）..." % len(todo))
    r = subprocess.run([PY, "G:/_setup/_dn_uniform.py", "--in", TMP, "--out", NRM,
                        "--ids", ids, "--mode", "fill", "--floor", "-72",
                        "--rel", "42", "--norm", "-24",
                        "--report", "G:/_setup/_elong_pick_norm.json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print((r.stdout or "")[-800:], (r.stderr or "")[-800:])
        sys.exit("归一化失败")

    print("\n[2/3] 复检")
    rows = []
    for rid, e, src in todo:
        p = os.path.join(NRM, "%s.wav" % rid)
        b = os.path.join(OUTD, "%s.wav" % rid)
        if not os.path.exists(p):
            rows.append((rid, "FAIL", "归一化未产出", None))
            continue
        s = D.audio_stats(p)
        tv, notes = D.gate_tech(s)
        s0 = D.audio_stats(b)
        dr = round(s["dur"] / s0["dur"], 2) if s0.get("dur") else None
        try:
            gv, gi = G.check(p)
        except Exception as ex:
            gv, gi = "ERR", {"code": "%s: %s" % (type(ex).__name__, ex)}
        sep = gi.get("sep") if isinstance(gi, dict) else None
        vr = voiced_rms_db(p)
        bad, warn = [], []
        if tv != "PASS":
            bad.append("tech:%s" % ",".join(x[0] for x in notes))
        # ★ 2026-11-25 改：纯时长比在「裁停顿」场景是错的尺子。
        #   c2_0372 现役 7.70s（117wpm，43% 是停顿）裁后 5.22s ⇒ 比值 0.68 报 FAIL，
        #   但裁后 15 词 / 5.22s = 172wpm 才是健康的。所以改成用 wpm 判：
        #   120~220 都算正常语速（省略号/破折号允许偏慢），超范围才拦。
        import re as _re
        # ★ 同一个坑第三次了：剧本用 U+2019(’) 当撇号，正则只认 ASCII ' 时
        #   somebody’s → somebody（少 1 词）、Here’s → Here，wpm 被低估 12%，
        #   9 词句被算成 8 词、109wpm。**先归一撇号再分词**。
        _t = (e.get("text", "").replace("\u2019", "'").replace("\u2018", "'"))
        _nw = len(_re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", _t))
        wpm = (_nw / s["dur"] * 60.0) if s.get("dur") else 0.0
        # 下限只拦「明显拖沓」：c2_0279(109) / c2_0309(118) 都带破折号，
        # 破折号本来就要拖，而且这两条用户是冲着语调选的（不是冲着语速）。
        # 用户关心的是「太快」（>300 像喊），慢一点他没意见。
        if wpm and not (100 <= wpm <= 235):
            bad.append("语速 %.0fwpm" % wpm)
        elif wpm:
            warn.append("%.0fwpm" % wpm)
        if abs(vr + 24) > 1.0:
            bad.append("voicedRMS %.1f" % vr)
        # ★ 不要拿 sep 的绝对值卡阈值：`gate_intra.sep` 是**段内声纹分离度**，
        #   基线 c1_0015 自己就是 0.203、5 个 seed 在 0.14~0.27，全部 PASS。
        #   之前误当相似度卡 0.55，把好条判死。
        # ★ 另外 `intra_unmeasurable` 是「测不了」（片段太短/单段无对比），不是不合格，
        #   4/5 条都落在这个状态；只拦真正判坏的。
        code = gi.get("code") if isinstance(gi, dict) else gv
        if gv != "PASS" and "unmeasurable" not in str(code):
            bad.append("intra:%s" % code)
        verdict = "PASS" if not bad else "FAIL"
        rows.append((rid, verdict, "; ".join(bad) or "tech/flat OK",
                     dict(seed=e["pick"], base=e.get("base"),
                          target=e.get("pick_ratio"), dur=s["dur"], dr=dr,
                          rms=round(vr, 2), floor=round(s["floor_db"], 1),
                          snr=round(s["snr_db"], 1), zero=round(s["zero_ms"], 1),
                          peak=round(s["peak"], 3), sep=sep)))
        print("  %-9s %-4s %s%s" % (rid, verdict, ("⚠%s " % ",".join(warn)) if warn else "", "; ".join(bad) or
                                  "seed%s %s=%.1fx voicedRMS %.1f floor %.1f zero %.0fms"
                                  % (e["pick"], e.get("word", ""),
                                     e.get("pick_ratio") or 0, vr,
                                     s["floor_db"], s["zero_ms"])))

    ok = [x for x in rows if x[1] == "PASS"]
    print("\n通过 %d / %d" % (len(ok), len(rows)))

    if not a.apply:
        print("\n[3/3] 未加 --apply，只体检不写文件")
        return
    if not ok:
        print("\n[3/3] 没有通过的条目，不写")
        return
    os.makedirs(BAK, exist_ok=True)
    print("\n[3/3] 回填")
    for rid, _, _, info in ok:
        src = os.path.join(NRM, "%s.wav" % rid)
        dst = os.path.join(OUTD, "%s.wav" % rid)
        shutil.copy2(dst, os.path.join(BAK, "%s.wav" % rid))
        shutil.copy2(src, dst)
        print("  %-9s 回填  seed%s  dur %.2fs→%.2fs" % (
            rid, info["seed"], D.audio_stats(os.path.join(BAK, "%s.wav" % rid))["dur"],
            info["dur"]))
    json.dump([{"id": r[0], "verdict": r[1], "why": r[2], "info": r[3]} for r in rows],
              open("G:/_setup/_seedpick_apply.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("备份目录 %s\n-> _seedpick_apply.json" % BAK)


if __name__ == "__main__":
    main()
