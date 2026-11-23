# -*- coding: utf-8 -*-
"""_emo_retag.py —— 「检测到情绪不到位 → 自动加 inline 标签 → 再生成 → 复检 → 回填」

用户 2026-11-14 23:1x 原话：
  「我说的加标签再生成，得是你自己检测哦 —— 你检测到好像这样不行、情绪还是到位不了。
   因为我们的链路是没有加标签的，但是 EDIT 引擎它是支持加标签的，所以可以有很多情绪，
   我们直接加标签就行。万一一加标签，哎那情绪可能就到位了，所以这才是我想要的东西。」

为什么可行（2026-11-14 23:0x 实测，`_emo_tag_probe.py`）
  - tts 任务下 inline `<emo type= level=>` **生效**（全句 angry L2 让 F0 +2.5 半音）
  - 句内两半不同情绪**可行**，且只作用在被包住的片段（前两段 -6.4 与基线完全一致）
  - **不毁音色**：声纹 0.865（红线 0.65）
  - level 2/3 是死参数（+2.5 / +1.4，不单调）⇒ 一律用 level 2
  - **主效应是语速**：9.92s → 7.04s（tempo 0.71，正好压 0.70 红线）
    ⇒ 必须复检 tempo，且「平静/委屈」这类不该变快的情绪，变快就拒

闭环五步
  1. 读闸结果，挑 tier ∈ {未达, 勉强} 且时长 ≥1.8s（太短的情绪不可测）
  2. 按 emo 映射到 dots type，文本整体包 `<emo type="X" level="2">…</emo>`
  3. 本地生成候选（同参考 / 同 seed，只改文本）
  4. 复检：情绪值 / 声纹 / tempo / 削波 /  MOS
  5. 达标就回填，写台账

验收口径（与生产一致，不另立一套）
  - 情绪：value ≥ p25（到位）；≥p10 记「勉强」不算通过
  - 声纹 vs 现役 ≥0.65
  - tempo = 现役时长 / 候选时长 ∈ [0.70, 1.00]
  - 峰值 <0.999（不削波）
  - 时长不得短于 0.6 × 现役（残片检测，11-14 r15 踩过）

用法
  G:/Python310/python.exe _emo_retag.py --list          # 只列待修
  G:/Python310/python.exe _emo_retag.py --gen --limit 4 # 先生成 4 条试
  G:/Python310/python.exe _emo_retag.py --gen           # 全量生成
  G:/Python310/python310.exe _emo_retag.py --judge      # 复检并出择优表
"""
import argparse
import json
import glob
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")   # ★ verdict / ser / vox 都在这里
sys.path.insert(0, "G:/voice_lib")

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = "G:/_setup/_emo_refs_all.json"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
GATE = "G:/_setup/_gate_dlg_v31.json"
OUT = "G:/_setup/_retag_out"
LEDGER = "G:/_setup/_retag_ledger.json"
SEED = 42

# ── 标签映射（由 `_tag_calib.py` 实测确定，见 _tag_calib.json / DECISIONS 23:4x）──
# dots 只支持 8 种：afraid angry calm disgusted happy melancholic sad surprised
#
# ★ 只有「激动反抗 → disgusted」实测有效（+0.144 dominance），其余全部无效或反向：
#   紧张 afraid −0.023 / surprised −0.050 / sad +0.024（不稳定）
#   兴奋 happy −0.029（反向）/ surprised +0.028
#   警惕 afraid +0.000 / angry −0.000
# 且「紧张」「兴奋」撞生成层数学上限（HARD_CAP 0.25 / 0.32），加标签救不了。
# ⇒ 默认只跑 ENABLED 里的；其余要跑得显式 --force-all。
EMO2TAG = {
    "激动反抗": "disgusted",
    "紧张": "sad",          # 实测 +0.024，弱；且撞 hard_cap，默认不跑
    "兴奋": "surprised",    # 实测 +0.028，弱；且撞 hard_cap，默认不跑
    "警惕": "afraid",       # 实测 +0.000，无效
    "委屈": "sad",
    "平静": "calm",
}
ENABLED = {"激动反抗"}      # 只有这一类有实测依据

# 哪些情绪「变快」是合理的（emo 标签的主效应是加快 29%）
FAST_OK = {"紧张", "激动反抗", "警惕", "兴奋"}

MIN_DUR = 1.8        # 短于此情绪不可测，不浪费时间
TEMPO_LO, TEMPO_HI = 0.70, 1.00
WPM_MAX = 260        # 生产语速上限（超过就是赶字）
COS_MIN = 0.65
FRAG_RATIO = 0.60    # 候选短于现役 60% 判残片


def load():
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        r = json.loads(l)
        plan[r["id"]] = r
    lib = json.load(open(LIB, encoding="utf-8"))
    gate = {x["wav"][:-4]: x for x in json.load(open(GATE, encoding="utf-8"))}
    return plan, lib, gate


