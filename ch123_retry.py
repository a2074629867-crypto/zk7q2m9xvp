# -*- coding: utf-8 -*-
"""对 ASR 判定吞字/错词的条目换 seed 重生成。

    G:/Python310/python.exe ch123_retry.py [轮次]

读 _ch123_check.json 里 need_retry=true 的，按 seed 43→44→45 逐个试，
每次覆盖原文件（原文件备份到 _bak/）。
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import INNER, PLAN, REFS

OUT = "G:/_setup/ch123"
BAK = "G:/_setup/ch123/_bak"
CHK = "G:/_setup/_ch123_check.json"
os.makedirs(BAK, exist_ok=True)

ITEMS = {("L%03d" % i): (w, e, t) for i, w, e, t in PLAN}
ITEMS.update({("I%02d" % i): (w, e, t) for i, (_, w, e, t) in enumerate(INNER)})


def gen_with_seed(body, ref, rtext, mt, out, seed):
    import subprocess
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--voice-ref", ref, "--reference-text", rtext, "--text", body,
           "--request-option", "max_tokens=%d" % mt, "--request-option", "use_xvector=on",
           "--seed", str(seed), "--out", out,
           "--session-option", "dots_tts.mem_saver=true"]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=R.ACPP_DIR)
    return os.path.exists(out) and os.path.getsize(out) > 60000


def main():
    rnd = sys.argv[1] if len(sys.argv) > 1 else "1"
    chk = json.load(open(CHK, encoding="utf-8"))
    todo = [k for k, v in chk.items() if v.get("need_retry")]
    print("需重生成 %d 条：%s" % (len(todo), " ".join(todo)), flush=True)
    for k in todo:
        who, emo, text = ITEMS[k]
        ref, rtext = REFS[who]
        body = "<emo, type=%s, level=2>%s</emo>" % (emo, text) if emo else text
        mt = max(200, int(len(text.split()) * 26) + 160)
        out = os.path.join(OUT, k + ".wav")
        bak = os.path.join(BAK, "%s_r%s.wav" % (k, rnd))
        if os.path.exists(out) and not os.path.exists(bak):
            shutil.copy2(out, bak)
        for seed in (43, 44, 45):
            ok = gen_with_seed(body, ref, rtext, mt, out, seed)
            print("  %-5s seed %d -> %s" % (k, seed, "OK" if ok else "FAIL"), flush=True)
            if ok:
                break
            time.sleep(12)
        time.sleep(11)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
