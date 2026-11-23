# -*- coding: utf-8 -*-
"""全库双参考竞选：每条台词用「情绪参考」和「角色音色参考」各生成一次，择优。

为什么是两条参考
----------------
2026-11-21 A/B 实测（`_sweep/ab_role`）：

| 台词 | 情绪参考 | 角色音色参考 |
|---|---|---|
| c1_0005 Joseph 紧张 | nervous 9.1s → **w2v_cov 0.83，吞了 "YOU MUST NOT BE"** | normal 13.4s → **1.00，零问题** |
| c1_0020 Thomas 大声 | loud 9.8s → **0.93（HOOPER 念对）** | calm 11.2s → 0.79（"HOOPER"→"TUPLE"） |

⇒ 没有「统一用哪种参考」的答案：情绪参考更贴表演，但它的录音本身发虚时会把吞音带进来；
角色音色参考吐字更稳，但个别词会走音。**只能每条都生成两版，用客观指标选。**

择优标准（`_pick9.py`）
----------------------
1. wav2vec2-960h 贪心解码的词覆盖率（不带语言模型，能抓真吞音）—— 降序
2. voiced-tilt 与该角色基线的距离（越接近音色越稳）—— 升序
3. 时长离同 id 双版中位不要太远

用法
----
  G:/Python310/python.exe -u _campaign9.py --offset 0 --limit 40
"""
import argparse
import io
import json
import os
import subprocess
import time

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
ROOT = "G:/_setup"
PLAN = os.path.join(ROOT, "_dlg_plan_v2.jsonl")
IDX = os.path.join(ROOT, "_ref9", "_index_srt.json")

# 角色「音色参考」：这个角色最中性、吐字最稳的一条长录音。
# Charles 用用户亲手切、亲耳点头的 13.58s；其它角色用该角色 calm/normal/nervous 的 9s 拼条。
ROLE_REF = {
    "Charles": (os.path.join(ROOT, "castle_fr_ref", "1_charles_normal.wav"),
                "Je suis né comme ça aussi? Vous êtes Monsieur Bréaud? Moi, je suis Charles Vernet. "
                "Non. Ça va mieux, maintenant. Non, monsieur. Et si elle, elle vous aime pas? "
                "Laisse. C'est moi qui t'invite. Je suis encore très riche."),
    "Thomas": ("_ref9/Thomas_calm.wav", None),
    "Joseph": ("_ref9/Joseph_normal.wav", None),
    "Helena": ("_ref9/Helena_nervous.wav", None),
}
# 情绪参考就等于音色参考的组：只生成一次
SAME_AS_ROLE = {"Thomas_calm", "Joseph_normal", "Helena_nervous", "Charles_neutral"}


def mtok(w):
    return max(120, min(900, int(w * 12 + 120)))


def load_plan():
    rows = []
    for l in io.open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            rows.append(json.loads(l))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=os.path.join(ROOT, "_sweep", "camp9"))
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()

    idx = json.load(io.open(IDX, encoding="utf-8"))
    plan = load_plan()
    if a.ids:
        want = {x.strip() for x in a.ids.split(",") if x.strip()}
        plan = [p for p in plan if p["id"] in want]
    else:
        plan = plan[a.offset: a.offset + a.limit] if a.limit else plan[a.offset:]
    os.makedirs(a.out, exist_ok=True)

    jobs = []
    for row in plan:
        rid = row["id"]
        group = (row.get("voice") or "").rsplit("_", 1)[0]
        role = group.split("_")[0]
        it = idx.get(group)
        # 「情绪参考本身就是角色音色参考」的组只跑一次，直接用角色参考
        # （Charles_neutral 必须走这里：角色参考是用户亲手切的 13.58s，
        #   而 _ref9/Charles_neutral.wav 是自动拼的 10.68s，用户没验过）
        if it and group not in SAME_AS_ROLE:
            jobs.append((rid, "emo", group, it["file"], it["text"], row))
        rr = ROLE_REF.get(role)
        if rr:
            p, t = rr
            p = p if os.path.isabs(p) else os.path.join(ROOT, p)
            if os.path.exists(p):
                jobs.append((rid, "role", role, p, t or idx["%s_%s" % (
                    role, {"Thomas": "calm", "Joseph": "normal",
                           "Helena": "nervous"}[role])]["text"], row))

    ok = skip = fail = 0
    t0 = time.time()
    for n, (rid, kind, key, ref, rtext, row) in enumerate(jobs, 1):
        out = os.path.join(a.out, "%s__%s__s%d.wav" % (rid, kind, a.seed))
        if os.path.exists(out) and os.path.getsize(out) > 50000:
            skip += 1
            continue
        text = row.get("text_src") or row["text"]
        cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
               "--backend", "vulkan", "--threads", str(a.threads),
               "--voice-ref", ref, "--reference-text", rtext or "",
               "--text", text, "--seed", str(a.seed), "--out", out,
               "--request-option", "max_tokens=%d" % mtok(len(text.split())),
               "--session-option", "dots_tts.mem_saver=true", "--metrics"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=ACPP_DIR, timeout=1800)
            err = (r.stderr or "")[-160:]
        except subprocess.TimeoutExpired:
            print("%s/%s TIMEOUT" % (rid, kind), flush=True)
            fail += 1
            continue
        good = os.path.exists(out) and os.path.getsize(out) > 50000
        if good:
            ok += 1
            if ok % 5 == 0 or n <= 4:
                print("[%d/%d %.0fmin] %s %s OK" % (n, len(jobs), (time.time() - t0) / 60,
                                                    rid, kind), flush=True)
        else:
            print("%s/%s FAIL %s" % (rid, kind, err), flush=True)
            fail += 1
    print("完成 OK %d / 跳过 %d / 失败 %d  %.1f 分钟" % (
        ok, skip, fail, (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    main()
