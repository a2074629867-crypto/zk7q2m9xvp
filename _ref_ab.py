# -*- coding: utf-8 -*-
"""_ref_ab.py —— 参考音 A/B：换档有没有用、48k 与 16k 差在哪。

三个变体跑同一句、同 seed：
  old  现用档（16k 老切片）
  n48  新切 48k
  n16  同一段内容降成 16k（隔离「格式」变量）
比较：输出自然度 / 时长 / F0 / 声纹（vs 该角色中心）/ 情绪 top-1
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
OUT = "G:/_setup/_ab_out"
HERE = "G:/_setup"

CASE = {
    "id": sys.argv[1] if len(sys.argv) > 1 else "c2_0246",
    "who": sys.argv[2] if len(sys.argv) > 2 else "Charles",
    "old_tier": sys.argv[3] if len(sys.argv) > 3 else "nervous",
    "new_cid": sys.argv[4] if len(sys.argv) > 4 else "c030_p0",
}
CASE["old_ref"] = "G:/_setup/_cloud_backup/voice_lib/%s_%s_1.wav" % (CASE["who"], CASE["old_tier"])


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def gen(text, ref, rtext, out, seed=42):
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rtext or "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % mtok(len(text.split())),
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ACPP_DIR, timeout=900)
    o = (r.stdout or "") + (r.stderr or "")
    dur = None
    for ln in o.splitlines():
        if "audio_duration_ms=" in ln:
            try:
                dur = float(ln.split("=")[1]) / 1000.0
            except Exception:
                pass
    return (os.path.exists(out) and os.path.getsize(out) > 50000), dur


def main():
    os.makedirs(OUT, exist_ok=True)
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
    lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
    meas = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"),
                                                encoding="utf-8"))}
    p = plan[CASE["id"]]
    text = p.get("text_src") or p["text"]
    print("句:", CASE["id"], p["who"], p["emo"], "|", text, flush=True)

    # 旧档参考文本
    old = lib[CASE["who"]][CASE["old_tier"]][0]
    old_rtext = old.get("text") or ""
    new = meas[CASE["new_cid"]]
    print("旧参考 %s" % os.path.basename(CASE["old_ref"]), flush=True)
    print("新参考 %s  %.1fs  MOS %.2f  F0 %.0f | %s"
          % (CASE["new_cid"], new["dur"], new["mos"], new["f0"], new["text"]), flush=True)

    # 16k twin
    y, sr = sf.read(os.path.join(HERE, "_refs_new/cand", CASE["new_cid"] + ".wav"),
                    dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    import parselmouth
    y16 = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr).resample(16000)
    p16 = os.path.join(OUT, "_ref16.wav")
    sf.write(p16, np.asarray(y16.values).ravel(), 16000, subtype="PCM_16")

    variants = [
        ("old", CASE["old_ref"], old_rtext),
        ("n48", os.path.join(HERE, "_refs_new/cand", CASE["new_cid"] + ".wav"), new["text"]),
        ("n16", p16, new["text"]),
    ]
    res = {}
    for tag, ref, rt in variants:
        out = os.path.join(OUT, "%s_%s.wav" % (CASE["id"], tag))
        ok, dur = gen(text, ref, rt, out)
        print("  %-4s %s dur=%s" % (tag, "OK" if ok else "FAIL", dur), flush=True)
        res[tag] = out if ok else None

    # 评估
    from _mut_all import M, to16, fbank
    import ser as S
    import _nat_guard as NG

    def nrm(v):
        return v / (np.linalg.norm(v) + 1e-9)

    m = M("r34")
    import glob
    import collections
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

    print()
    print("%-5s %5s %5s %6s %8s %8s %-12s %5s" %
          ("变体", "时长", "F0", "vsCharles", "vsThomas", "MOS", "情绪top1", "p"))
    for tag in ("old", "n48", "n16"):
        f = res[tag]
        if not f:
            print("%-5s FAIL" % tag)
            continue
        y, sr = sf.read(f, dtype="float32", always_2d=True)
        y = y.mean(axis=1)
        d = len(y) / sr
        snd = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr)
        pit = snd.to_pitch_ac(0.01, 60, 600).selected_array["frequency"]
        pit = pit[pit > 0]
        f0 = float(np.median(pit)) if len(pit) else 0
        e = nrm(m.emb_f(fbank(to16(f), m.cmn)))
        sc = e2v.score(f) or {}
        mos = NG.raw(f).get("nq_mos")
        print("%-5s %5.2f %5.0f %6.3f %8.3f %8.2f %-12s %5.2f" %
              (tag, d, f0, float(e @ cen["Charles"]), float(e @ cen["Thomas"]),
               mos or 0, (sc.get("_top") or "-")[:12], sc.get(sc.get("_top"), 0)), flush=True)


if __name__ == "__main__":
    main()