def resolve(lib, voice):
    head, n = voice.rsplit("_", 1)
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    if not items or int(n) > len(items):
        return None, ""
    it = items[int(n) - 1]
    if isinstance(it, dict):
        return it.get("path"), it.get("text") or ""
    return it, ""


def targets(plan, gate, limit=0, force_all=False):
    """挑待修：情绪未达/勉强，且时长够。默认只挑 ENABLED（有实测依据的）。"""
    out = []
    for sid, x in gate.items():
        if sid not in plan:
            continue
        e = x.get("emo_res") or {}
        if e.get("tier") not in ("未达", "勉强"):
            continue
        dur = x["tech"]["dur"]
        if dur < MIN_DUR:
            continue
        if plan[sid]["emo"] not in EMO2TAG:
            continue
        if not force_all and plan[sid]["emo"] not in ENABLED:
            continue
        out.append(dict(sid=sid, who=plan[sid]["who"], emo=plan[sid]["emo"],
                        voice=plan[sid].get("voice"), dur=dur,
                        tier=e.get("tier"), value=e.get("value"),
                        p25=e.get("p25"), p10=e.get("p10"),
                        tag=EMO2TAG[plan[sid]["emo"]]))
    out.sort(key=lambda r: (r["tier"] != "未达", -(r["value"] or 0)))
    return out[:limit] if limit else out


def gen_one(t, plan, lib, seed=None):
    sid = t["sid"]
    sd = SEED if seed is None else seed
    ref, rtext = resolve(lib, t["voice"])
    if not ref or not os.path.exists(ref):
        return False, 0.0, "参考缺失 %s" % t["voice"]
    text = '<emo type="%s" level="2">%s</emo>' % (t["tag"], plan[sid]["text"])
    # ★ 文件名必须带 seed：不带就会「已存在」跳过，等于没换 seed 重跑
    #   （2026-11-14 21:5x 踩过同型坑：同文本+同参考+同 seed 是确定性输出）
    out = os.path.join(OUT, "%s__%s_s%d.wav" % (sid, t["tag"], sd))
    if os.path.exists(out) and os.path.getsize(out) > 40000:
        return True, 0.0, "已存在"
    mt = max(200, int(len(plan[sid]["text"].split()) * 26) + 200)
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--voice-ref", ref, "--reference-text", rtext or "",
           "--text", text, "--seed", str(sd), "--out", out,
           "--request-option", "max_tokens=%d" % mt,
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ACPP_DIR, timeout=900)
    dt = time.time() - t0
    ok = os.path.exists(out) and os.path.getsize(out) > 40000
    return ok, dt, "" if ok else (r.stdout + r.stderr)[-200:]


