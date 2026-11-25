# -*- coding: utf-8 -*-
"""_regen_pool.py —— 给一条台词多生成若干 take，只负责「出音频」。

为什么要单独一个脚本：
  用户的判断是「语调是模型随机做的，多生成几次就能同时拿到好语调和干净咬字」。
  所以问题不是「哪个 seed」，而是**候选池够不够大**。这个脚本只做生成，
  筛选交给 _pool_rank.py（语调 + 塞音清晰度 + 闸门）。

用法：
  python _regen_pool.py --id c3_0853 --seeds 50-61 --out G:/_setup/_seedpick2
"""
import argparse
import json
import os
import subprocess
import sys

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

sys.path.insert(0, "G:/_setup")
import _paths as P            # noqa: E402
import _pause_gap as PG       # noqa: E402

REF_DIR = "G:/_setup/_refs_v3"


def parse_seeds(s):
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def mtok(text, bonus=150):
    """与 _regen9 / _seed_pick_batch 同一公式：按词数估，短句不许给 760。"""
    n = len(text.split())
    return max(200, min(900, int(n * 12 + 120) + bonus))


def resolve_ref(voice):
    if not voice:
        return None
    p = os.path.join(REF_DIR, voice + ".wav")
    if os.path.exists(p):
        return p
    import re
    p = os.path.join(REF_DIR, re.sub(r"_\d+$", "", voice) + ".wav")
    return p if os.path.exists(p) else None


def gen(text, ref, out, seed):
    cmd = [P.ACPP, "--task", "tts", "--family", "dots_tts", "--model", P.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % mtok(text),
           "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, cwd=P.ACPP_DIR, capture_output=True, text=True, timeout=1800)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--seeds", default="50-61")
    ap.add_argument("--out", default="G:/_setup/_seedpick2")
    ap.add_argument("--ref", default="")
    a = ap.parse_args()

    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
    text = PG.clean(rows[a.id]["text"])
    voice = ""
    for l in open("G:/_setup/_castle_en_ch123_plan_v4.jsonl", encoding="utf-8"):
        d = json.loads(l)
        if d.get("id") == a.id:
            voice = d.get("voice", "")
            break
    ref = a.ref or resolve_ref(voice)
    if not ref:
        print("找不到参考音频 voice=%r" % voice)
        return 2

    d = os.path.join(a.out, a.id)
    os.makedirs(d, exist_ok=True)
    print("id=%s  voice=%s  ref=%s" % (a.id, voice, os.path.basename(ref)))
    print("text=%r" % text)
    print("max_tokens=%d  词数=%d" % (mtok(text), len(text.split())))

    seeds = parse_seeds(a.seeds)
    for sd in seeds:
        p = os.path.join(d, "s%d.wav" % sd)
        if os.path.exists(p) and os.path.getsize(p) > 10000:
            print("  seed %-3d 已存在，跳过" % sd)
            continue
        rc = gen(text, ref, p, sd)
        ok = os.path.exists(p) and os.path.getsize(p) > 10000
        print("  seed %-3d rc=%s %s" % (sd, rc, "OK" if ok else "FAIL"))
        sys.stdout.flush()
    print("->", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
