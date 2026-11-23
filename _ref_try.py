# -*- coding: utf-8 -*-
"""_ref_try.py —— 换档快速验证：只生成「新参考」一条，跟**已交付音频**比。

与 `_ref_ab.py` 的区别：不重跑 old/n16 两个变体（已交付音频本身就是 old 基线），
每条只花 1 次生成 ⇒ 一档一验的成本从 ~3 分钟降到 ~1 分钟。

用法：
  python _ref_try.py c3_0875 Thomas c286_p2 Thomas_wary_2
"""
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
HERE = "G:/_setup"
OUT = os.path.join(HERE, "_ref_try")


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def gen(text, ref, rtext, out, seed=42):
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--voice-ref", ref, "--reference-text", rtext or "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % mtok(len(text.split())),
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=ACPP_DIR, timeout=1200)
    return os.path.exists(out) and os.path.getsize(out) > 50000


def main():
    sid, role, cid = sys.argv[1], sys.argv[2], sys.argv[3]
    tier = sys.argv[4] if len(sys.argv) > 4 else cid
    os.makedirs(OUT, exist_ok=True)

    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
    meas = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"),
                                               encoding="utf-8"))}
    gate = {x["id"]: x for x in json.load(open(os.path.join(HERE, "_gate_dlg_v20.json"),
                                               encoding="utf-8"))}
    p = plan[sid]
    new = meas[cid]
    print("句 %s  %s/%s  现用档 %s  时长 %.2fs" %
          (sid, p["who"], p["emo"], p["voice"],
           sf.info(os.path.join(HERE, "_audio_ch123/out", sid + ".wav")).duration), flush=True)
    print("新参考 %s (%s)  %.2fs MOS %.2f F0 %.0f | %s" %
          (cid, tier, new["dur"], new["mos"], new["f0"], new["text"]), flush=True)

    text = p.get("text_src") or p["text"]
    out = os.path.join(OUT, "%s_%s.wav" % (sid, tier))
    ok = gen(text, os.path.join(HERE, "_refs_new/cand", cid + ".wav"), new["text"], out)
    print("生成 %s -> %s" % ("OK" if ok else "FAIL", out), flush=True)
    if not ok:
        return

    # ---- 测量 ----
    from _mut_all import M, to16, fbank
    import ser as S
    import _nat_guard as NG
    import glob
    import collections
    import parselmouth

    def nrm(v):
        return v / (np.linalg.norm(v) + 1e-9)

    m = M("r34")
    E = {}
    for f in sorted(glob.glob(os.path.join(HERE, "_cloud_backup/voice_lib/*.wav"))):
        k = os.path.basename(f)[:-4]
        if k.startswith(("Thomas_begging", "Thomas_nervous_2", "Charles_soft_3")):
            continue
        E[k] = nrm(m.emb_f(fbank(to16(f), m.cmn)))
    G = collections.defaultdict(list)
    for k, e in E.items():
        G[k.split("_")[0]].append(e)
    cen = {r: nrm(np.mean(v, 0)) for r, v in G.items()}
    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))
    st = NG.load_stat("dlg")

    def probe(f):
        y, sr = sf.read(f, dtype="float32", always_2d=True)
        y = y.mean(axis=1)
        snd = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr)
        pit = snd.to_pitch_ac(0.01, 60, 600).selected_array["frequency"]
        pit = pit[pit > 0]
        e = nrm(m.emb_f(fbank(to16(f), m.cmn)))
        sc = e2v.score(f) or {}
        r = NG.verdict(f, domain="dlg")
        return dict(dur=len(y) / sr, f0=float(np.median(pit)) if len(pit) else 0,
                    cos=float(e @ cen[role]),
                    mos=(r.get("raw") or {}).get("nq_mos"),
                    score=r.get("score"), verdict=r.get("verdict"),
                    top=(sc.get("_top") or "-"), tp=sc.get(sc.get("_top"), 0))

    old_f = os.path.join(HERE, "_audio_ch123/out", sid + ".wav")
    a, b = probe(old_f), probe(out)
    g = gate[sid]
    print("\n%-6s %6s %6s %8s %7s %7s %-12s" %
          ("变体", "时长", "F0", "vs" + role, "MOS", "自然度σ", "情绪top1"))
    for tag, r in (("旧", a), ("新", b)):
        print("%-6s %6.2f %6.0f %8.3f %7.2f %7.2f %-12s" %
              (tag, r["dur"], r["f0"], r["cos"], r["mos"] or 0, r["score"] or 0, r["top"][:10]))
    print("\n旧: 声纹闸 %s / 情绪闸 %s / 自然度闸 %s" %
          (g["gates"].get("speaker"), g["gates"].get("emotion"), g["gates"].get("nat")))
    print("新: 声纹 cos %.3f / 自然度 %s (%.2fσ) / 情绪 %s" %
          (b["cos"], b["verdict"], b["score"] or 0, b["top"]))


if __name__ == "__main__":
    main()
