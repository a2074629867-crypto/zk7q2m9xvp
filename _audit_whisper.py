"""对被体检标出的条目跑 whisper 词级转写，作为第二 ASR 仲裁。"""
import io
import json
import os
import sys

sys.path.insert(0, "G:/_setup")

AUD = "G:/_setup/_audio_ch123/out_paused"
OUT = "G:/_setup/_audit_whisper.json"


def main():
    rows = json.load(io.open("G:/_setup/_dlg_audit.json", encoding="utf-8"))
    ids = [r["id"] for r in rows if r["flags"]]
    print("待转写 %d 条" % len(ids), flush=True)
    from transplant_prosody2 import word_times
    out = {}
    for k, i in enumerate(ids):
        p = os.path.join(AUD, i + ".wav")
        if not os.path.exists(p):
            continue
        try:
            ws = word_times(p)
        except Exception as e:
            print("  %s 失败 %s" % (i, e), flush=True)
            ws = []
        out[i] = [(t, round(a, 3), round(b, 3)) for a, b, t in ws]
        if k % 10 == 0:
            print("  %d/%d" % (k, len(ids)), flush=True)
    json.dump(out, io.open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("写出", OUT, len(out))


if __name__ == "__main__":
    main()
