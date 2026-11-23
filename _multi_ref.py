# -*- coding: utf-8 -*-
"""_multi_ref.py —— 薄档补了 2 条参考后，同句多参考生成 + 择优。

背景：5 个薄档原来各只有 1 条参考，导致两类复发问题
  ① Thomas_defiant_1 换档后声纹降级（Charles 余弦上升，c1_0052/c2_0468 被拒）
  ② 警惕同参考不同 seed 双峰（0.9996 ↔ 0.0004）
补到 3 条后不再死磕单条，改成「同句换参考各生成一条，按闸口径择优」。

流程（一条命令跑完）：
  1. 每个 (id, voice) 生成到 `_mref_out/<id>__<voice>.wav`（已存在则跳过）
  2. 归一到 −24dBFS（**先归一再评测**，否则 MOS 被电平左右）
  3. 评测：主信号（闸在用的那个）+ 声纹 cos（对本角色质心）+ e2v + MOS
  4. 择优：满足「主信号 ≥ p10 且 MOS ≥ 2.0」里取 MOS 最高；都不过 p10 则取主信号最高
  5. 胜者复制到 `_regen_r10_out/<id>.wav`，台账 `_multi_ref_log.json`

用法：python _multi_ref.py            # 跑全部
      python _multi_ref.py c1_0052    # 只跑某条
"""
import json, os, shutil, subprocess, sys
import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
from norm_dlg import vdb, soft_clip

HERE = "G:/_setup"
ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = os.path.join(HERE, "_emo_refs_all.json")
PLAN = os.path.join(HERE, "_dlg_plan_v2.jsonl")
MREF = os.path.join(HERE, "_mref_out")
NORM = os.path.join(HERE, "_mref_norm")
OUT = os.path.join(HERE, "_regen_r10_out")
TARGET, PEAK_MAX = -24.0, 0.891

# id -> 主信号档（闸口径）与候选 voice
JOBS = {
    "c1_0052": ("激动反抗", ["Thomas_defiant_2", "Thomas_defiant_3"]),
    "c2_0468": ("激动反抗", ["Thomas_defiant_2", "Thomas_defiant_3"]),
    "c2_0210": ("警惕",     ["Thomas_wary_2", "Thomas_wary_3"]),
    "c2_0324": ("警惕",     ["Thomas_wary_2", "Thomas_wary_3"]),
    "c3_0637": ("警惕",     ["Thomas_wary_2", "Thomas_wary_3"]),
    "c2_0487": ("警惕",     ["Charles_wary_2", "Charles_wary_3"]),
}


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def resolve(lib, voice):
    head, n = voice.rsplit("_", 1)
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    n = int(n)
    if 1 <= n <= len(items):
        it = items[n - 1]
        return (it.get("path"), it.get("text") or "") if isinstance(it, dict) else (it, "")
    return None, None


def gen(lib, plan, i, voice):
    p = os.path.join(MREF, "%s__%s.wav" % (i, voice))
    if os.path.exists(p) and os.path.getsize(p) > 50000:
        return p, "skip"
    ref, rtext = resolve(lib, voice)
    if not ref or not os.path.exists(ref):
        return None, "参考解析失败"
    text = plan[i].get("text_src") or plan[i]["text"]
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--voice-ref", ref, "--reference-text", rtext or "",
           "--text", text, "--seed", "42", "--out", p,
           "--request-option", "max_tokens=%d" % mtok(len(text.split())),
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    try:
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ACPP_DIR, timeout=900)
    except subprocess.TimeoutExpired:
        return None, "超时"
    if os.path.exists(p) and os.path.getsize(p) > 50000:
        return p, "ok"
    return None, "生成失败"


def normalize(src, dst):
    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    g = TARGET - vdb(y, sr)
    y = y * (10 ** (g / 20.0))
    if float(np.abs(y).max()) > PEAK_MAX:
        y = soft_clip(y, PEAK_MAX)
    sf.write(dst, y.astype(np.float32), sr, subtype="PCM_16")
    return round(float(vdb(y, sr)), 2), round(float(np.abs(y).max()), 3)


