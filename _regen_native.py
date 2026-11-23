# -*- coding: utf-8 -*-
"""_regen_native.py —— 原速重生成（禁止任何波形后期：不降速、不插停顿）

背景（用户 2026-11-20 反馈）：
  「不是说喊，是情绪很激动很快的说话，这是跟紧张完全不同的，另外现在调整过的
    速度又太慢了，中间插入的停顿太明显了，没有呼吸感，停顿太空」

结论：`_rebuild_calm*.py` 的 rubberband 降速 + `_add_breath.py` 的谷内噪声填充
被用户明确否掉。停顿要让模型自己给（文本里放 `...` 触发自然拖音/换气），
不是后期灌静音。

用法：
  G:/Python310/python.exe _regen_native.py --ids c2_0246,c2_0279 --seeds 42,7
  G:/Python310/python.exe _regen_native.py --override c2_0312="A... B... C."
"""
import argparse
import json
import os
import subprocess

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = "G:/_setup/_emo_refs_all.json"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"


def mtok(words):
    return max(120, min(900, int(words * 12 + 120)))


def resolve(lib, voice):
    parts = voice.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None, None
    head, n = parts[0], int(parts[1])
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    if not (1 <= n <= len(items)):
        return None, None
    it = items[n - 1]
    if isinstance(it, dict):
        return it.get("path"), it.get("text") or ""
    return it, ""


def load_plan():
    p = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            x = json.loads(l)
            p[x["id"]] = x
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--seeds", default="42,7")
    ap.add_argument("--out", default="G:/_setup/_sweep/cand52")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--override", default="", help="id=text;id=text")
    ap.add_argument("--tag", default="", help="强制输出标签（单 id 多文本变体时用，避免同名覆盖）")
    ap.add_argument("--ref", default="", help="强制参考 wav（覆盖 plan 的音色档）")
    ap.add_argument("--ref-text", default="", help="强制参考文本")
    a = ap.parse_args()

    ov = {}
    for seg in a.override.split(";"):
        seg = seg.strip()
        if "=" in seg:
            k, v = seg.split("=", 1)
            ov[k.strip()] = v.strip()

    lib = json.load(open(LIB, encoding="utf-8"))
    plan = load_plan()
    os.makedirs(a.out, exist_ok=True)
    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]

    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    ok = fail = 0
    for i in ids:
        row = plan.get(i)
        if not row:
            print("%s NOT_IN_PLAN" % i, flush=True)
            fail += 1
            continue
        ref, rtext = resolve(lib, row["voice"])
        if a.ref:
            ref, rtext = a.ref, (a.ref_text or rtext)
        if not ref or not os.path.exists(ref):
            print("%s NO_REF %s" % (i, row["voice"]), flush=True)
            fail += 1
            continue
        # 原样传：项目主生成器（_seed_sweep）也是原样传 plan.text，
        # 剥掉 ’ 会把 it’s→its、won’t→wont 直接改坏发音。
        text = ov.get(i, row.get("text_src") or row["text"])
        for s in seeds:
            tag = a.tag or (i if i not in ov else i + "x")
            out = os.path.join(a.out, "%s__s%d.wav" % (tag, s))
            if os.path.exists(out) and os.path.getsize(out) > 50000:
                print("%s s%d SKIP" % (tag, s), flush=True)
                ok += 1
                continue
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", str(a.threads),
                   "--voice-ref", ref, "--reference-text", rtext or "",
                   "--text", text, "--seed", str(s), "--out", out,
                   "--request-option", "max_tokens=%d" % mtok(len(text.split())),
                   "--session-option", "dots_tts.mem_saver=true", "--metrics"]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", cwd=ACPP_DIR, timeout=1800)
            except subprocess.TimeoutExpired:
                print("%s s%d TIMEOUT" % (tag, s), flush=True)
                fail += 1
                continue
            good = os.path.exists(out) and os.path.getsize(out) > 50000
            print("%s s%d %s" % (tag, s, "OK" if good else "FAIL"), flush=True)
            ok += 1 if good else 0
            fail += 0 if good else 1
    print("完成 OK %d / 失败 %d" % (ok, fail), flush=True)


if __name__ == "__main__":
    main()
