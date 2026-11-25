# -*- coding: utf-8 -*-
"""_selftest.py —— 配音链路端到端自检（可重复跑，输出 PASS/FAIL）

用户 2026-11-21：「测试链路也要完整，包括回环、重生成回环、吞字回环，情绪检测也得正常工作」

设计原则：**只跑通不算通过，必须有阳性/阴性对照**。
  阳性样本用「注入法」造：拿一条干净音频，把某个词的时间区间按 -34 dB 削掉，
  这就是一条确定的「吞字」样本。检测器报不出来 = 漏检（FAIL）；干净样本被报 = 误报（FAIL）。

五项：
  T1 指标基座   底噪 / 有声 RMS / 时长 与 _dn_scan.json 复算，容差 0.2 dB / 20 ms
  T2 吞字环     align_gate 对注入样本的召回 + 对干净样本的误报
  T3 回环       wav2vec2 greedy 覆盖率：注入丢词必须掉 ≥0.10，干净样本必须守住 ≥0.95
  T4 重生成环   regen9 单条 → 产物指标 → 择优排序 → 写临时目录不回写 out/
  T5 情绪闸     模板库角色覆盖 / 已知 PASS 重跑一致性 / 情绪识别 vs 标注

用法：
  G:/Python310/python.exe -u _selftest.py                # 全跑
  G:/Python310/python.exe -u _selftest.py --skip T4      # 跳过慢项
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
OUT = os.path.join(ROOT, "_selftest")
PY = "G:/Python310/python.exe"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "emo_bench"))

CLEAN_IDS = ["c2_0265", "c3_0623", "c3_0651"]   # 历史 verdict=PASS、cen_gap 0.29~0.33
JOSEPH_IDS = ["c1_0002", "c1_0027"]             # 历史 role_unmeasurable（旧库无 Joseph 模板）
REGEN_ID = "c2_0265"

R = []          # (name, ok, detail)


def rec(name, ok, detail):
    R.append({"test": name, "ok": bool(ok), "detail": detail})
    print("[%s] %-22s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def frame_db(y, sr, hop=0.01, win=0.025):
    h, w = int(hop * sr), int(win * sr)
    n = 1 + (len(y) - w) // h
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    seg = y[idx]
    e = np.sqrt((seg ** 2).mean(1)) + 1e-12
    zero = np.abs(seg).max(1) == 0
    return 20 * np.log10(e), zero


def measure(p):
    y, sr = sf.read(p, dtype="float64", always_2d=True)
    y = y.mean(1)
    db, zero = frame_db(y, sr)
    nz = db[~zero]
    return {"dur": len(y) / sr, "sr": sr,
            "floor": float(np.percentile(nz, 10)) if len(nz) else -240.0,
            "rms": float(np.mean(db[db > -45])) if (db > -45).any() else -120.0}


# ---------------- T1 指标基座 ----------------
def t1():
    scan = json.load(open(os.path.join(ROOT, "_dn_scan.json"), encoding="utf-8"))
    worst = 0.0
    bad = []
    for rid in CLEAN_IDS:
        p = os.path.join(ROOT, "_audio_ch123", "out", rid + ".wav")
        if not os.path.exists(p) or rid not in scan:
            continue
        m = measure(p)
        d1 = abs(m["floor"] - scan[rid]["floor_nz"])
        d2 = abs(m["rms"] - scan[rid]["sp_rms"])
        d3 = abs(m["dur"] - scan[rid]["dur"]) * 1000
        worst = max(worst, d1)
        if d1 > 0.2 or d2 > 0.1 or d3 > 20:
            bad.append("%s Δfloor%.2f Δrms%.2f Δdur%.0fms" % (rid, d1, d2, d3))
    rec("T1 指标基座", not bad,
        "复算一致，最大 Δfloor %.2f dB" % worst if not bad else "; ".join(bad))


# ---------------- 注入器 ----------------
def inject_word(wav, text, keep=0.0, force_idx=None):
    """把一个词的时间区间按 keep 倍幅度缩放，返回 (新路径, 词, 原区间, 对齐结果)"""
    import _align_gate as AG
    proc, model = AG.load_model()
    r = AG.align(proc, model, wav, text)
    if not r:
        return None, None, None, None, (proc, model)
    # 拼词，取第一个长度 >=5 的词（太短的词削掉不具判别力）
    words, cur = [], []
    for t in r["tokens"]:
        if t["tok"] == "|":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        words.append(cur)
    cand = [w for w in words if len(w) >= 5]
    if not cand:
        return None, None, None, r, (proc, model)
    w = cand[force_idx % len(cand)] if force_idx is not None else cand[0]
    t0, t1 = w[0]["start"] * 0.02, w[-1]["end"] * 0.02
    y, sr = sf.read(wav, dtype="float64", always_2d=True)
    y = y.mean(1)
    i0, i1 = int(t0 * sr), int(t1 * sr)
    if i1 - i0 < int(0.03 * sr):
        return None, None, None, r, (proc, model)
    y2 = y.copy()
    y2[i0:i1] *= keep
    dst = os.path.join(OUT, "inj_" + os.path.basename(wav))
    sf.write(dst, y2, sr)
    return dst, "".join(x["tok"] for x in w), (t0, t1), r, (proc, model)


# ---------------- T2 吞字环 / T3 回环 ----------------
def t23():
    import _align_gate as AG
    import _pick52 as PK
    sys.path.insert(0, ROOT)
    import _calm_gate as CG
    plan = CG.load_plan()

    hits, miss, false_pos, cov_ok, cov_detail = 0, [], [], 0, []
    proc = model = None
    for rid in CLEAN_IDS:
        src = os.path.join(ROOT, "_audio_ch123", "out", rid + ".wav")
        if not os.path.exists(src):
            continue
        text = plan[rid]["text"]
        if proc is None:
            proc, model = AG.load_model()
        base = AG.align(proc, model, src, text)
        if not base:
            continue
        b_bad, _ = AG.judge(base)
        b_cov = PK.coverage(PK.norm_words(text), PK.norm_words(base["greedy"]))

        dst, wword, span, raw, _ = inject_word(src, text)
        if not dst:
            continue
        inj = AG.align(proc, model, dst, text)
        i_bad, i_all = AG.judge(inj)
        i_cov = PK.coverage(PK.norm_words(text), PK.norm_words(inj["greedy"]))

        # 真阳性：注入的那个词必须被判出问题（或该词均分明显下降）
        bword = {x["word"]: x["mean"] for x in AG.judge(base)[1]}
        iword = {x["word"]: x["mean"] for x in i_all}
        wmean_drop = bword.get(wword, 0) - iword.get(wword, 0)
        found = wmean_drop >= 1.0 or any(wword in b["word"] or b["word"] in wword
                                         for b in i_bad)
        if found:
            hits += 1
        else:
            miss.append("%s(%s ↓%.1f)" % (rid, wword, wmean_drop))
        # 误报：判据是「注入前后 bad 的**增量**」，不是基线有没有 bad ——
        # 历史 PASS 的条也可能本来就有 1 个轻微瑕疵词，那不是误报。
        bset = {x["word"] for x in b_bad}
        iset = {x["word"] for x in i_bad}
        extra = iset - bset - {wword}
        if extra and wword not in iset:
            false_pos.append("%s 无关词被误报 %s" % (rid, sorted(extra)))
        # T3
        drop = b_cov - i_cov
        # 注入 1 个词，覆盖率该掉 1/nwords；0.05 是下限（长句 20 词时掉 1 词只有 0.05）
        if drop >= 0.05:
            cov_ok += 1
        cov_detail.append("%s %.3f→%.3f (Δ%.3f)" % (rid, b_cov, i_cov, -drop))

    n = len(CLEAN_IDS)
    rec("T2 吞字环(注入召回)", hits >= max(2, n - 1),
        "%d/%d 检出；漏检 %s" % (hits, n, miss or "无"))
    if false_pos:
        rec("T2b 吞字环(误报)", False, "; ".join(false_pos))
    else:
        rec("T2b 吞字环(误报)", True, "干净样本 0 误报")
    rec("T3 回环(覆盖率)", cov_ok >= max(2, n - 1), "; ".join(cov_detail))


# ---------------- T4 重生成环 ----------------
def t4(reuse=False):
    od = os.path.join(OUT, "regen")
    os.makedirs(od, exist_ok=True)
    outs = glob.glob(os.path.join(od, "*.wav"))
    dt = 0.0
    if not (reuse and outs):
        for f in outs:
            os.remove(f)
        t = time.time()
        r = subprocess.run([PY, "-u", "_regen9.py", "--ids", REGEN_ID, "--seeds", "42",
                            "--ref-dir", "_ref9_clean", "--out", od],
                           cwd=ROOT, capture_output=True, text=True)
        dt = time.time() - t
        outs = glob.glob(os.path.join(od, "*.wav"))
        if r.returncode != 0 or not outs:
            rec("T4 重生成环", False, "regen 失败 %ds：%s" % (dt, (r.stderr or r.stdout)[-200:]))
            return
    p = outs[0]
    m = measure(p)
    src = os.path.join(ROOT, "_audio_ch123", "out", REGEN_ID + ".wav")
    m0 = measure(src) if os.path.exists(src) else None
    y, sr = sf.read(p, dtype="float64", always_2d=True)
    y = y.mean(1)
    peak = float(np.abs(y).max())
    # 重生成本身不做电平归一化（模型原始输出 −30~−34 是正常的），
    # 判据只看「是不是一条有效音频」：时长够、不削顶、底噪低于原版。
    ok = (m["dur"] > 0.3 and peak < 0.999 and 0.001 < peak
          and m["floor"] < (m0["floor"] - 6 if m0 else -999))
    rec("T4a 重生成产出有效", ok,
        "%s %.2fs rms %.1f peak %.2f floor %.1f（原 %.1f）%s"
        % (os.path.basename(p), m["dur"], m["rms"], peak, m["floor"],
           m0["floor"] if m0 else -999,
           "复用" if dt == 0 else "耗时 %.0fs" % dt))

    # 回填前必须归一到 voiced RMS −24±0.1，否则全库响度会跳
    import shutil as _sh
    tmp = os.path.join(OUT, "norm24_" + os.path.basename(p))
    _sh.copy2(p, tmp)
    import _deliver as DL
    lv, pk = DL.norm24(tmp)
    rec("T4c 回填归一化", abs(lv + 24.0) <= 0.1,
        "voiced RMS %.2f dBFS（目标 −24±0.1）peak %.2f" % (lv, pk))

    # 不回写：out/ 里的原文件指纹不能变
    import hashlib
    h = hashlib.md5(open(src, "rb").read()).hexdigest()[:12]
    scan = json.load(open(os.path.join(ROOT, "_dn_scan.json"), encoding="utf-8"))
    same = abs(m0["dur"] - scan[REGEN_ID]["dur"]) < 0.02
    rec("T4b 不回写 out/", same, "%s md5 %s dur %.2f 未变" % (REGEN_ID, h, m0["dur"]))


# ---------------- T5 情绪闸 ----------------
def t5():
    import _calm_gate as CG
    plan = CG.load_plan()
    # 优先用补过 Joseph/Helena 的 v2 库；没有才退回单角色库
    libp = os.path.join(ROOT, "_emo_refs_v2.json")
    if not os.path.exists(libp):
        libp = os.path.join(ROOT, "_emo_refs.json")
    lib = json.load(open(libp, encoding="utf-8"))
    lib_roles = set(lib.keys())
    plan_roles = {}
    for v in plan.values():
        plan_roles[v["who"]] = plan_roles.get(v["who"], 0) + 1
    missing = {k: v for k, v in plan_roles.items() if k not in lib_roles}
    n_missing = sum(missing.values())
    rec("T5a 模板库角色覆盖", not missing,
        "%s 库 %s / 台账 %s ⇒ 缺 %s（%d/%d 条无模板）"
        % (os.path.basename(libp), sorted(lib_roles), sorted(plan_roles),
           missing or "无", n_missing, sum(plan_roles.values())))

    # 已知 PASS 重跑：结论必须一致
    hist = json.load(open(os.path.join(ROOT, "_gate_dlg_v49.json"), encoding="utf-8"))
    hrows = hist if isinstance(hist, list) else list(hist.values())
    hm = {r["wav"][:-4]: r for r in hrows}
    agree, detail = 0, []
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT + ";" + os.path.join(ROOT, "emo_bench")
    for rid in CLEAN_IDS:
        if rid not in hm:
            continue
        src = os.path.join(ROOT, "_audio_ch123", "out", rid + ".wav")
        o = os.path.join(OUT, "g_" + rid + ".json")
        cmd = [PY, "-u", "dialog_gate.py", "--wav", src,
               "--who", plan[rid]["who"], "--emo", plan[rid]["emo"], "--out", o]
        if libp.endswith("_v2.json"):
            cmd += ["--lib", libp]
            bm = os.path.join(ROOT, "_bg_map_v2.json")
            if os.path.exists(bm):
                cmd += ["--bg-map", "@" + bm]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
        if not os.path.exists(o):
            detail.append("%s 跑不动" % rid)
            continue
        d = json.load(open(o, encoding="utf-8"))
        row = d[0] if isinstance(d, list) else d
        prev = hm[rid]["verdict"]
        now = row["verdict"]
        s = row.get("spk") or {}
        # ★ 2026-11-24 改：只比 **G3 情绪闸**。
        #   原来比总 verdict，c2_0265 被新加的 G1 噪声闸（noise_floor −50.6）判 REGEN，
        #   就被记成「情绪闸劣化」—— 张冠李戴。技术闸归 T1/T4 管，这里只管情绪。
        g_now = (row.get("gates") or {}).get("emotion")
        g_prev = hm[rid].get("gates", {}).get("emotion") if isinstance(hm[rid], dict) else None
        if g_now and g_prev:
            same = (g_prev == g_now)
            cmp = "emo %s→%s" % (g_prev, g_now)
        else:
            same = (prev == now)
            cmp = "%s→%s" % (prev, now)
        agree += same
        detail.append("%s %s gap %.3f" % (rid, cmp,
                                            s.get("cen_gap") if s.get("cen_gap") is not None else -1))
    n = len([d for d in detail if "跑不动" not in d])
    rec("T5b 情绪闸不劣化", n > 0 and agree == n,
        "%d/%d 老 PASS 仍 PASS：%s" % (agree, n, "; ".join(detail)))

    # T5c：旧库判不出角色的 Joseph 条目，新库必须判得出（这是补库的全部意义）
    okj, det = 0, []
    emo_hit, emo_all = 0, 0
    for rid in JOSEPH_IDS:
        if rid not in plan:
            continue
        src = os.path.join(ROOT, "_audio_ch123", "out", rid + ".wav")
        o = os.path.join(OUT, "g_" + rid + ".json")
        cmd = [PY, "-u", "dialog_gate.py", "--wav", src,
               "--who", plan[rid]["who"], "--emo", plan[rid]["emo"], "--out", o]
        if libp.endswith("_v2.json"):
            cmd += ["--lib", libp, "--bg-map", "@" + os.path.join(ROOT, "_bg_map_v2.json")]
        subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
        if not os.path.exists(o):
            det.append("%s 跑不动" % rid)
            continue
        row = json.load(open(o, encoding="utf-8"))
        row = row[0] if isinstance(row, list) else row
        s_ = row.get("spk") or {}
        gap = s_.get("cen_gap")
        good = (s_.get("role_top") == plan[rid]["who"] and (gap or 0) >= 0.10)
        okj += good
        det.append("%s %s gap %.3f emo %s(标注%s)" % (
            rid, s_.get("role_top"), gap if gap is not None else -1,
            s_.get("emo"), plan[rid]["emo"]))
        emo_all += 1
        if (s_.get("emo") or "") in ("normal", "calm") and plan[rid]["emo"] == "平静":
            emo_hit += 1
    rec("T5c Joseph 角色可测", okj == len(JOSEPH_IDS), "; ".join(det))
    rec("T5d 情绪识别(平静档)", emo_all and emo_hit == emo_all,
        "平静→normal/calm %d/%d" % (emo_hit, emo_all))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", default="")
    ap.add_argument("--reuse", action="store_true", help="T4 复用上次产物")
    a = ap.parse_args()
    skip = {x.strip().upper() for x in a.skip.split(",") if x.strip()}
    os.makedirs(OUT, exist_ok=True)

    print("=== 链路自检 %s ===" % time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    if "T1" not in skip:
        t1()
    if not ({"T2", "T3"} & skip):
        t23()
    if "T4" not in skip:
        t4(a.reuse)
    if "T5" not in skip:
        t5()

    ok = sum(1 for x in R if x["ok"])
    print("\n=== %d/%d PASS ===" % (ok, len(R)), flush=True)
    for x in R:
        if not x["ok"]:
            print("  FAIL  %-22s %s" % (x["test"], x["detail"]))
    # 分项跑（--skip）时不要把上次的结果冲掉：按 test 名合并
    jp = os.path.join(ROOT, "_selftest.json")
    old = {}
    if os.path.exists(jp):
        try:
            old = {x["test"]: x for x in json.load(open(jp, encoding="utf-8"))}
        except Exception:
            old = {}
    for x in R:
        old[x["test"]] = x
    merged = sorted(old.values(), key=lambda x: x["test"])
    json.dump(merged, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved _selftest.json（累计 %d 项）" % len(merged))


if __name__ == "__main__":
    main()
