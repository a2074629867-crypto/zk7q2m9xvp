# -*- coding: utf-8 -*-
"""把 `_read_full.py` 的日志解析成 {id: 现役召回}，供短句闸做第二 ASR 仲裁。

为什么需要第二 ASR：
  短句（1~3 词）上自由识别误伤率极高 —— `O.K.`→`Okay`、`Liar`→`Lila`、
  `Moths`→`Bush` 都会被判成「念错」。单 ASR 结论在 59 条里误伤 6 条（≥10%）。
  规则：两个独立 ASR 都认不出才算真错；任一 >= 0.80 即认为内容在。
"""
import io
import json
import re
import sys

out = {}
for p in sys.argv[1:]:
    cur = None
    for line in io.open(p, encoding="utf-8"):
        m = re.match(r"^== (\S+)\s", line)
        if m:
            cur = m.group(1)
            continue
        m = re.search(r"现役\s+召回\s+([\d.]+)", line)
        if m and cur:
            out[cur] = float(m.group(1))
print(json.dumps(out, ensure_ascii=False))
io.open("G:/_setup/_whisper_recall.json", "w", encoding="utf-8").write(
    json.dumps(out, ensure_ascii=False, indent=1))
print("写出 G:/_setup/_whisper_recall.json %d 条" % len(out))
