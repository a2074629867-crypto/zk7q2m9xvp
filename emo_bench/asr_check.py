# -*- coding: utf-8 -*-
"""ASR 复核：标签有没有把字吃掉。

emo 标签会改变韵律，最危险的副作用是吞字 / 漏词（用户明确要求「吞字必须重生成」）。
这里用 Parakeet TDT v3 逐条转写，与目标文本做词级对齐，报：
    - 词数覆盖（转写词数 / 目标词数）
    - 缺词列表
    - WER（简单归一后）
"""
import json, os, sys, re, collections

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "G:/_setup")

TARGET = "I don't think anyone else knows about that door."
OUT = os.path.join(HERE, "out")


def norm(s):
    s = s.lower().replace("’", "'")
    s = re.sub(r"[^a-z' ]", " ", s)
    return [w for w in s.split() if w]


def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / max(1, len(r))


def main():
    import _asr_lib
    idx = os.path.join(OUT, "gen_index.jsonl")
    items = [json.loads(l) for l in open(idx, encoding="utf-8")]
    out = os.path.join(OUT, "gen_asr.jsonl")
    done = set()
    if os.path.exists(out):
        for ln in open(out, encoding="utf-8"):
            try:
                done.add(json.loads(ln)["path"])
            except Exception:
                pass
    todo = [it for it in items if it["path"] not in done]
    print("待转写", len(todo), "/", len(items), flush=True)
    if not todo:
        return
    paths = [it["path"] for it in todo]
    res = _asr_lib.transcribe(paths)
    with open(out, "a", encoding="utf-8") as fh:
        for it in todo:
            r = res.get(it["path"]) or {}
            txt = r.get("text", "")
            ref = it["text"]
            rec = dict(path=it["path"], pid=it["pid"], cond=it["cond"],
                       hyp=txt, ref=ref, wer=round(wer(ref, txt), 3),
                       n_hyp=len(norm(txt)), n_ref=len(norm(ref)),
                       dur=it["dur"])
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print("  %-32s WER=%.2f  %s" % (os.path.basename(it["path"]), rec["wer"], txt[:70]), flush=True)


if __name__ == "__main__":
    main()
