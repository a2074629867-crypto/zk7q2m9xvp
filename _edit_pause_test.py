# -*- coding: utf-8 -*-
"""_edit_pause_test.py —— 验证「edit 模板 + <pause act="ins" level=N/>」能不能原生插停顿

背景
  交付版 `_regen_final` 的停顿是**后期切音频**叠上去的（`_run_pause_1123.py`）：
  TTS 自己给的 0.24s + 注入 0.74s ⇒ 接缝处容易听出撕裂，且末句没标点就一次不插。
  用户 11-25 08:2x：「Edit 引擎，就是能原生插停顿的。」

  依据（本项目已验过的两条）：
  1. `DOTS_MARKUP_RULES.md` §一：`<pause act="ins"/>` 标准 XML → 模型方言
     `<pause act="ins" level="2"/>`；`pause` 会自动打开 xvector ⇒ 音色来自 `source_audio`。
  2. `_adv_edit.py`（2026-11 实测）：本地 CLI 走
     `--task tts --request-option template_name=edit --source-audio ... --request-option use_xvector=on`
     可以真正跑 edit（产物时长 4.96 → 4.48s，标签生效）。

本脚本只回答一个问题：**level 1/2/3 各插出多少秒，插在哪，其余词有没有被改坏。**

条件（同句、同源、同 seed，只改 level）
    base  不加标签（控制：验证 edit 复刻源音频）
    l1/l2/l3  comma 后插 <pause act="ins" level="N"/>

用法：
    G:/Python310/python.exe _edit_pause_test.py --sid c3_0948
    G:/Python310/python.exe _edit_pause_test.py --sid c3_0948 --levels 0,1,2,3 --seed 42
"""
import argparse
import json
import os
import shutil
import subprocess
import time

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/_setup/cloud/ref/ref.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
OUT = os.path.join(ROOT, "_edit_pause")
LOG = os.path.join(ROOT, "_edit_pause.log")
STEPS = 8
THREADS = 2
TIMEOUT = 900


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- 文本：从 plan 取带标点原文，槽位用 pause_llm_narr_v3 的目标位置 ----------
def load_text(sid):
    for fn in ("_narr_plan_for_pause.jsonl", "_castle_en_ch123_plan_v4.jsonl"):
        p = os.path.join(ROOT, fn)
        if not os.path.exists(p):
            continue
        for l in open(p, encoding="utf-8"):
            r = json.loads(l)
            if r.get("id") == sid:
                return r["text"]
    raise SystemExit("找不到 %s 的文本" % sid)


def slots(sid):
    p = os.path.join(ROOT, "pause_llm_narr_v3.json")
    d = json.load(open(p, encoding="utf-8")).get(sid) or {}
    return {int(k): v for k, v in d.items()}


def build_ins(text, level, slot_idx, act="ins"):
    """在「第 slot_idx 个 token 之后」插 pause 标签。token 用空白切，标点粘在前词上。

    level 传 "r1"/"r2"/"r3" 时 act=red（减少），否则 act=ins（插入）。
    """
    toks = text.split()
    if not (0 <= slot_idx < len(toks)):
        return text
    head = " ".join(toks[: slot_idx + 1])
    tail = " ".join(toks[slot_idx + 1:])
    lv, act = level, act
    if isinstance(level, str) and level[:1] in ("d", "D"):      # d3 = 两个 ins3 并联
        n = int(lv[1:])
        return "%s %s %s" % (head, ("<pause act=\"ins\" level=\"%d\"/> " % n) * 2, tail)
    if isinstance(level, str) and level[:1] in ("r", "R"):
        act, lv = "red", int(level[1:])
    if int(lv) <= 0:
        return text
    return '%s <pause act="%s" level="%d"/> %s' % (head, act, int(lv), tail)


