# -*- coding: utf-8 -*-
"""用 LLM 判定「声学测出的 top1 焦点是合法重音，还是分析器伪影」，并与人工 gold 对比。

    python _llm_accent_eval.py --dry                    # 只打印 prompt，不调接口
    python _llm_accent_eval.py --models gpt-4o-mini     # 跑一种条件
    python _llm_accent_eval.py --models a,b --mode all  # 多模型对比

任务定义（二分类）：
    VALID    = 该词做句内主重音在语言学上成立（否定 / 指示 / 时间 / 称呼 / 对比焦点）
    ARTIFACT = 分析器伪影（句首 F0 重置、短语后接停顿的边界效应）

三种信号条件：
    bare     只给句子 + top1 词和位置
    context  额外给该句前面的原文（验证「理解上下文」是否真有增量）
    fewshot  额外给 4 个已判例子（验证 few-shot 是否真有增量）

输出：准确率 / 混淆矩阵 / 每个条件的假阳性率（把 VALID 判成 ARTIFACT）。
假阳性率是关键 —— 一个总喊 ARTIFACT 的模型在虚词集上分数会虚高，必须看负例。
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import urllib.request

GOLD = "G:/_setup/_accent_eval_set.json"
CTX = "G:/_setup/_accent_ctx.json"
BASE = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
KEY = os.environ.get("OPENAI_API_KEY", "")

SYS = "You are an English prosody annotator. Answer with one label only."

TPL_BARE = """A text-to-speech system read this sentence. An acoustic analyzer then reported \
that the single most prominent word is "{w}" (word {pos1} of {n}).

Sentence: {s}

Is "{w}" a linguistically legitimate place for the primary prominence, or is it an artifact \
of the analyzer (for example a sentence-initial F0 reset, or a boundary effect on a phrase \
that is immediately followed by a pause)?

Answer exactly one of: VALID / ARTIFACT
Then a reason of at most 12 words."""

TPL_CTX = """{ctx}

A text-to-speech system read the last sentence. An acoustic analyzer then reported that the \
single most prominent word in it is "{w}" (word {pos1} of {n}).

Target sentence: {s}

Considering the preceding context, is "{w}" a linguistically legitimate place for the primary \
prominence, or is it an artifact of the analyzer (sentence-initial F0 reset, boundary effect \
before a pause)?

Answer exactly one of: VALID / ARTIFACT
Then a reason of at most 12 words."""

FEWSHOT = """Examples of how to label:

Sentence: But it had not been moving.
Most prominent word: "not" (word 4 of 6)
Answer: VALID - negative focus, this is the expected nucleus.

Sentence: For, in middle age, he was acquiring a dynastic sense.
Most prominent word: "For" (word 1 of 10)
Answer: ARTIFACT - sentence-initial function word followed by a comma; real focus is "dynastic".

Sentence: And that was no more than the truth, though his father would not have believed it.
Most prominent word: "that" (word 2 of 16)
Answer: VALID - demonstrative referring back to prior content, contrastive.

Sentence: At once, the whole moth, already years dead, disintegrated.
Most prominent word: "once" (word 2 of 8)
Answer: ARTIFACT - fronted adverbial followed by a comma; real focus is the main verb.
"""


def build_prompt(it, mode):
    s = it["text"]
    tpl = TPL_CTX if mode == "context" else TPL_BARE
    ctx = ""
    if mode == "context":
        ctx = (it.get("prev") or "").strip()
        ctx = ("Preceding text from the same book:\n" + ctx) if ctx else "There is no preceding text."
    body = tpl.format(w=it["top1"], pos1=it["pos"] + 1, n=it["n"], s=s, ctx=ctx)
    if mode == "fewshot":
        body = FEWSHOT + "\nNow label this one:\n\n" + body
    return body


def call(model, prompt, retries=3):
    url = BASE + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 60,
    }
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read())
            return d["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last = e
    return "ERR " + type(last).__name__ + " " + str(last)[:80]


def parse(resp):
    u = resp.upper()
    if "ARTIFACT" in u:
        return "cwt_artifact"
    if "VALID" in u:
        return "valid_focus"
    return None


def gold_label(it):
    lab = it["label"]
    return "cwt_artifact" if lab == "cwt_artifact" else "valid_focus"


def run(model, mode, items, workers):
    prompts = [(i, build_prompt(it, mode)) for i, it in enumerate(items)]
    out = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(call, model, p): i for i, p in prompts}
        for f in cf.as_completed(futs):
            out[futs[f]] = f.result()
    return [out[i] for i in range(len(items))]


def score(items, resps, verbose=False):
    tp = fp = tn = fn = bad = 0
    rows = []
    for it, r in zip(items, resps):
        g = gold_label(it)
        p = parse(r)
        rows.append((it, g, p, r))
        if p is None:
            bad += 1
            continue
        if g == "cwt_artifact" and p == "cwt_artifact":
            tp += 1
        elif g == "cwt_artifact":
            fn += 1
        elif p == "cwt_artifact":
            fp += 1
        else:
            tn += 1
    n = tp + fp + tn + fn
    acc = (tp + tn) / n if n else 0
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    if verbose:
        for it, g, p, r in rows:
            if p != g:
                print(f"    MISS {it['uid']:6s} gold={g:12s} pred={p}  top1={it['top1']:8s} pos={it['pos']:2d}  <- {r[:60]}")
    return {"n": n, "unparsed": bad, "acc": acc, "prec_artifact": prec, "rec_artifact": rec, "f1_artifact": f1,
            "ok": tp + tn, "fp": fp, "fn": fn}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--mode", default="bare", choices=["bare", "context", "fewshot", "all"])
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="G:/_setup/_llm_accent_result.json")
    a = ap.parse_args()

    d = json.load(open(GOLD, encoding="utf-8"))
    items = d["items"]
    if os.path.exists(CTX):
        ctx = json.load(open(CTX, encoding="utf-8"))
        for it in items:
            it["prev"] = ctx.get(it["uid"], "")
    else:
        print(f"[warn] no context file {CTX}; 'context' mode falls back to empty", file=sys.stderr)

    modes = ["bare", "context", "fewshot"] if a.mode == "all" else [a.mode]

    if a.dry:
        for m in modes:
            print("=" * 20, m, "=" * 20)
            print(build_prompt(items[1], m))
        return

    models = [x.strip() for x in a.models.split(",") if x.strip()]
    if not models:
        sys.exit("--models required (or use --dry)")
    if not BASE or not KEY:
        sys.exit("OPENAI_BASE_URL / OPENAI_API_KEY missing")

    report = {}
    for model in models:
        for m in modes:
            resps = run(model, m, items, a.workers)
            s = score(items, resps, verbose=True)
            report[f"{model}|{m}"] = s
            print(f"{model:28s} {m:8s} n={s['n']:2d} acc={s['acc']:.3f} "
                  f"P(ART)={s['prec_artifact']:.3f} R(ART)={s['rec_artifact']:.3f} "
                  f"miss={s['fp']}fa+{s['fn']}fr unparsed={s['unparsed']}")
    json.dump(report, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved", a.out)


if __name__ == "__main__":
    main()
