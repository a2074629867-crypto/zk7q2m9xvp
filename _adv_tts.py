# -*- coding: utf-8 -*-
"""dots.tts **纯生成（--task tts）+ 单词级标注** 实验。

与 `_adv_edit.py` 的根本区别：
    edit  = 给源音频 + template_name=edit ⇒ 输出时长被源音频**钉死**，
            rate 只能在固定预算内重新分配时间（从邻词借）。
    tts   = 不给源音频 ⇒ 模型自己决定总长，rate 拉长那个词**不必从邻词借**。

用户问题："不能依靠 edit 引擎重生成让时长变长吗？而不是在原音频上改"
⇒ edit 是重生成，但预算是源的；要真正变长必须走 tts（无源）或 edit+pause（能破预算）。

条件（同 seed 严格对照）：
    base  无标签                → 这一 seed 的自然时长基线
    r7    副词包 rate 0.70
    r6    副词包 rate 0.60
    r5    副词包 rate 0.50
    pr7   副词前插停顿 + rate 0.70（不嵌套，两个并列标签）

用法：
    python _adv_tts.py --units N0627 --conds base,r7 --seed 2051
    python _adv_tts.py --units N0219,N0627 --conds r7 --seeds 2051,2053
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import wave

sys.path.insert(0, "G:/_setup")
import dots_markup as MK

ROOT = "G:/_setup"
ACPP = ("C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/"
        "reader/_tts_lab/acpp/audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = ("called Sirius, is reaching Earth after traveling at 186,000 "
           "miles per second.")
STATE = os.path.join(ROOT, "_mt_adv_state.json")
OUT = os.path.join(ROOT, "_adv_tts")
LOG = os.path.join(ROOT, "_adv_tts.log")
STEPS = 8
THREADS = 2
TIMEOUT = 1200


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def dur(p):
    try:
        w = wave.open(p)
        d = w.getnframes() / float(w.getframerate())
        w.close()
        return d
    except Exception:
        return 0.0


def span_word(text, adv, fn):
    """把副词（最后一处）包进标签，其余原文不动。"""
    low = text.lower()
    i = low.rfind(adv.lower())
    if i < 0:
        return text
    j = i + len(adv)
    return text[:i] + fn(text[i:j]) + text[j:]


# ⛔ 叠加条件（rp / rp9 / pr）已于 2026-10-27 由用户否掉：
#    「如果叠加读的那个副词直接音色都变了，不要叠加」「要么就 pitch 要么就 rate0.7」
#    代码保留只为复现历史实验，**生产禁止使用**；加 --allow-stack 才能跑。
STACK_CONDS = ("rp", "rp9", "pr")


def instruction(text, adv, cond):
    if cond == "base":
        return text
    if cond == "r7":
        return span_word(text, adv, lambda w: MK.rate(w, 0.70))
    if cond == "r6":
        return span_word(text, adv, lambda w: MK.rate(w, 0.60))
    if cond == "r5":
        return span_word(text, adv, lambda w: MK.rate(w, 0.50))
    if cond == "pr7":
        return span_word(text, adv, lambda w: MK.pause("ins", 2) + MK.rate(w, 0.70))
    if cond == "p6":
        return span_word(text, adv, lambda w: MK.pitch(w, 6))
    if cond == "p9":
        return span_word(text, adv, lambda w: MK.pitch(w, 9))
    if cond == "p3":
        return span_word(text, adv, lambda w: MK.pitch(w, 3))
    if cond == "rp":
        # 「两个一起」：官方铁律禁止嵌套，这里用**相邻两个 span 覆盖同一位置**做不到，
        # 所以直接试嵌套写法，看解析器是否接受；不接受就走 _adv_chain.py 两步串行。
        return span_word(text, adv,
                         lambda w: MK.rate(MK.pitch(w, 6), 0.60))
    if cond == "pr":
        # 反序嵌套，用来判断「先 rate 后 pitch」是否比「先 pitch 后 rate」更灵
        return span_word(text, adv,
                         lambda w: MK.pitch(MK.rate(w, 0.60), 6))
    if cond == "rp9":
        # rate 0.60 + pitch 9：两个单轴各自最强的档位组合
        return span_word(text, adv,
                         lambda w: MK.rate(MK.pitch(w, 9), 0.60))
    raise ValueError(cond)


def run_one(uid, text, adv, cond, seed, xvec):
    os.makedirs(OUT, exist_ok=True)
    tag = "%s_%s_s%d" % (uid, cond, seed)
    dst = os.path.join(OUT, tag + ".wav")
    if os.path.exists(dst) and dur(dst) > 0.3:
        log("  跳过已存在 %s (%.2fs)" % (tag, dur(dst)))
        return dst
    ins = instruction(text, adv, cond)
    tmp = os.path.join(ROOT, "_mt_tmp", "tts_" + tag)
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    outw = os.path.join(tmp, "o.wav")
    # 给「更长」留足预算：33% 冗余 + 200
    mt = min(720, max(260, int(len(text.split()) * 28 + 200)))
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", str(THREADS),
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", ins,
           "--out", outw,
           "--seed", str(seed),
           "--request-option", "max_tokens=%d" % mt,
           "--num-inference-steps", str(STEPS),
           "--session-option", "dots_tts.mem_saver=true"]
    if xvec != "none":
        cmd[1:1] = []          # 占位，保持结构清晰
        cmd += ["--request-option", "use_xvector=" + xvec]
    log("  → %s  ins=%s" % (tag, ins[:110]))
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=TIMEOUT)
        rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        rc, out = -9, "TIMEOUT"
    el = time.time() - t0
    ok = os.path.exists(outw) and dur(outw) > 0.3
    if ok:
        shutil.copy2(outw, dst)
        log("    ok %.2fs 用时%.0fs  rc=%d" % (dur(dst), el, rc))
    else:
        log("    FAIL rc=%d 用时%.0fs" % (rc, el))
        for ln in out.strip().splitlines()[-6:]:
            log("      " + ln[:180])
    shutil.rmtree(tmp, ignore_errors=True)
    return dst if ok else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", default="N0627")
    ap.add_argument("--conds", default="base,r7")
    ap.add_argument("--allow-stack", action="store_true",
                    help="⛔ 仅复现历史实验：允许 rp/rp9/pr 叠加（生产禁用）")
    ap.add_argument("--seed", type=int, default=2051)
    ap.add_argument("--seeds", default=None)
    ap.add_argument("--xvec", default="off", choices=["off", "on", "none"],
                    help="tts 无源音频，默认 off 强制走 voice-ref 音色")
    a = ap.parse_args()

    st = json.load(open(STATE, encoding="utf-8"))["units"]
    uids = [x.strip() for x in a.units.split(",") if x.strip()]
    conds = [x.strip() for x in a.conds.split(",") if x.strip()]
    bad = [c for c in conds if c in STACK_CONDS]
    if bad and not getattr(a, "allow_stack", False):
        raise SystemExit("⛔ 叠加条件 %s 已由用户否决（强调词的音色会变）。"
                         "要么 pitch 要么 rate 0.70，二选一。"
                         "确需复现历史实验请加 --allow-stack。" % ",".join(bad))
    seeds = ([int(x) for x in a.seeds.split(",") if x.strip()]
             if a.seeds else [a.seed])

    made = []
    for u in uids:
        x = st[u]
        log("%s  adv=%s  %s" % (u, x["adv"], x["text"][:70]))
        for seed in seeds:
            for c in conds:
                p = run_one(u, x["text"], x["adv"], c, seed, a.xvec)
                if p:
                    made.append(dict(uid=u, cond=c, seed=seed, wav=p,
                                     adv=x["adv"], out_dur=round(dur(p), 2)))
    mf = os.path.join(OUT, "_manifest.json")
    old = []
    if os.path.exists(mf):
        try:
            old = json.load(open(mf, encoding="utf-8"))
        except Exception:
            old = []
    seen = {(r["uid"], r["cond"], r["seed"]) for r in made}
    keep = [r for r in old if (r["uid"], r["cond"], r["seed"]) not in seen]
    json.dump(keep + made, open(mf, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log("完成 %d 条 → %s" % (len(made), OUT))


if __name__ == "__main__":
    main()