# ---------- 调用 ----------
def run_edit(text_plain, ins, src, seed, dst):
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(dst) and sf.info(dst).duration > 0.3:
        log("  跳过已存在 %s (%.2fs)" % (os.path.basename(dst), sf.info(dst).duration))
        return dst
    tmp = os.path.join(ROOT, "_tmp_edit_pause")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    outw = os.path.join(tmp, "o.wav")
    mt = min(600, max(220, int(len(text_plain.split()) * 26 + 200)))
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", str(THREADS),
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--request-option", "template_name=edit",
           "--source-audio", src,
           "--request-option", "source_text=" + text_plain,
           "--request-option", "target_text=" + text_plain,
           "--request-option", "use_xvector=on",
           "--text", ins,
           "--out", outw,
           "--request-option", "seed=%d" % seed,
           "--request-option", "max_tokens=%d" % mt,
           "--num-inference-steps", str(STEPS),
           "--session-option", "dots_tts.mem_saver=true",
           "--metrics"]
    log("  → %s" % os.path.basename(dst))
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=TIMEOUT)
        out = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        out = "TIMEOUT"
    el = time.time() - t0
    ok = os.path.exists(outw) and sf.info(outw).duration > 0.3
    if ok:
        shutil.copy2(outw, dst)
        log("    ok %.2fs 用时%.0fs" % (sf.info(dst).duration, el))
    else:
        log("    FAIL 用时%.0fs" % el)
        for ln in out.strip().splitlines()[-8:]:
            log("      " + ln[:200])
    shutil.rmtree(tmp, ignore_errors=True)
    return dst if ok else None


# ---------- 测量 ----------
def gaps(path, minlen=0.15):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    hop = int(sr * 0.02)
    n = len(y) // hop
    e = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) + 1e-12 for i in range(n)])
    db = 20 * np.log10(e)
    thr = max(np.percentile(db, 90) - 20, -60)
    sil = db < thr
    out = []
    i = 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            d = (j - i) * 0.02
            if d >= minlen and i > 3 and j < n - 3:
                out.append((round(i * 0.02, 2), round(d, 2)))
            i = j
        else:
            i += 1
    return len(y) / sr, out, float(db[~sil].mean()) if (~sil).any() else -60


def seam_jump(path, g):
    """每个静音洞的出入口 20ms 内，采样级最大跳变 / 局部 RMS（>3 就有可听 click）"""
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    vals = []
    for st, d in g:
        for t in (st, st + d):
            k = int(t * sr)
            if 400 < k < len(y) - 400:
                loc = np.sqrt(np.mean(y[k - 400:k + 400] ** 2)) + 1e-9
                vals.append(float(np.max(np.abs(np.diff(y[k - 200:k + 200]))) / loc))
    return max(vals) if vals else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sid", default="c3_0948")
    ap.add_argument("--levels", default="0,1,2,3")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--src", default="", help="默认 _regen_1123_norm/<sid>.wav")
    a = ap.parse_args()

    text = load_text(a.sid)
    sl = slots(a.sid)
    slot_idx = min(sl) if sl else None
    if slot_idx is None:
        raise SystemExit("%s 在 pause_llm_narr_v3.json 里没有槽位" % a.sid)
    target = sl[slot_idx]

    src = a.src or os.path.join(ROOT, "_regen_1123_norm", a.sid + ".wav")
    sdur, sg, slv = gaps(src)
    log("源 %s  %.2fs  内部停顿 %s  voiced均值%.1fdB" % (os.path.basename(src), sdur, sg, slv))
    log("槽位：第 %d 个 token 之后（%r）  目标 %.3fs  %s  %s"
        % (slot_idx, text.split()[slot_idx], target["d"], target["kind"], target.get("why", "")))

    rows = []
    for lv in [x.strip() for x in a.levels.split(",") if x.strip()]:
        ins = build_ins(text, lv, slot_idx)
        dst = os.path.join(OUT, "%s_L%s_s%d.wav" % (a.sid, lv, a.seed))
        p = run_edit(text, ins, src, a.seed, dst)
        if not p:
            continue
        d, g, lvl = gaps(p)
        rows.append(dict(level=lv, dur=round(d, 2), gaps=g, voiced_db=round(lvl, 1),
                         seam=round(seam_jump(p, g), 2), path=p))
        log("    dur=%.2fs（源 %.2fs，Δ%+.2fs）  内部停顿 %s  接缝跳变=%.2f"
            % (d, sdur, d - sdur, g, rows[-1]["seam"]))

    json.dump(dict(sid=a.sid, src=src, src_dur=round(sdur, 2), src_gaps=sg,
                   slot=slot_idx, target=target, rows=rows),
              open(os.path.join(ROOT, "_edit_pause_%s.json" % a.sid), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)
    log("写出 _edit_pause_%s.json" % a.sid)


if __name__ == "__main__":
    main()
