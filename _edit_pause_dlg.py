# -*- coding: utf-8 -*-
"""_edit_pause_dlg.py —— 对白：edit 引擎原生插停顿（目标来自 LLM 表）→ 再裁剪到目标

用户口径（2026-11-25 09:17）：
  「最好就走 Edit 引擎原生，但是它停顿出来的肯定会有长有短，我们肯定需要再裁剪一下，
    至于停顿时间要多长，我已经告诉你用 LLM 来裁剪了。」

所以这条链是：
  1) 目标 = `pause_llm_castle.json`（239 条 / 567 槽，src=llm 100%，带 why）
  2) 天然间隙 < 目标 → 用 `<pause act="ins" level=N/>` 让模型自己多停（量子 +0.18/+0.48/+0.78）
  3) 天然间隙 > 目标 → **red 实测不生效**（c1_0174 源 1.06 → L0 1.06、c1_0008 Lr2 1.08 → 1.08），
     只能渲染完再**剪纯静音**到目标
  4) 口吃重复（同一词相邻）不按标点算，一律 ≤200ms（`_pause_gap.gap_kind`）

安全阀：只剪静音核心（`_gapfix.silent_core`），剪不动就保留并记 SKIP；
        末帧补 −72dBFS 底噪、voiced RMS 归 −24（全库口径）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")

import _align_gate as AG     # noqa: E402
import _gapfix as GF         # noqa: E402
import _pause_gap as PG      # noqa: E402
import _dn_uniform as DU     # noqa: E402

ROOT = "G:/_setup"
ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = os.path.join(ROOT, "cloud/ref/ref.wav")
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
OUTD = os.path.join(ROOT, "_audio_ch123/out")
EDITD = os.path.join(ROOT, "_edit_pause_dlg")
NORM_DB = -24.0
TOL = 0.12            # 比目标多出 120ms 以上才剪
QUANTUM = {1: 0.18, 2: 0.48, 3: 0.78}
SEED = 42
STEPS = 8
THREADS = 2
TIMEOUT = 900
LOG = os.path.join(ROOT, "_edit_pause_dlg.log")


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- 文本与槽位 ----------
def load_text(sid):
    rows = {r["id"]: r for r in json.load(open(os.path.join(ROOT, "_dlg_final_v49.json"),
                                               encoding="utf-8"))}
    return PG.clean(rows[sid]["text"])


def load_slots(sid):
    d = json.load(open(os.path.join(ROOT, "pause_llm_castle.json"), encoding="utf-8"))
    return {int(k): v for k, v in (d.get(sid) or {}).items()}


def word_positions(text):
    """返回 {词序号: token 下标}。词序号只数字母词，和 pause_llm_castle 的 key 对齐。"""
    pos, k = {}, 0
    for i, t in enumerate(text.split()):
        if any(ch.isalpha() for ch in t):
            pos[k] = i
            k += 1
    return pos


def build_text(text, slots, natural, idx2tok):
    """按「天然间隙 < 目标」的槽位插 ins 标签；返回 (带标签文本, 计划明细)。"""
    toks = text.split()
    plan = []
    for wi, meta in sorted(slots.items()):
        if wi not in idx2tok:
            continue
        ti = idx2tok[wi]
        if ti >= len(toks) - 1:        # 句末槽位不插（末停顿由收尾保留长度控制）
            continue
        tgt = float(meta["d"])
        nat = natural.get(wi, 0.0)
        need = tgt - nat
        if need <= 0.10:
            plan.append(dict(word=wi, tok=ti, target=tgt, natural=round(nat, 2),
                             act="none", level=0, need=round(need, 2)))
            continue
        lv = min(QUANTUM, key=lambda k: abs(QUANTUM[k] - need))
        plan.append(dict(word=wi, tok=ti, target=tgt, natural=round(nat, 2),
                         act="ins", level=lv, need=round(need, 2)))
    # 从后往前插，避免下标漂移
    for p in sorted(plan, key=lambda x: -x["tok"]):
        if p["act"] != "ins":
            continue
        toks[p["tok"]] = '%s <pause act="ins" level="%d"/>' % (toks[p["tok"]], p["level"])
    return " ".join(toks), plan


# ---------- 测量 ----------
def audible_gap(y, sr, a, b, rel=30.0):
    """听得见的间隔（能量法）。对齐边界会把元音拖尾算进来，虚报约 250ms。"""
    n = int(0.01 * sr)
    seg = y[int(a * sr):int(b * sr)]
    c = len(seg) // n
    if c < 4:
        return 0.0
    db = np.array([20 * np.log10(np.sqrt((seg[i * n:(i + 1) * n] ** 2).mean()) + 1e-12)
                   for i in range(c)])
    thr = np.percentile(db, 85) - rel
    low, best, s0 = db < thr, 0, None
    for i, v in enumerate(low):
        if v and s0 is None:
            s0 = i
        if (not v or i == c - 1) and s0 is not None:
            e = i if not v else i + 1
            best = max(best, e - s0)
            s0 = None
    return best * 0.01


def read(p):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    return y, sr


# ---------- edit 渲染 ----------
def render(sid, text_plain, text_tagged, src, dst):
    if os.path.exists(dst) and sf.info(dst).duration > 0.3:
        log("  复用已存在 %s" % os.path.basename(dst))
        return dst
    os.makedirs(EDITD, exist_ok=True)
    tmp = os.path.join(ROOT, "_tmp_edit_dlg")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    outw = os.path.join(tmp, "o.wav")
    mt = min(900, max(220, int(len(text_plain.split()) * 26 + 220)))
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", str(THREADS),
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--request-option", "template_name=edit",
           "--source-audio", src,
           "--request-option", "source_text=" + text_plain,
           "--request-option", "target_text=" + text_plain,
           "--request-option", "use_xvector=on",
           "--text", text_tagged,
           "--out", outw,
           "--request-option", "seed=%d" % SEED,
           "--request-option", "max_tokens=%d" % mt,
           "--num-inference-steps", str(STEPS),
           "--session-option", "dots_tts.mem_saver=true"]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=TIMEOUT)
        out = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        out, r = "TIMEOUT", None
    el = time.time() - t0
    ok = os.path.exists(outw) and sf.info(outw).duration > 0.3
    if ok:
        shutil.copy2(outw, dst)
        log("  渲染 ok %.2fs 用时%.0fs" % (sf.info(dst).duration, el))
    else:
        log("  渲染 FAIL 用时%.0fs" % el)
        for ln in out.strip().splitlines()[-6:]:
            log("    " + ln[:180])
    shutil.rmtree(tmp, ignore_errors=True)
    return dst if ok else None


# ---------- 裁剪到目标 ----------
def energy_gaps(y, sr, minlen=0.10):
    """纯能量切停顿：返回 [(start, dur), ...]。编辑后的音频不能用对齐边界量 ——
    模型插了停顿，forced_align 会把静音算进前一个词（实测 "yes" 被拉成 2.16s）。"""
    hop = int(0.02 * sr)
    n = len(y) // hop
    db = np.array([20 * np.log10(np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) + 1e-12)
                   for i in range(n)])
    thr = max(np.percentile(db, 90) - 20, -60)
    sil = db < thr
    out, i = [], 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            if (j - i) * 0.02 >= minlen and i > 3 and j < n - 3:
                out.append((i * 0.02, (j - i) * 0.02))
            i = j
        else:
            i += 1
    return out


def boundary_of(gap, spans):
    """定位这个停顿属于第几个词边界：取「结束时间在停顿之后的第一个词」的下标 -1。
    这样即使某个词被拉伸吞掉了静音，也能定位对（比按 end 判断稳）。"""
    g1 = gap[0] + gap[1]
    for i, (w, a, b) in enumerate(spans):
        if a > g1 - 0.02:
            return i - 1
    return None


def trim_to_targets(sid, y, sr, spans, slots, log_rows):
    marks = PG.word_mark_map(PG.clean(load_text(sid)))
    fl = GF.floor_db(y, sr)
    todo = []
    for st, d in energy_gaps(y, sr):
        bi = boundary_of((st, d), spans)
        if bi is None or bi < 0:
            continue
        kind = PG.gap_kind(spans, marks, bi)
        if kind == "stutter":
            target = PG.LIMITS["stutter"] / 1000.0
        elif bi in slots:
            target = float(slots[bi]["d"])
        else:
            target = PG.LIMITS[kind] / 1000.0
        row = dict(word=bi, after=spans[bi][0], kind=kind, at=round(st, 2),
                   target=round(target, 2), measured=round(d, 2))
        log_rows.append(row)
        if d <= target + TOL:
            row["act"] = "keep"
            continue
        core = GF.silent_core(y, sr, st, st + d, fl)
        if not core:
            row["act"] = "no_core"
            continue
        c0, c1, _ = core
        core_ms = (c1 - c0)
        need = min(d - target, core_ms - 0.12)
        if need < 0.06:
            row["act"] = "core_short"
            continue
        todo.append((c0, c1, need, row))
    for c0, c1, need, row in sorted(todo, key=lambda t: -t[0]):
        y, cut = GF.cut_core(y, sr, c0, c1, need)
        row["act"] = "cut"
        row["cut"] = round(cut / sr * 1000)
    return y, sum(r.get("cut", 0) for r in log_rows) / 1000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verify", action="store_true", help="跑 ASR 覆盖 + 接缝 + F0")
    ap.add_argument("--out", default=EDITD)
    ap.add_argument("--plan-only", action="store_true", help="只打印标签方案，不渲染")
    ap.add_argument("--no-edit", action="store_true",
                    help="只按 LLM 目标裁剪现役音频，不重渲染（保留已选定的 take）")
    a = ap.parse_args()

    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    if not ids:
        ids = sorted(json.load(open(os.path.join(ROOT, "pause_llm_castle.json"),
                                    encoding="utf-8")).keys())
        if a.limit:
            ids = ids[:a.limit]
    os.makedirs(a.out, exist_ok=True)
    proc, model = AG.load_model()
    rep = {}

    for sid in ids:
        src = os.path.join(OUTD, sid + ".wav")
        if not os.path.exists(src):
            log("%-9s 缺源" % sid)
            continue
        text = load_text(sid)
        slots = load_slots(sid)
        if not slots:
            log("%-9s LLM 表无槽位，跳过" % sid)
            continue
        # 天然间隙（对源做一次对齐）
        spans0 = PG.align_spans(src, text, proc, model)
        if not spans0:
            log("%-9s 源对齐失败" % sid)
            continue
        y0, sr0 = read(src)
        nat = {i: audible_gap(y0, sr0, spans0[i][2], spans0[i + 1][1])
               for i in range(min(len(spans0) - 1, 40))}
        tagged, plan = build_text(text, slots, nat, word_positions(text))
        if a.plan_only:
            log("%-9s 槽%d 源%.2fs  %s" % (sid, len(slots), len(y0) / sr0, tagged))
            log("         plan=%s" % json.dumps(plan, ensure_ascii=False))
            continue
        log("%-9s 槽 %d · 插标签 %d · 源%.2fs" % (
            sid, len(slots), sum(1 for p in plan if p["act"] == "ins"), len(y0) / sr0))

        raw = os.path.join(EDITD, "%s_edit.wav" % sid)
        if a.no_edit:
            raw = src
        elif not render(sid, text, tagged, src, raw):
            rep[sid] = dict(err="render")
            continue

        y, sr = read(raw)
        spans = PG.align_spans(raw, text, proc, model)
        if not spans:
            rep[sid] = dict(err="align")
            continue
        rows = []
        y, saved = trim_to_targets(sid, y, sr, spans, slots, rows)
        fl = GF.floor_db(y, sr)
        y, _ = GF.trim_edges(y, sr, fl, tail_keep=0.30)
        y = GF.fill_floor(y, sr)
        y = DU.norm_rms(y, sr, NORM_DB)
        pk = float(np.abs(y).max())
        if pk > 0.97:
            y = y * (0.97 / pk)
        dst = os.path.join(a.out, "%s.wav" % sid)
        sf.write(dst, y, sr, subtype="PCM_24")
        rep[sid] = dict(plan=plan, gaps=rows, cut_ms=round(saved * 1000),
                        dur=round(len(y) / sr, 2), peak=round(float(np.abs(y).max()), 2),
                        dst=dst)
        log("  裁剪 %d 处 共%.0fms  → %.2fs" % (sum(1 for r in rows if r.get("act") == "cut"),
                                          saved * 1000, len(y) / sr))

    json.dump(rep, open(os.path.join(ROOT, "_edit_pause_dlg_report.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)
    log("-> %s  %d 条" % (os.path.join(a.out, "*.wav"), len(rep)))


if __name__ == "__main__":
    sys.exit(main())
