# -*- coding: utf-8 -*-
"""_excited_ab.py —— Thomas「兴奋」参考档 A/B：从原片找更像兴奋的段，替代 loud。

背景（2026-11-13 17:0x，用户明确否决）：
  当前 Thomas 兴奋 5 条全用 `Thomas_loud_1` 生成 —— **用户不接受**：
  「绝对不能用 loud，音色差别太大，情绪表现也不是同样的」。
  原判 hard_cap（生成层数学上限）建立在 loud 这一个参考上，参考换掉必须重测。

筛选口径（不只看 e2v top-1）：
  e2v 八类把「得意/炫耀」经常判成 angry / neutral，所以按三条一起挑：
    ① e2v 的 happy 概率（哪怕不是 top-1）
    ② F0 相对该角色中位（高唤醒代理）
    ③ **文本语境**——Thomas 兴奋的 5 条是「炫耀所有权 / 我得手了」，不是狂喜
  MOS ≥ 2.2 保底（<2.2 的参考会把音质带崩，c308_p1 就是这个反例）。

输出 `_excited_ab/<cid>.wav`，台账 `_excited_ab_log.json`。
用法：G:/Python310/python.exe _excited_ab.py
"""
import json, os, subprocess, sys

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
HERE = "G:/_setup"
OUT = os.path.join(HERE, "_excited_ab")
TEST_ID = "c2_0264"          # 「When my father dies, this house will belong to me」——炫耀所有权
CAND = ["c314_p0", "c327_p1", "c319_p1", "c172_p2", "c308_p1"]
# 对照组：现役 loud 档（路径与文本都从参考库取，别手写）
LIB = os.path.join(HERE, "_emo_refs_all.json")


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def main():
    os.makedirs(OUT, exist_ok=True)
    meas = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"),
                                                 encoding="utf-8"))}
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
    text = plan[TEST_ID].get("text_src") or plan[TEST_ID]["text"]
    print("试句 %s（%d 词）：%s" % (TEST_ID, len(text.split()), text[:80]), flush=True)

    jobs = []
    for c in CAND:
        r = meas.get(c)
        if not r:
            print("缺测量 %s" % c); continue
        jobs.append((c, os.path.join(HERE, "_refs_new/cand", c + ".wav"), r.get("text") or ""))
    _loud = (json.load(open(LIB, encoding="utf-8"))["Thomas"]["loud"])[0]
    jobs.append(("loud_baseline", _loud["path"], _loud.get("text") or ""))
    for tag, ref, rtext in jobs:
        if not os.path.exists(ref):
            print("%-14s 参考不存在 %s" % (tag, ref), flush=True); continue
        out = os.path.join(OUT, tag + "_" + TEST_ID + ".wav")
        if os.path.exists(out) and os.path.getsize(out) > 50000:
            print("%-14s 已存在，跳过" % tag, flush=True); continue
        cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
               "--backend", "vulkan", "--threads", "6",
               "--voice-ref", ref, "--reference-text", rtext or "",
               "--text", text, "--seed", "42", "--out", out,
               "--request-option", "max_tokens=%d" % mtok(len(text.split())),
               "--session-option", "dots_tts.mem_saver=true", "--metrics"]
        try:
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=1800)
        except subprocess.TimeoutExpired:
            print("%-14s 超时" % tag, flush=True); continue
        ok = os.path.exists(out) and os.path.getsize(out) > 50000
        print("%-14s %s" % (tag, "OK" if ok else "FAIL"), flush=True)

    # ── 评测：情绪分 / 声纹 / MOS / 语速
    import soundfile as sf
    import ser as S
    import _nat_guard as NG
    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))
    rows = []
    for tag, _, _ in jobs:
        p = os.path.join(OUT, tag + "_" + TEST_ID + ".wav")
        if not os.path.exists(p):
            continue
        sc = e2v.score(p) or {}
        d = sf.info(p).duration
        w = len([k for k in text.split() if any(ch.isalpha() for ch in k)])
        rows.append(dict(tag=tag, happy=round(float(sc.get("开心/happy", 0)), 4),
                         top=sc.get("_top"), mos=round(float((NG.raw(p) or {}).get("nq_mos") or 0), 2),
                         dur=round(d, 2), wpm=round(w / d * 60) if d else 0,
                         path=p))
        print("%-14s happy %.4f  top %-14s MOS %.2f  %.2fs %3dwpm"
              % (tag, rows[-1]["happy"], rows[-1]["top"], rows[-1]["mos"], d, rows[-1]["wpm"]),
              flush=True)
    json.dump(rows, open(os.path.join(HERE, "_excited_ab_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
