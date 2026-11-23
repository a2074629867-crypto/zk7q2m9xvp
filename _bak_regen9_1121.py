# -*- coding: utf-8 -*-
"""全库按「角色 × 情绪 9s 参考」重生成。

用户 2026-11-21：
  「我之前让你每个角色每种情绪，参考时间得接近 9s 准一点，你做了没？」
  「9s 参考很好，就是很多字都吞了，很多音没发好」

三件事一起修（前两件是吞字/发音不准的根因，见 DECISIONS.md 02:5x 那条）：
 1. 参考时长 4~5s → 9~14s（`_ref9/`，`_build_ref9.py` + `_topup_ref9.py`）
 2. 参考文本改用 SRT 原文（`_fix_ref9_text.py`）。ASR 猜的文本会让模型照着错的音念。
 3. 参考里不再出现「模型自己听写」的文本残留。

只重生成，不做任何波形后期（不降速、不插停顿、不降噪）—— 用户已明确否掉这些。

用法：
  G:/Python310/python.exe -u _regen9.py --offset 0 --limit 20
  G:/Python310/python.exe -u _regen9.py --ids c2_0246 --seeds 42,7
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

import soundfile as sf

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
ROOT = "G:/_setup"
PLAN = os.path.join(ROOT, "_dlg_plan_v2.jsonl")
IDX = os.path.join(ROOT, "_ref9", "_index_srt.json")

# 用户亲自切、亲自点头的 13.58s 参考：Charles 平静/中性句一律用它。
# 它和 `_ref9/Charles_neutral.wav`（自动拼的 9.87s）不是同一份素材，
# 用户听过并明确说「9s 参考很好」，所以优先级高于自动拼接。
USER_REF = {
    "Charles_neutral": (
        os.path.join(ROOT, "castle_fr_ref", "1_charles_normal.wav"),
        # 这段参考文本是实测比出来的：cand54 用 ASR 猜的文本时 pebble→FEBLE、
        # house→OUSE、they're→A；换成这一版（对照 SRT 句序重写）三条全部恢复。
        "Je suis né comme ça aussi? Vous êtes Monsieur Bréaud? Moi, je suis Charles Vernet. "
        "Non. Ça va mieux, maintenant. Non, monsieur. Et si elle, elle vous aime pas? "
        "Laisse. C'est moi qui t'invite. Je suis encore très riche.",
    ),
}


def mtok(words):
    return max(120, min(900, int(words * 12 + 120)))


def load_plan():
    rows = []
    for l in io.open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            rows.append(json.loads(l))
    return rows


def group_of(voice):
    return (voice or "").rsplit("_", 1)[0]


def ref_for(group, idx):
    if group in USER_REF:
        p, t = USER_REF[group]
        if os.path.exists(p):
            return p, t
    it = idx.get(group)
    if not it:
        return None, None
    return it["file"], it["text"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0, help="0=全部")
    ap.add_argument("--seeds", default="42")
    ap.add_argument("--out", default=os.path.join(ROOT, "_sweep", "cand9"))
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--tag", default="")
    ap.add_argument("--ref", default="", help="强制参考（A/B 试验用）")
    ap.add_argument("--ref-text", default="", help="配合 --ref 的参考文本")
    a = ap.parse_args()

    idx = json.load(io.open(IDX, encoding="utf-8"))
    plan = load_plan()
    if a.ids:
        want = {x.strip() for x in a.ids.split(",") if x.strip()}
        plan = [p for p in plan if p["id"] in want]
    else:
        plan = plan[a.offset: a.offset + a.limit] if a.limit else plan[a.offset:]
    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]
    os.makedirs(a.out, exist_ok=True)

    ok = fail = skip = 0
    t0 = time.time()
    for n, row in enumerate(plan, 1):
        rid = row["id"]
        group = group_of(row.get("voice"))
        ref, rtext = ref_for(group, idx)
        if a.ref:
            ref, rtext = a.ref, (a.ref_text or rtext)
        if not ref or not os.path.exists(ref):
            print("%s NO_REF %s" % (rid, group), flush=True)
            fail += 1
            continue
        text = row.get("text_src") or row["text"]
        for s in seeds:
            tag = a.tag or rid
            out = os.path.join(a.out, "%s__s%d.wav" % (tag, s))
            if os.path.exists(out) and os.path.getsize(out) > 50000:
                skip += 1
                continue
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", str(a.threads),
                   "--voice-ref", ref, "--reference-text", rtext or "",
                   "--text", text, "--seed", str(s), "--out", out,
                   "--request-option", "max_tokens=%d" % mtok(len(text.split())),
                   "--session-option", "dots_tts.mem_saver=true", "--metrics"]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   cwd=ACPP_DIR, timeout=1800)
                err = (r.stderr or "")[-200:]
            except subprocess.TimeoutExpired:
                print("%s s%d TIMEOUT" % (tag, s), flush=True)
                fail += 1
                continue
            good = os.path.exists(out) and os.path.getsize(out) > 50000
            if good:
                d = sf.info(out).duration
                print("[%d/%d %5.1fmin] %s s%d OK %.2fs (ref %s %.1fs)" % (
                    n, len(plan), (time.time() - t0) / 60, tag, s, d,
                    group, sf.info(ref).duration), flush=True)
                ok += 1
            else:
                print("%s s%d FAIL %s" % (tag, s, err), flush=True)
                fail += 1
    print("完成 OK %d / 跳过 %d / 失败 %d  用时 %.1f 分钟" % (
        ok, skip, fail, (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    main()
