# -*- coding: utf-8 -*-
"""dots.tts **edit 模板 + 单词级标注** 实验：给副词加重音，其它一切照抄源音频。

用户思路：不要在后期改波形（WORLD 声码器有伪影），而是回到 dots.tts，
用 `template_name=edit` + `source_audio` 让模型"只改那个词、其余复刻"，
标注用 `<pitch, semitones=N>`（必要时叠 `<rate, factor=x>`）。
第一次不行就换 seed 再试，拼概率自动生成。

条件（同一 seed 对照，source 都是当前交付版）：
    base    无标签                  → 验证 edit 链路可用、时长 ≈ 源
    p6      副词包 pitch +6
    p9      副词包 pitch +9
    r7      副词包 rate 0.70
    p6r7    pitch +6 + rate 0.70（顺序：先 rate 后 pitch？不能嵌套！）
    emo     副词包 emo（短句风险高，仅作对照）

⚠️ 铁律：标签不能嵌套。p6r7 要用 sequential 语义做不到，
   所以改成「两个独立 span 相邻」是不可行的（同一个词只能包一次）。
   ⇒ 组合条件只能二选一：只 pitch 或只 rate。这里 emo 单独一档。

用法：
    python _adv_edit.py --units N0219 --conds base,p6 --seed 2041
    python _adv_edit.py --units N0219,N0627 --conds p6 --seed 2041 --seeds 2041,2043
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
OUT = os.path.join(ROOT, "_adv_edit")
LOG = os.path.join(ROOT, "_adv_edit.log")
STEPS = 8
THREADS = 2
TIMEOUT = 900


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


def instruction(text, adv, cond):
    """把副词包进标签。**只包最后一处**（同一句多副词时取与测量一致的那个）。"""
    if cond == "base":
        return text
    low = text.lower()
    i = low.rfind(adv.lower())
    if i < 0:
        return text
    j = i + len(adv)
    head, word, tail = text[:i], text[i:j], text[j:]
    if cond == "p6":
        tag = MK.pitch(word, 6)
    elif cond == "p9":
        tag = MK.pitch(word, 9)
    elif cond == "r7":
        tag = MK.rate(word, 0.70)
    elif cond == "r8":
        tag = MK.rate(word, 0.80)
    elif cond == "r6":
        tag = MK.rate(word, 0.60)
    elif cond == "pr7":
        # 前停顿 + 拉长：句末词唯一能制造强调的组合（两个标签并列、不嵌套）
        tag = MK.pause("ins", 2) + MK.rate(word, 0.70)
    elif cond == "ph7":
        # 短语级：把副词前一个词一起包进去，制造「渐慢进入关键词」
        k = head.rstrip().rfind(" ")
        prev = head[k + 1:].strip() if k >= 0 else ""
        if prev:
            head = head[:k + 1] + " "
            tag = MK.rate(prev + " " + word, 0.75)
        else:
            tag = MK.rate(word, 0.75)
    else:
        raise ValueError(cond)
    return head + tag + tail


def run_one(uid, text, adv, cond, seed, src):
    """跑一条 edit。返回输出路径或 None。"""
    os.makedirs(OUT, exist_ok=True)
    tag = "%s_%s_s%d" % (uid, cond, seed)
    dst = os.path.join(OUT, tag + ".wav")
    if os.path.exists(dst) and dur(dst) > 0.3:
        log("  跳过已存在 %s (%.2fs)" % (tag, dur(dst)))
        return dst
    ins = instruction(text, adv, cond)
    plain = text          # source_text / target_text 都是**不带标签的原文**
    tmp = os.path.join(ROOT, "_mt_tmp", "edit_" + tag)
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    outw = os.path.join(tmp, "o.wav")
    mt = min(600, max(220, int(len(text.split()) * 22 + 120)))
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", str(THREADS),
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--request-option", "template_name=edit",
           "--source-audio", src,
           "--request-option", "source_text=" + plain,
           "--request-option", "target_text=" + plain,
           "--request-option", "use_xvector=on",
           "--text", ins,
           "--out", outw,
           "--request-option", "seed=%d" % seed,
           "--request-option", "max_tokens=%d" % mt,
           "--num-inference-steps", str(STEPS),
           "--session-option", "dots_tts.mem_saver=true"]
    log("  → %s  ins=%s" % (tag, ins[:110]))
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=TIMEOUT)
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
    ap.add_argument("--units", default="N0219")
    ap.add_argument("--conds", default="base,p6")
    ap.add_argument("--seed", type=int, default=2041)
    ap.add_argument("--seeds", default=None, help="逗号分隔，覆盖 --seed")
    a = ap.parse_args()

    st = json.load(open(STATE, encoding="utf-8"))["units"]
    uids = [x.strip() for x in a.units.split(",") if x.strip()]
    conds = [x.strip() for x in a.conds.split(",") if x.strip()]
    seeds = ([int(x) for x in a.seeds.split(",") if x.strip()]
             if a.seeds else [a.seed])

    made = []
    for u in uids:
        x = st[u]
        src = os.path.join(ROOT, "_mt_pick", u + ".wav")
        if not os.path.exists(src):
            log("!! %s 无交付版" % u)
            continue
        log("%s  adv=%s  src=%.2fs  %s" % (u, x["adv"], dur(src), x["text"][:70]))
        for seed in seeds:
            for c in conds:
                p = run_one(u, x["text"], x["adv"], c, seed, src)
                if p:
                    made.append(dict(uid=u, cond=c, seed=seed, wav=p,
                                     adv=x["adv"], src=src,
                                     src_dur=round(dur(src), 2),
                                     out_dur=round(dur(p), 2)))
    json.dump(made, open(os.path.join(OUT, "_manifest.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)
    log("完成 %d 条 → %s" % (len(made), OUT))


if __name__ == "__main__":
    main()
