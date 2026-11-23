# -*- coding: utf-8 -*-
"""单词级 rate 标签端到端实测。

A 条件：原文直接生成
B 条件：只把目标副词用 <rate, factor=F> 包住，其余文本不变
同 seed、同批、同参数 ⇒ 差异只能来自标签。

跑完自动：ASR → TextGrid → wpt → 逐词 rel 对比。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import wave

sys.path.insert(0, "G:/_setup")
import mt_gen

ROOT = "G:/_setup"
PLAN = "B:/mt-tts/data/plan/mt_plan3b.json"
OUT = os.path.join(ROOT, "_adv_exp")
TAGDIR = os.path.join(OUT, "wav")
TG = os.path.join(OUT, "tg")
STAGE = os.path.join(OUT, "stage")
PROM = os.path.join(OUT, "prom")
ASRPY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")
WPTPY = os.path.join(ROOT, "wpt_venv", "Scripts", "python.exe")
CFG = os.path.join(ROOT, "_wpt", "mt.yaml")


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def tag_word(text, word, factor):
    """把 text 里第一次出现的 word 用 rate 标签包住（保留原大小写）。"""
    pat = re.compile(r"(?<![A-Za-z'])(%s)(?![A-Za-z'])" % re.escape(word), re.I)
    m = pat.search(text)
    if not m:
        return None
    return text[:m.start()] + "<rate, factor=%.2f>%s</rate>" % (factor, m.group(1)) + text[m.end():]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="N0528:completely,N0794:desperately,N0112:deliberately,N0072:entirely")
    ap.add_argument("--factor", type=float, default=0.70)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    for d in (OUT, TAGDIR, TG, STAGE, PROM):
        os.makedirs(d, exist_ok=True)

    plan = {str(it["id"]): it["text"] for it in
            (lambda d: d if isinstance(d, list) else d.get("items", []))
            (json.load(open(PLAN, encoding="utf-8")))}

    items = []
    pairs = []
    for spec in a.pairs.split(","):
        uid, w = spec.split(":")
        txt = plan.get(uid)
        if not txt:
            log("!! %s 不在 plan" % uid)
            continue
        tagged = tag_word(txt, w, a.factor)
        if not tagged:
            log("!! %s 里找不到 %s" % (uid, w))
            continue
        items.append(("%s__A" % uid, txt, 1.0))
        items.append(("%s__B" % uid, tagged, 1.0))
        pairs.append((uid, w, txt, tagged))

    log("待生成 %d 条（%d 对），seed=%d factor=%.2f" % (len(items), len(pairs), a.seed, a.factor))
    for uid, w, txt, tagged in pairs:
        log("  %s [%s]\n     A: %s\n     B: %s" % (uid, w, txt[:100], tagged[:120]))

    t0 = time.time()
    ok = mt_gen.gen_batch(items, "advrate", TAGDIR, a.seed)
    log("生成完成 %d/%d，%.1f 分钟" % (ok, len(items), (time.time() - t0) / 60))

    wavs = []
    for uid, w, _t, _g in pairs:
        for cond in ("A", "B"):
            p = os.path.join(TAGDIR, "%s__%s.wav" % (uid, cond))
            if os.path.exists(p):
                wavs.append(p)
    if not wavs:
        log("!! 无 wav")
        return

    # ASR
    asr_json = os.path.join(OUT, "asr.json")
    t0 = time.time()
    r = subprocess.run([ASRPY, os.path.join(ROOT, "_asr_lib.py"), "--out", asr_json] + wavs,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    if r.returncode != 0 or not os.path.exists(asr_json):
        log("!! ASR 失败 rc=%d %s" % (r.returncode, (r.stderr or "")[-400:]))
        return
    asr = json.load(open(asr_json, encoding="utf-8"))
    log("ASR %d 条，%.1f 分钟" % (len(asr), (time.time() - t0) / 60))

    # TextGrid + stage
    for p in wavs:
        base = os.path.splitext(os.path.basename(p))[0]
        if p not in asr:
            log("  !! %s 无 ASR" % base)
            continue
        tg = os.path.join(TG, base + ".TextGrid")
        import mt_loop
        mt_loop.write_textgrid(tg, asr[p]["dur"], asr[p]["words"])
        shutil.copy2(p, os.path.join(STAGE, base + ".wav"))
        shutil.copy2(tg, os.path.join(STAGE, base + ".TextGrid"))

    t0 = time.time()
    r = subprocess.run([WPTPY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                        "-j", "4", "-c", CFG, "-o", PROM, STAGE],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=1800)
    log("wpt %d 条，%.1f 分钟 rc=%d %s" % (len(wavs), (time.time() - t0) / 60,
                                          r.returncode, (r.stderr or "")[-200:].replace("\n", " ")))

    # 解析
    import _adv_check as AC
    res = {}
    for uid, w, txt, tagged in pairs:
        row = {}
        for cond in ("A", "B"):
            pf = os.path.join(PROM, "%s__%s.prom" % (uid, cond))
            if not os.path.exists(pf):
                continue
            rows = AC.read_prom(pf)
            got = AC.analyse(txt, rows, uid, cond)
            for g in got:
                if g["adv"].lower() == w.lower():
                    row[cond] = g
        res[uid] = dict(word=w, A=row.get("A"), B=row.get("B"),
                        text=txt, tagged=tagged)

    print("\n" + "=" * 92)
    print("%-8s %-13s %-6s %-8s %-8s %-8s %-8s %-6s" %
          ("uid", "word", "cond", "dur", "rel", "prom", "verdict", "delta"))
    print("=" * 92)
    for uid, d in res.items():
        A, B = d["A"], d["B"]
        for nm, x in (("A", A), ("B", B)):
            if not x:
                print("%-8s %-13s %-6s  --" % (uid, d["word"], nm))
                continue
            print("%-8s %-13s %-6s %-8s %-8s %-8s %-8s" %
                  (uid, d["word"], nm, x["dur"], x["rel"], x["prom"], x["verdict"]))
        if A and B and A["dur"] and B["dur"]:
            print("         → 时长 %.3f → %.3f  = x%.2f   rel %.3f → %.3f   判定 %s → %s"
                  % (A["dur"], B["dur"], B["dur"] / A["dur"], A["rel"], B["rel"],
                     A["verdict"], B["verdict"]))
        print("-" * 92)

    json.dump(res, open(os.path.join(OUT, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log("写出 %s" % os.path.join(OUT, "result.json"))


if __name__ == "__main__":
    main()
