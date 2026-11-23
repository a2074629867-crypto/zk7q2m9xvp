# -*- coding: utf-8 -*-
"""regen_narr.py —— 旁白重生成（只跑物理闸判 FIX 的那几条）。

链路与现有 716 条保持一致：
    生成（纯文本 + seed，不用 <rate> 标签）
    → trim 首尾静音（HEAD 0.06 / TAIL 0.10，与 narr_post 同值）
    → tempe 伸缩（rate 来自 plan，夹 [0.70, 1.00]）
    → 按**能量平均** voiced RMS 归一到 −24dBFS + 峰值 ≤ 0.891

为什么不用 `narr_post.py` 的 `CL.clean`：它的 `RB.rms_voiced_db` 是算术平均 dB
（名字带 rms 但没做均方根），用它归一出来的「−24」实际能量平均约 −18dBFS，
与现有 716 条的实测中位 −24.2 不是同一把尺子。见 DECISIONS 同名条。

用法：
  python regen_narr.py --ids c1_0181,c3_0706 --dry
  python regen_narr.py --ids c1_0181,c3_0706
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db  # noqa: E402
import ch123_rebuild as RB             # noqa: E402

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/_setup/cloud/ref/ref.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
OUT = "G:/_setup/_regen_narr_out"
LOG = "G:/_setup/_regen_narr_1111.jsonl"
FF = "E:/tool/oopz/ffmpeg.exe"
SR = 48000
HEAD, TAIL = 0.06, 0.10
TARGET = -24.0
PEAK_MAX = 0.891
TEMPO_FLOOR, TEMPO_MAX = 0.70, 1.00


def mtok(words):
    return max(120, min(900, int(words * 12 + 150)))


def load(p):
    x, sr = sf.read(p, dtype="float64", always_2d=True)
    x = x.mean(1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = np.gcd(int(sr), SR)
        x = resample_poly(x, SR // g, sr // g)
    return x.astype(np.float32)


def trim(a, sr):
    segs = RB.split_at_silence(a, sr, min_gap=0.10)
    if not segs:
        return a
    s0 = max(0.0, segs[0][0] - HEAD)
    s1 = min(len(a) / sr, segs[-1][1] + TAIL)
    return a[int(s0 * sr):int(s1 * sr)]


def stretch(a, sr, tempo, tag):
    tmp = "G:/_setup/_tmp_regen_narr"
    os.makedirs(tmp, exist_ok=True)
    src = os.path.join(tmp, "%s_in.wav" % tag)
    dst = os.path.join(tmp, "%s_out.wav" % tag)
    sf.write(src, a, sr, subtype="PCM_16")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-af", "rubberband=tempo=%.4f:pitchq=quality" % tempo,
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)
    return load(dst)


def call_tts(text, out, seed=42, mt=400):
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % mt,
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    r = subprocess.run(cmd, cwd=ACPP_DIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--plan", default=PLAN,
                    help="默认旧 plan（0.76~0.83）；读标注 rate 用 _castle_en_ch123_plan_v2.jsonl")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--stress", default=None,
                    help="stress_tts_narr.json（stress_ann2tts.py 产出）。给定时用带标签文本生成；"
                         "整句 tempo<1.0 的句子自动跳过标签（避免双重减速）")
    ap.add_argument("--seed", type=int, default=42,
                    help="生成 seed。回环抽 seed 时用（默认 42，与全库一致）")
    ap.add_argument("--log", default=LOG, help="记录 jsonl 路径")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(a.plan, encoding="utf-8") if l.strip()}
    ids = [x.strip() for x in a.ids.split(",") if x.strip()]

    stress_map = {}
    if a.stress:
        _d = json.load(open(a.stress, encoding="utf-8"))
        stress_map = _d.get("items", _d)
        print("stress 表 %d 句（%s）" % (len(stress_map), os.path.basename(a.stress)))

    for k in ids:
        p = plan.get(k)
        if not p:
            print("%-9s plan 里没有" % k)
            continue
        text = p["text"]
        words = len(text.split())
        rate = float(p.get("rate") or 0.8)
        tempo = max(TEMPO_FLOOR, min(TEMPO_MAX, rate))
        mt = mtok(words)

        # ---- stress 词级标签（STRESS_PLAYBOOK §2.4）----
        # 两条硬约束在这里落地：
        #   1. 整句 tempo<1.0 = 已经走"慢读"这条路，再叠词级 <rate> 会双重减速
        #      （0.70 × 0.8 = 0.56），音色也会变 ⇒ 两者互斥，优先整句慢读。
        #   2. 句末词用 <pitch>，只在 --task tts 下有效 —— 本脚本正是 tts，成立。
        st = stress_map.get(k) or {}
        tags = st.get("tags") or []
        gen_text, st_used, st_note = text, 0, ""
        if tags:
            if abs(tempo - 1.0) <= 0.02:
                gen_text = st.get("model") or text
                st_used = len(tags)
                st_note = "  stress=%d" % st_used
                mt += 40 * st_used          # 标签本身要吃 token
            else:
                st_note = "  stress=0(整句 rate %.2f，不叠加)" % tempo
        dst = os.path.join(a.out, k + ".wav")
        print("%-9s %2d 词  rate=%.2f  mt=%d%s  %s"
              % (k, words, rate, mt, st_note, gen_text[:46]))
        if a.dry:
            continue

        raw = os.path.join(a.out, "_raw_%s.wav" % k)
        t0 = time.time()
        rc, txt = call_tts(gen_text, raw, seed=a.seed, mt=mt)
        if rc != 0 or not os.path.exists(raw):
            print("           生成失败 rc=%s %s" % (rc, txt[-160:]))
            continue
        y = load(raw)
        y = trim(y, SR)
        if abs(tempo - 1.0) > 0.02:
            y = stretch(y, SR, tempo, k)
        lv0, _, _ = voiced_db(y, SR)
        y = y * (10 ** ((TARGET - lv0) / 20.0))
        pk = float(np.abs(y).max())
        rollback = False
        if pk > PEAK_MAX:
            y = y * (PEAK_MAX / pk)
            rollback = True
        sf.write(dst, y.astype(np.float32), SR, subtype="PCM_16")
        y2 = load(dst)
        lv1, _, _ = voiced_db(y2, SR)
        pk1 = float(np.abs(y2).max())
        rec = dict(id=k, words=words, rate=rate, tempo=round(tempo, 3), mt=mt,
                   seed=a.seed,
                   stress_used=st_used, stress_tags=len(tags),
                   dur=round(len(y2) / SR, 2), lvl_before=round(lv0, 2),
                   lvl_after=round(lv1, 2), peak=round(pk1, 3),
                   peak_rollback=rollback, sec=round(time.time() - t0, 1),
                   out=dst, ref=REF)
        open(a.log, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("           %.2fs  %.1f→%.1f dBFS  峰值 %.3f%s  %.0fs"
              % (rec["dur"], lv0, lv1, pk1, "  [峰值回退]" if rollback else "", rec["sec"]))
        try:
            os.remove(raw)
        except OSError:
            pass


if __name__ == "__main__":
    main()
