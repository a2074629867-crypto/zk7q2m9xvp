# -*- coding: utf-8 -*-
"""多手段对比：让指定副词「读慢」的可控性实测。

同一文本、同一 seed，只改一个变量：
  A_orig   原文
  B_r050   <rate, factor=0.50>word</rate>
  C_r040   <rate, factor=0.40>word</rate>
  D_comma  在词两侧加逗号（模型自然重读）
  E_dash   在词两侧加破折号

跑完自动 ASR → TextGrid → wpt → 逐词 rel。
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
OUT = os.path.join(ROOT, "_adv_exp2")
WAV = os.path.join(OUT, "wav")
TG = os.path.join(OUT, "tg")
STAGE = os.path.join(OUT, "stage")
PROM = os.path.join(OUT, "prom")
ASRPY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")
WPTPY = os.path.join(ROOT, "wpt_venv", "Scripts", "python.exe")
CFG = os.path.join(ROOT, "_wpt", "mt.yaml")


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def _span(text, word):
    pat = re.compile(r"(?<![A-Za-z'-])(%s)(?![A-Za-z'-])" % re.escape(word), re.I)
    m = pat.search(text)
    return (m.start(), m.end(), m.group(1)) if m else (None, None, None)


def tag_rate(text, word, factor):
    a, b, w = _span(text, word)
    if a is None:
        return None
    return text[:a] + "<rate, factor=%.2f>%s</rate>" % (factor, w) + text[b:]


def wrap(text, word, left, right):
    a, b, w = _span(text, word)
    if a is None:
        return None
    # 去掉词紧邻的原标点，避免出现 ",," 或 ", deliberately,"
    before = text[:a].rstrip()
    after = text[b:].lstrip()
    drop_l = ",;:—–" if before.endswith((",", ";", ":", "—", "–")) else ""
    drop_r = ",;:—–" if after[:1] in (",", ";", ":", "—", "–") else ""
    if drop_l:
        before = before[:-1].rstrip()
    if drop_r:
        after = after[1:].lstrip()
    return before + left + w + right + (" " if after else "") + after


CONDS = [
    ("A_orig", lambda t, w: t),
    ("B_r050", lambda t, w: tag_rate(t, w, 0.50)),
    ("C_r040", lambda t, w: tag_rate(t, w, 0.40)),
    ("D_comma", lambda t, w: wrap(t, w, ", ", ",")),
    ("E_dash", lambda t, w: wrap(t, w, " — ", " — ")),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="N0528:completely,N0794:desperately,N0072:entirely")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--conds", default="A_orig,B_r050,C_r040,D_comma,E_dash",
                    help="逗号分隔的条件名，须在 CONDS 里")
    ap.add_argument("--out", default=None, help="结果目录名（默认 _adv_exp2）")
    a = ap.parse_args()

    global OUT, WAV, TG, STAGE, PROM
    if a.out:
        OUT = os.path.join(ROOT, a.out)
        WAV = os.path.join(OUT, "wav")
        TG = os.path.join(OUT, "tg")
        STAGE = os.path.join(OUT, "stage")
        PROM = os.path.join(OUT, "prom")

    want = [c.strip() for c in a.conds.split(",") if c.strip()]
    conds = [(n, f) for n, f in CONDS if n in want]
    if not conds:
        raise SystemExit("无有效条件")
    log("使用条件：%s" % ",".join(n for n, _ in conds))

    for d in (OUT, WAV, TG, STAGE, PROM):
        os.makedirs(d, exist_ok=True)

    plan = {str(it["id"]): it["text"] for it in
            (lambda d: d if isinstance(d, list) else d.get("items", []))
            (json.load(open(PLAN, encoding="utf-8")))}

    items, pairs = [], []
    for spec in a.pairs.split(","):
        uid, w = spec.split(":")
        txt = plan.get(uid)
        if not txt:
            log("!! %s 不在 plan" % uid)
            continue
        variants = {}
        for name, fn in conds:
            v = fn(txt, w)
            if v:
                variants[name] = v
                items.append(("%s__%s" % (uid, name), v, 1.0))
        pairs.append((uid, w, txt, variants))

    log("待生成 %d 条（%d 单元 × %d 条件），seed=%d"
        % (len(items), len(pairs), len(conds), a.seed))
    for uid, w, txt, variants in pairs:
        log("  === %s [%s] ===" % (uid, w))
        for k, v in variants.items():
            log("     %-8s %s" % (k, v))

    t0 = time.time()
    ok = mt_gen.gen_batch(items, "adv2", WAV, a.seed)
    log("生成 %d/%d，%.1f 分钟" % (ok, len(items), (time.time() - t0) / 60))

    wavs = [os.path.join(WAV, "%s__%s.wav" % (u, c)) for u, _w, _t, vv in pairs for c in vv]
    wavs = [p for p in wavs if os.path.exists(p)]
    if not wavs:
        log("!! 无 wav")
        return

    asr_json = os.path.join(OUT, "asr.json")
    t0 = time.time()
    r = subprocess.run([ASRPY, os.path.join(ROOT, "_asr_lib.py"), "--out", asr_json] + wavs,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    if r.returncode != 0 or not os.path.exists(asr_json):
        log("!! ASR 失败 %s" % (r.stderr or "")[-300:])
        return
    asr = json.load(open(asr_json, encoding="utf-8"))
    log("ASR %d 条，%.1f 分钟" % (len(asr), (time.time() - t0) / 60))

    import mt_loop
    n_stage = 0
    for p in wavs:
        base = os.path.splitext(os.path.basename(p))[0]
        if p not in asr:
            log("  !! %s 无 ASR" % base)
            continue
        tg = os.path.join(TG, base + ".TextGrid")
        mt_loop.write_textgrid(tg, asr[p]["dur"], asr[p]["words"])
        shutil.copy2(p, os.path.join(STAGE, base + ".wav"))
        shutil.copy2(tg, os.path.join(STAGE, base + ".TextGrid"))
        n_stage += 1

    t0 = time.time()
    r = subprocess.run([WPTPY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                        "-j", "4", "-c", CFG, "-o", PROM, STAGE],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=1800)
    log("wpt %d 条，%.1f 分钟 rc=%d" % (n_stage, (time.time() - t0) / 60, r.returncode))

    import _adv_check as AC
    res = {}
    for uid, w, txt, variants in pairs:
        row = {}
        for cond in variants:
            pf = os.path.join(PROM, "%s__%s.prom" % (uid, cond))
            if not os.path.exists(pf):
                continue
            got = AC.analyse(txt, AC.read_prom(pf), uid, cond)
            for g in got:
                if g["adv"].lower() == w.lower():
                    row[cond] = g
        res[uid] = dict(word=w, conds=row, text=txt,
                        variants=variants,
                        sent_dur={c: round(asr.get(os.path.join(WAV, "%s__%s.wav" % (uid, c)), {}).get("dur", 0), 2)
                                  for c in variants})

    print("\n" + "=" * 104)
    print("%-8s %-13s %-8s %-7s %-7s %-7s %-9s %-8s" %
          ("uid", "word", "cond", "dur", "rel", "prom", "verdict", "sent_dur"))
    print("=" * 104)
    for uid, d in res.items():
        base = d["conds"].get("A_orig")
        for cond in d["variants"]:
            x = d["conds"].get(cond)
            if not x:
                print("%-8s %-13s %-8s  --  (无 prom)" % (uid, d["word"], cond))
                continue
            mark = ""
            if base and x["dur"] and base["dur"] and cond != "A_orig":
                mark = " x%.2f" % (x["dur"] / base["dur"])
            print("%-8s %-13s %-8s %-7s %-7s %-7s %-9s %-8s%s" %
                  (uid, d["word"], cond, x["dur"], x["rel"], x["prom"], x["verdict"],
                   d["sent_dur"].get(cond), mark))
        print("-" * 104)

    json.dump(res, open(os.path.join(OUT, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log("写出 %s" % os.path.join(OUT, "result.json"))


if __name__ == "__main__":
    main()