def main():
    for d in (MREF, NORM, OUT):
        os.makedirs(d, exist_ok=True)
    lib = json.load(open(LIB, encoding="utf-8"))
    plan = {json.loads(l)["id"]: json.loads(l) for l in open(PLAN, encoding="utf-8") if l.strip()}
    only = {a for a in sys.argv[1:] if not a.startswith("--")}
    score_only = "--score-only" in sys.argv

    import ser as S
    import verdict as V
    import dialog_gate as DG
    import _nat_guard as NG
    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))
    VOX = S.VoxDim()
    stats = DG.load_ref_stats()
    PRIMARY = {"警惕": ("e2v", "厌恶/disgusted"), "激动反抗": ("vox", "d"),
               "委屈": ("vox", "neg_a"), "兴奋": ("vox", "a_x_v")}

    # 角色质心（r34，交付音频）
    d = np.load(os.path.join(HERE, "_utt_emb/r34.npz"), allow_pickle=True)
    whos, embs = d["whos"], d["embs"]
    cent = {}
    for who in set(whos.tolist()):
        v = embs[whos == who]
        v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
        c = v.mean(0)
        cent[who] = c / (np.linalg.norm(c) + 1e-9)
    from _mut_all import M
    from _utt_verify import utt_emb
    spk = M("r34")

    # 1) 生成
    todo = [i for i in JOBS if not only or i in only]
    for i in ([] if score_only else todo):
        emo, voices = JOBS[i]
        for v in voices:
            p, st = gen(lib, plan, i, v)
            print("  gen %-8s %-20s %s" % (i, v, st), flush=True)

    # 2) 归一 + 3) 评测
    rows = []
    for i in todo:
        emo, voices = JOBS[i]
        kind, key = PRIMARY[emo]
        p10 = stats[emo]["signals"]["%s:%s" % (kind, key)]["pos"]["p10"]
        p25 = stats[emo]["signals"]["%s:%s" % (kind, key)]["pos"]["p25"]
        cands = []
        # 现役交付音频也参评（作为「不改」的基准，同电平比较）
        cur = os.path.join(HERE, "_audio_ch123/out", i + ".wav")
        if os.path.exists(cur):
            cands.append(("cur", cur))
        for v in voices:
            p = os.path.join(MREF, "%s__%s.wav" % (i, v))
            if os.path.exists(p):
                cands.append((v, p))
        scored = []
        for tag, p in cands:
            npth = os.path.join(NORM, "%s__%s.wav" % (i, tag))
            rms1, pk = normalize(p, npth)
            sc = e2v.score(npth) or {}
            vs = VOX.score(npth) or {}
            val = (float(sc.get(key, 0)) if kind == "e2v" else float(V.vox_feat(vs, key)))
            if kind == "vox":
                try:
                    val = float(V.vox_feat(vs, key))
                except Exception:
                    val = 0.0
            vv = utt_emb(spk, npth)
            vv = vv / (np.linalg.norm(vv) + 1e-9)
            cos = float(vv @ cent[plan[i]["who"]])
            mos = float((NG.raw(npth) or {}).get("nq_mos") or 0)
            dur = sf.info(npth).duration
            scored.append(dict(tag=tag, path=p, norm=npth, val=round(val, 4),
                               cos=round(cos, 3), mos=round(mos, 2),
                               rms=round(rms1, 2), peak=pk, dur=round(dur, 2)))
        # 3.5) 硬闸：时长/语速。★ 2026-11-13 18:35 补 —— 前两版只比主信号与 MOS，
        #   于是选出「情绪对但话没说完」的候选（c2_0468 8.96s→4.64s = 285wpm；
        #   c1_0052 2.48s→1.44s = ratio 0.58）。变短就是截断风险，无条件排除。
        d_old = sf.info(os.path.join(HERE, "_audio_ch123/out", i + ".wav")).duration \
            if os.path.exists(os.path.join(HERE, "_audio_ch123/out", i + ".wav")) else 0
        wc = len([k for k in (plan[i].get("text") or "").split() if any(ch.isalpha() for ch in k)])
        for x in scored:
            bad = []
            if x["peak"] >= 0.999:
                bad.append("削波")
            if x["mos"] < 2.0:
                bad.append("MOS%.2f" % x["mos"])
            if x["cos"] < 0.55:
                bad.append("cos%.2f" % x["cos"])
            if d_old > 0:
                ratio = x["dur"] / d_old
                wpm = wc / x["dur"] * 60 if x["dur"] > 0 else 0
                if wc <= 9:
                    if ratio < 0.75:
                        bad.append("短句变短x%.2f" % ratio)
                    elif ratio > 1.40 and wpm < 120:
                        bad.append("短句变长且%.0fwpm" % wpm)
                elif not (90 <= wpm <= 260):
                    bad.append("%.0fwpm" % wpm)
            x["bad"] = bad

        # 4) 择优（只在过硬闸的候选里选）
        clean = [x for x in scored if not x["bad"]]
        if not clean:
            best = next(x for x in scored if x["tag"] == "cur")
            why = "全部候选过硬闸失败→保留原文件"
        else:
            good = [x for x in clean if x["val"] >= p10]
            if good:
                best = max(good, key=lambda x: (x["mos"], x["val"], x["cos"]))
                why = "双过(p10+硬闸)"
            else:
                best = max(clean, key=lambda x: (x["val"], x["mos"]))
                why = "无达p10→取主信号最高(过硬闸)"
        tier = "到位" if best["val"] >= p25 else ("勉强" if best["val"] >= p10 else "未达")
        if best["tag"] != "cur":
            shutil.copy2(best["norm"], os.path.join(OUT, i + ".wav"))
        rows.append(dict(id=i, emo=emo, win=best["tag"], val=best["val"], cos=best["cos"],
                         mos=best["mos"], tier=tier, why=why, p10=round(p10, 4),
                         p25=round(p25, 4), detail=scored))
        print("%-8s %-6s 胜 %-18s %s %.4f (p10 %.4f/p25 %.4f) cos %.3f MOS %.2f  [%s]"
              % (i, emo, best["tag"], ("%.4f" % best["val"]), best["val"], p10, p25,
                 best["cos"], best["mos"], why), flush=True)
        for x in scored:
            print("      %-20s %s=%.4f cos %.3f MOS %.2f %.2fs %s%s" % (
                x["tag"], key, x["val"], x["cos"], x["mos"], x["dur"],
                "←胜" if x["tag"] == best["tag"] else "",
                ("  拒:" + ",".join(x["bad"])) if x.get("bad") else ""), flush=True)

    json.dump(rows, open(os.path.join(HERE, "_multi_ref_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n台账 -> _multi_ref_log.json；胜者已落 _regen_r10_out/")


if __name__ == "__main__":
    main()
