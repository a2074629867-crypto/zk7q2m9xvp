# -*- coding: utf-8 -*-
"""_excited_ab2.py —— Thomas「兴奋」参考置换 A/B（第二版，修正试句与指标）。

第一版两个错（2026-11-13 17:2x，写下来别再犯）：
  1. **试句选错**：用 `c2_0264` 做基准，而它连现役 loud 产物的 e2v happy 都是 0.000
     （top=angry 1.000）——拿最不像兴奋的一条当尺子，任何参考都会被判死。
  2. **指标搞错**：情绪闸里走 e2v 的只有「警惕」一个档；兴奋用的是 vox 的 `a_x_v`
     （arousal×valence）。我拿 e2v happy 当兴奋分，测的根本不是闸在用的东西。

本版：
  试句 = `c2_0491`（「This is my father's room, this is my spare room…」炫耀式，
    现役 loud 产物 e2v happy 0.555 / a_x_v 0.169 —— 五条里最接近兴奋的一条）
  指标 = `a_x_v`（闸口径，p25 0.3745 / p10 0.2470）+ e2v happy（听感旁证）+ MOS + 语速
  对照 = 现役 loud 产物（`_audio_ch123/out/c2_0491.wav`），不再重复生成

用法：G:/Python310/python.exe _excited_ab2.py
"""
import json, os, subprocess, sys

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
HERE = "G:/_setup"
OUT = os.path.join(HERE, "_excited_ab3")
TEST_ID = "c2_0491"
# 五个候选：happy 概率 × F0 × 语境（得意/炫耀/兴致）三条一起挑，MOS≥2.2 保底
CAND = ["c312_p0", "c207_p0", "c216_p0", "c093_p0", "c292_p0"]
CUR = os.path.join(HERE, "_audio_ch123/out", TEST_ID + ".wav")


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def main():
    os.makedirs(OUT, exist_ok=True)
    meas = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"),
                                                 encoding="utf-8"))}
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
    text = plan[TEST_ID].get("text_src") or plan[TEST_ID]["text"]
    print("试句 %s（%d 词）" % (TEST_ID, len(text.split())), flush=True)

    for c in CAND:
        r = meas.get(c)
        if not r:
            print("缺测量 %s" % c); continue
        ref = os.path.join(HERE, "_refs_new/cand", c + ".wav")
        out = os.path.join(OUT, c + ".wav")
        if os.path.exists(out) and os.path.getsize(out) > 50000:
            print("%-10s 已存在" % c, flush=True); continue
        if not os.path.exists(ref):
            print("%-10s 参考缺失" % c); continue
        cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
               "--backend", "vulkan", "--threads", "6",
               "--voice-ref", ref, "--reference-text", r.get("text") or "",
               "--text", text, "--seed", "42", "--out", out,
               "--request-option", "max_tokens=%d" % mtok(len(text.split())),
               "--session-option", "dots_tts.mem_saver=true", "--metrics"]
        try:
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=1800)
        except subprocess.TimeoutExpired:
            print("%-10s 超时" % c, flush=True); continue
        ok = os.path.exists(out) and os.path.getsize(out) > 50000
        print("%-10s %s" % (c, "OK" if ok else "FAIL"), flush=True)

    # ── 评测（三把尺：闸口径 a_x_v / 听感 happy / 音质 MOS）
    import soundfile as sf
    import ser as S
    import verdict as V
    import _nat_guard as NG
    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))
    vox = S.VoxDim()
    rows = []
    items = [("现役(loud)", CUR)] + [(c, os.path.join(OUT, c + ".wav")) for c in CAND]
    for tag, p in items:
        if not os.path.exists(p):
            print("%-12s 缺失" % tag); continue
        sc = e2v.score(p) or {}
        vs = vox.score(p) or {}
        av = V.vox_feat(vs, "a_x_v")
        d = sf.info(p).duration
        w = len([k for k in text.split() if any(ch.isalpha() for ch in k)])
        rows.append(dict(tag=tag, a_x_v=round(av, 4), happy=round(float(sc.get("开心/happy", 0)), 4),
                         top=sc.get("_top"), A=round(float(vs.get("arousal", 0)), 3),
                         Vv=round(float(vs.get("valence", 0)), 3),
                         mos=round(float((NG.raw(p) or {}).get("nq_mos") or 0), 2),
                         dur=round(d, 2), wpm=round(w / d * 60) if d else 0))
        print("%-12s a_x_v %.3f  happy %.3f  A %.2f V %.2f  MOS %.2f  %.1fs %3dwpm  top %s"
              % (tag, rows[-1]["a_x_v"], rows[-1]["happy"], rows[-1]["A"], rows[-1]["Vv"],
                 rows[-1]["mos"], d, rows[-1]["wpm"], rows[-1]["top"]), flush=True)
    json.dump(rows, open(os.path.join(HERE, "_excited_ab3_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n闸口径：兴奋 p25 0.3745 / p10 0.2470（a_x_v）", flush=True)


if __name__ == "__main__":
    main()
