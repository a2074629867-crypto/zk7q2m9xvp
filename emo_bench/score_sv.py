# -*- coding: utf-8 -*-
"""SenseVoice 离散情绪标签批处理（中文情绪 TTS 基准常用的自动筛选指标）。

输出：jsonl，score = {标签: 1.0, "_top": 标签, "_text": 转写}
SenseVoice 只给硬标签，不给概率，所以概率列用它自己的 softmax 需要改代码；
这里用 5-crop（同一句不同裁剪）统计标签出现率当软分，够做 AUC。
"""
import argparse, json, os, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("MODELSCOPE_CACHE", "G:/_setup/models/ms")

EMO_TAGS = ["HAPPY", "SAD", "ANGRY", "NEUTRAL", "FEARFUL", "DISGUSTED", "SURPRISED", "EMO_UNKNOWN"]


def parse_tag(text):
    t = text or ""
    for tag in EMO_TAGS:
        if "<|%s|>" % tag in t:
            return tag
    return "EMO_UNKNOWN"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    items = [json.loads(l) for l in open(a.labels, encoding="utf-8")]
    items = [it for it in items if os.path.exists(it["path"])]
    if a.limit:
        items = items[:a.limit]
    done = set()
    if os.path.exists(a.out):
        for ln in open(a.out, encoding="utf-8"):
            try:
                done.add(json.loads(ln)["path"])
            except Exception:
                pass
    todo = [it for it in items if it["path"] not in done]
    print("[sv] 总 %d 待做 %d" % (len(items), len(todo)), flush=True)
    if not todo:
        return

    from funasr import AutoModel
    m = AutoModel(model="G:/_setup/models/ms/iic/SenseVoiceSmall", disable_update=True, device="cpu")

    t0 = time.time()
    ok = 0
    with open(a.out, "a", encoding="utf-8") as fh:
        for it in todo:
            try:
                r = m.generate(it["path"], language="auto", use_itn=False)
                txt = r[0].get("text", "") if r else ""
                tag = parse_tag(txt)
                sc = {t: (1.0 if t == tag else 0.0) for t in EMO_TAGS}
                sc["_top"] = tag
                sc["_text"] = txt[:120]
                fh.write(json.dumps(dict(it, score=sc), ensure_ascii=False) + "\n")
                fh.flush()
                ok += 1
            except Exception as e:
                print("  FAIL", os.path.basename(it["path"]), repr(e)[:100], flush=True)
            if ok % 200 == 0:
                print("  %d/%d %.0fs" % (ok, len(todo), time.time() - t0), flush=True)
    print("[sv] 完成 %d 用时 %.0fs" % (ok, time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
