# -*- coding: utf-8 -*-
"""finish_r5.py —— 第五轮重生成收尾（Charles 紧张 13 + 激动反抗 8，换 48k 新参考）。

与 r3 的差别：多一条「自然度必须不变差」硬闸 —— 换参考的目的是提质量，
不能闸门过了、MOS 掉了也照收。判据：new_mos >= old_mos - 0.15（容 0.15 测量噪声）。

与 finish_r2.py 的差别：
  1) 多一个 --norm：候选先归一到 voiced RMS −24dBFS（与全库同口径），再进闸。
     r2 当时是回填后才整库归一，结果新条目在闸里的电平是原始电平，和库里不可比。
  2) 备份目录独立（out_bak_r3_1112），不覆盖 r2 的备份 —— 那批备份是回滚依据。

用法（顺序固定）：
  G:/Python310/python.exe finish_r5.py --norm
  G:/Python310/python.exe finish_r5.py --plan-only
  G:/Python310/python.exe dialog_gate.py --plan _dlg_plan_r5_cand.jsonl \
      --lib _emo_refs_all.json --bg-map @_bg_map.json --out G:/_setup/_gate_r5_cand.json
  G:/Python310/python.exe finish_r5.py --gate _gate_r5_cand.json
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from norm_dlg import vdb, soft_clip  # 同一把尺子，不许另写一套
import _nat_guard as NG      # 只在 --gate 里用，用于「不变差」硬闸

ACPP_PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
DLG_PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
R3 = "G:/_setup/_regen_r5.json"
R3_OUT = "G:/_setup/_regen_r5_out"
OUT = "G:/_setup/_audio_ch123/out"
BAK = "G:/_setup/_audio_ch123/out_bak_r5_1112"
CAND_PLAN = "G:/_setup/_dlg_plan_r5_cand.jsonl"
OK_JSON = "G:/_setup/_backfill_r5_ok.json"
LOG = "G:/_setup/_backfill_r5_log.json"
NORM_LOG = "G:/_setup/_norm_r5_log.json"

TARGET = -24.0
PEAK_MAX = 0.891
GAIN_LIMIT = 20.0
RATIO_LO, RATIO_HI = 0.65, 1.55
# ★ r5 不用比值闸：这一轮换的就是「产出语速明显偏慢」的档（旧 nervous_1 实测 65~93 wpm），
#   比值必然 <0.65，用它会把全部正解都拒掉。改判**绝对语速**：
#   英文对白正常区间取 90~260 wpm（项目既有 _wpm_r3 口径），越界才拒。
WPM_LO, WPM_HI = 90.0, 260.0


def wpm_of(i, dur):
    t = (src_texts().get(i) or {}).get("text") or ""
    t = t.replace("\u2018", " ").replace("\u2019", "'")
    w = len([k for k in t.split() if any(c.isalpha() for c in k)])
    return (w / dur * 60.0) if dur > 0 else 0.0


def todo():
    return json.load(open(R3, encoding="utf-8"))


def src_texts():
    d = {}
    for line in open(ACPP_PLAN, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            d[r["id"]] = r
    return d


def cmd_norm(dry=False):
    rows, miss = [], []
    for r in todo():
        i = r["id"]
        p = os.path.join(R3_OUT, i + ".wav")
        if not os.path.exists(p):
            miss.append(i)
            continue
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        r0 = vdb(y, sr)
        gain = TARGET - r0
        if abs(gain) > GAIN_LIMIT:
            rows.append(dict(id=i, rms0=round(r0, 2), gain=round(gain, 2), rms1=None,
                             peak=round(float(np.abs(y).max()), 3), clip=False,
                             note="超 ±%ddB 未处理" % GAIN_LIMIT))
            continue
        y1 = y * (10 ** (gain / 20.0))
        pk = float(np.abs(y1).max())
        clip = False
        if pk > PEAK_MAX:
            y1 = soft_clip(y1, PEAK_MAX)
            clip = True
        r1 = vdb(y1, sr)
        rows.append(dict(id=i, rms0=round(r0, 2), gain=round(gain, 2), rms1=round(r1, 2),
                         peak=round(float(np.abs(y1).max()), 3), clip=clip, note=""))
        if not dry:
            sf.write(p, y1.astype(np.float32), sr, subtype="PCM_16")
    ok = [r for r in rows if r["rms1"] is not None]
    print("归一 %d 条 / 缺 %d 条" % (len(ok), len(miss)), flush=True)
    if ok:
        v = sorted(r["rms1"] for r in ok)
        print("  归一后 voiced RMS：min %.2f  中位 %.2f  max %.2f  跨度 %.2f dB"
              % (v[0], v[len(v) // 2], v[-1], v[-1] - v[0]), flush=True)
        print("  限幅 %d 条 · 峰值最大 %.3f" % (sum(1 for r in ok if r["clip"]),
                                          max(r["peak"] for r in ok)), flush=True)
    bad = [r for r in rows if r["rms1"] is None]
    if bad:
        print("  超增益上限（本身有问题）：%s" % [(r["id"], r["rms0"]) for r in bad], flush=True)
    if miss:
        print("  还没生成：%s" % miss, flush=True)
    json.dump(rows, open(NORM_LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("  台账 -> %s%s" % (NORM_LOG, "（dry 未写盘）" if dry else ""), flush=True)


def cmd_plan():
    src = src_texts()
    out, miss = [], []
    for r in todo():
        i = r["id"]
        p = os.path.join(R3_OUT, i + ".wav")
        if not os.path.exists(p) or i not in src:
            miss.append(i)
            continue
        out.append({"path": p, "who": r.get("role") or src[i].get("speaker"),
                    "emo": r["emo"], "id": i, "voice": r["voice"],
                    "text": src[i]["text"]})
    with open(CAND_PLAN, "w", encoding="utf-8", newline="\n") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print("候选清单 %d 条 -> %s" % (len(out), CAND_PLAN), flush=True)
    if miss:
        print("  缺 %d 条: %s" % (len(miss), miss), flush=True)


def cmd_gate(gate_json, allow=()):
    """allow：闸门判 REGEN 但仍要回填的 id（须附理由，写进台账）。

    唯一用到它的场景：「警惕」的 emo_low —— 该判据（e2v disgusted）已被证伪
    （DECISIONS「emo type 一刀切」，两条参考 0.0006→0.0004），
    对它的 REGEN 等于用坏尺子判死刑。回填后音频与 plan 一致，
    复检里保留 REGEN 标记，等 §8.3 重标映射后再判。
    """
    src = src_texts()
    todos = {r["id"]: r for r in todo()}
    gate = {r["id"]: r for r in json.load(open(gate_json, encoding="utf-8"))}
    os.makedirs(BAK, exist_ok=True)

    acc, rej = [], []
    for i, g in gate.items():
        new = os.path.join(R3_OUT, i + ".wav")
        old = os.path.join(OUT, i + ".wav")
        if not (os.path.exists(new) and os.path.exists(old)):
            rej.append((i, "文件缺"))
            continue
        d1, d2 = sf.info(old).duration, sf.info(new).duration
        ratio = d2 / d1 if d1 > 0 else 0
        y, _ = sf.read(new, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        pk = float(np.abs(y).max())
        bad = []
        if g["verdict"] == "REGEN" and i not in allow:
            bad.append("闸门REGEN")
        wn = wpm_of(i, d2)
        if not (WPM_LO <= wn <= WPM_HI):
            bad.append("语速%.0fwpm(新)" % wn)
        if pk >= 0.999:
            bad.append("削波%.3f" % pk)
        # ★ 换参考的目的是提质量：闸门过了但 MOS 掉了，说明这个新档对这句不适用
        #   （A/B 是单条证据，不能保证整档都受益）⇒ 拒收，保留旧音频。
        m_old = (NG.raw(old) or {}).get("nq_mos")
        m_new = (NG.raw(new) or {}).get("nq_mos")
        if m_old is not None and m_new is not None and m_new < m_old - 0.15:
            bad.append("MOS降 %.2f->%.2f" % (m_old, m_new))
        mos_delta = (round(m_new - m_old, 2)
                     if (m_old is not None and m_new is not None) else None)
        if bad:
            rej.append((i, " ".join(bad)))
        else:
            acc.append({"id": i, "verdict": g["verdict"], "ratio": round(ratio, 2),
                        "voice": todos[i]["voice"], "emo": todos[i]["emo"],
                        "dur_old": round(d1, 2), "dur_new": round(d2, 2),
                        "wpm_new": round(wn), "wpm_old": round(wpm_of(i, d1)),
                        "mos_old": round(m_old, 2) if m_old is not None else None,
                        "mos_new": round(m_new, 2) if m_new is not None else None,
                        "mos_delta": mos_delta,
                        "override": ("REGEN→回填:%s" % ",".join(
                            r["code"] for r in g.get("reasons", []))
                            if g["verdict"] == "REGEN" and i in allow else "")})

    print("通过双闸 %d 条 / 拒绝 %d 条" % (len(acc), len(rej)), flush=True)
    import collections
    print("  通过里判决:", dict(collections.Counter(x["verdict"] for x in acc)), flush=True)
    if rej:
        print("  拒绝:", rej, flush=True)

    log = []
    for x in acc:
        i = x["id"]
        new = os.path.join(R3_OUT, i + ".wav")
        old = os.path.join(OUT, i + ".wav")
        bp = os.path.join(BAK, i + ".wav")
        if not os.path.exists(bp):          # 不覆盖 r2/归一前的备份
            shutil.copy2(old, bp)
        shutil.copy2(new, old)
        log.append(dict(x, action="replaced", backup=bp,
                        at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # plan 的 voice 以本清单为准（复检要按实际生成档判 ref_emo）
    plan = {}
    for line in open(DLG_PLAN, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            plan[r["id"]] = r
    vmap = {x["id"]: x["voice"] for x in acc}
    for i, v in vmap.items():
        if i in plan:
            plan[i]["voice"] = v
    with open(DLG_PLAN, "w", encoding="utf-8", newline="\n") as f:
        for r in plan.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    json.dump(acc, open(OK_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    oldlog = []
    if os.path.exists(LOG):
        oldlog = json.load(open(LOG, encoding="utf-8"))
    json.dump(oldlog + log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n回填 %d 条，plan voice 同步 %d 条" % (len(log), len(vmap)), flush=True)
    print("台账 %s  备份 %s" % (LOG, BAK), flush=True)

    import hashlib
    bad = [x["id"] for x in log
           if hashlib.md5(open(os.path.join(OUT, x["id"] + ".wav"), "rb").read()).hexdigest()
           != hashlib.md5(open(os.path.join(R3_OUT, x["id"] + ".wav"), "rb").read()).hexdigest()]
    print("落盘校验不一致:", bad if bad else "无 ✓", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--norm", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--gate", default="")
    ap.add_argument("--allow", default="", help="闸门判 REGEN 仍回填的 id，逗号分隔")
    a = ap.parse_args()
    if a.norm:
        cmd_norm(a.dry)
    elif a.plan_only:
        cmd_plan()
    elif a.gate:
        cmd_gate(a.gate, set(x.strip() for x in a.allow.split(",") if x.strip()))
    else:
        ap.error("给 --norm / --plan-only / --gate")


if __name__ == "__main__":
    main()