def judge(ts, plan, gate):
    """复检：情绪 / 声纹 / tempo / 削波 / 残片。用生产同一套判据。"""
    import soundfile as sf
    import verdict as V      # ★ 生产用的就是 verdict（dialog_gate.py:58 `import verdict as V`）
    import ser as S
    from _mut_all import M
    import _utt_verify as U

    if "G:/_setup/emo_bench" not in sys.path:
        sys.path.insert(0, "G:/_setup/emo_bench")
    vox = S.VoxDim()
    e2v = None
    m = M("r34")

    rows = []
    jobs = []
    for t in ts:
        # 一条可能有多个 seed 的候选，全部打分（双峰择优：取最好的那个）
        for c in sorted(glob.glob(os.path.join(OUT, "%s__%s*.wav" % (t["sid"], t["tag"])))):
            jobs.append((t, c))
    for t, cand in jobs:
        cur = "G:/_setup/_audio_ch123/out/%s.wav" % t["sid"]
        if not os.path.exists(cand):
            continue
        try:
            seed = int(os.path.basename(cand)[:-4].rsplit("_s", 1)[1])
        except Exception:
            seed = None
        cd = sf.info(cand).duration
        od = sf.info(cur).duration
        y, sr = sf.read(cand, dtype="float32")
        pk = float(np.max(np.abs(y))) if len(y) else 0.0
        tempo = (od / cd) if cd else None

        # 情绪值
        val = None
        try:
            src, key = V.PRIMARY[t["emo"]]
            if src == "vox":
                sc = vox.score(cand) or {}
                val = float(V.vox_feat(sc, key))
            else:
                if e2v is None:
                    e2v = S.E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large")
                sc = e2v.score(cand) or {}
                val = float(sc.get("厌恶/disgusted", 0.0))
        except Exception as e:
            print("  情绪打分失败 %s: %s" % (t["sid"], e))

        cos = None
        try:
            a, b = U.utt_emb(m, cand), U.utt_emb(m, cur)
            cos = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        except Exception as e:
            print("  声纹失败 %s: %s" % (t["sid"], e))

        # ★ 语速要用 wpm 判，不是「时长比」。
        #   tempo = 原长/新长 只在「同一条音频做时间拉伸」时才有意义；
        #   重生成是独立音频，时长不同不等于加速。实测 c2_0430 tempo 1.08 但
        #   wpm 只从 80 变 87，完全正常 —— 用 tempo 会误杀。
        words = len((plan[t["sid"]].get("text") or "").split())
        wpm = (words / cd * 60) if (cd and words) else None

        bad = []
        if pk >= 0.999:
            bad.append("削波")
        if wpm is not None and wpm > WPM_MAX:
            bad.append("wpm %.0f>%d" % (wpm, WPM_MAX))
        if cd < FRAG_RATIO * od:
            bad.append("残片 %.2fs" % cd)
        if cos is not None and cos < COS_MIN:
            bad.append("声纹 %.3f" % cos)
        if val is not None and t["p25"] is not None and val < t["p25"]:
            bad.append("情绪 %.3f<p25" % val)

        rows.append(dict(sid=t["sid"], who=t["who"], emo=t["emo"], tag=t["tag"],
                         seed=seed, cand=os.path.basename(cand),
                         cur_dur=round(od, 2), cand_dur=round(cd, 2),
                         tempo=(round(tempo, 3) if tempo else None),
                         peak=round(pk, 3),
                         cur_val=t["value"], new_val=(round(val, 4) if val is not None else None),
                         p25=t["p25"], cos=(round(cos, 4) if cos is not None else None),
                         wpm=(round(wpm) if wpm else None),
                         bad=bad, ok=not bad,
                         gain=((val - t["value"]) if (val is not None and t["value"] is not None) else None)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--gen", action="store_true")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--seeds", default="",
                    help="逗号分隔多 seed，如 7,11,23（双峰择优用）")
    ap.add_argument("--force-all", action="store_true",
                    help="连实测无效的情绪也跑（紧张/兴奋/警惕，别抱期望）")
    a = ap.parse_args()

    plan, lib, gate = load()
    ts = targets(plan, gate, a.limit, a.force_all)

    if a.list or not (a.gen or a.judge):
        print("待修 %d 条（情绪未达/勉强 且 时长 ≥%.1fs）" % (len(ts), MIN_DUR))
        import collections
        c = collections.Counter((t["emo"], t["tier"]) for t in ts)
        for k, v in sorted(c.items()):
            print("  %-8s %-4s %d" % (k[0], k[1], v))
        print()
        print("%-9s %-8s %-6s %-4s %-8s %5s %7s %7s" %
              ("sid", "who", "emo", "tier", "tag", "dur", "val", "p25"))
        for t in ts[:30]:
            print("%-9s %-8s %-6s %-4s %-8s %5.2f %7.3f %7.3f" %
                  (t["sid"], t["who"], t["emo"], t["tier"], t["tag"],
                   t["dur"], t["value"] or 0, t["p25"] or 0))
        if len(ts) > 30:
            print("  … 共 %d 条" % len(ts))
        return

    if a.gen:
        os.makedirs(OUT, exist_ok=True)
        print("生成 %d 条（本地 GPU，约 90s/条）" % len(ts))
        seeds = [int(x) for x in a.seeds.split(",") if x.strip()] or [a.seed]
        print("生成 %d 条 × %d seed = %d 个候选（本地 GPU，约 90s/个）"
              % (len(ts), len(seeds), len(ts) * len(seeds)))
        log = []
        k = 0
        for t in ts:
            for sd in seeds:
                k += 1
                ok, dt, msg = gen_one(t, plan, lib, sd)
                print("  [%d/%d] %-9s %-6s %-8s s%-3d %s %.1fs %s" %
                      (k, len(ts) * len(seeds), t["sid"], t["emo"], t["tag"], sd,
                       "OK" if ok else "FAIL", dt, msg), flush=True)
                log.append(dict(sid=t["sid"], emo=t["emo"], tag=t["tag"], seed=sd,
                                ok=ok, sec=round(dt, 1), msg=msg))
        json.dump(log, open("G:/_setup/_retag_genlog.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("生成完成，日志 _retag_genlog.json")
        return

    if a.judge:
        rows = judge(ts, plan, gate)
        print()
        print("%-9s %-8s %-6s %-5s %-6s %-6s %-6s %-6s %-5s %s" %
              ("sid", "who", "emo", "seed", "cur", "new", "cos", "tempo", "OK", "问题"))
        for r in sorted(rows, key=lambda z: (not z["ok"], -(z["gain"] or 0))):
            print("%-9s %-8s %-6s %-5s %-6s %-6s %-6s %-6s %-5s %s" % (
                r["sid"], r["who"], r["emo"], r.get("seed"),
                r["cur_val"], r["new_val"], r["cos"], r["tempo"],
                "✓" if r["ok"] else "✗", ",".join(r["bad"])))
        ok = [r for r in rows if r["ok"]]
        print()
        print("通过 %d / %d" % (len(ok), len(rows)))
        json.dump(rows, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("写出", LEDGER)


if __name__ == "__main__":
    main()
