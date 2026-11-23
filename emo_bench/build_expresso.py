# -*- coding: utf-8 -*-
"""从 Expresso parquet 抽取平衡的情绪评测集（真人 ground truth）。

Expresso 的 style 就是表演风格，天然带标注：
    default(中性) / happy / sad / confused / whisper / laughing / enunciated / emphasis

每个 (style, speaker) 抽 N 条，16k 单声道写盘，同时落 manifest.json。
音频来自 parquet 内嵌 bytes（原始 48k flac 或 wav，取决于数据集版本）。
"""
import argparse, io, json, os, glob, collections
import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

SRC = "G:/voice_lib/datasets/expresso"
OUT = "G:/_setup/emo_bench/wav/expresso"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=25, help="每个 style×speaker 抽几条")
    ap.add_argument("--min-sec", type=float, default=1.5)
    ap.add_argument("--max-sec", type=float, default=12.0)
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    buckets = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(SRC, "*.parquet"))):
        t = pq.ParquetFile(f).read(columns=["style", "speaker_id", "text", "audio", "id"])
        styles = t.column("style").to_pylist()
        spks = t.column("speaker_id").to_pylist()
        texts = t.column("text").to_pylist()
        auds = t.column("audio").to_pylist()
        ids = t.column("id").to_pylist()
        for i in range(len(t)):
            st, sp = styles[i], spks[i]
            if st in ("essentials", "longform", "singing"):
                continue
            buckets[(st, sp)].append((ids[i], texts[i], auds[i]["bytes"]))

    manifest = []
    for (st, sp), items in sorted(buckets.items()):
        # 均匀取样：按 id 排序后等距抽，避免全取开头
        items.sort(key=lambda x: x[0])
        step = max(1, len(items) // args.per)
        picked, i = [], 0
        while len(picked) < args.per and i < len(items):
            picked.append(items[i])
            i += step
        for cid, text, blob in picked:
            try:
                y, sr = sf.read(io.BytesIO(blob), dtype="float32", always_2d=True)
            except Exception as e:
                print("read fail", cid, e)
                continue
            y = y.mean(axis=1)
            d = len(y) / sr
            if d < args.min_sec or d > args.max_sec:
                continue
            if sr != 16000:
                from scipy.signal import resample_poly
                from math import gcd
                g = gcd(int(sr), 16000)
                y = resample_poly(y, 16000 // g, int(sr) // g).astype(np.float32)
                sr = 16000
            # 峰值归一，避免电平差干扰模型
            pk = float(np.abs(y).max()) or 1.0
            y = (y / pk * 0.89).astype(np.float32)
            name = "%s__%s__%s.wav" % (sp, st, cid)
            p = os.path.join(OUT, name)
            sf.write(p, y, sr)
            manifest.append(dict(path=p, style=st, speaker=sp, text=text, dur=round(d, 2)))

    with open(os.path.join(OUT, "_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    c = collections.Counter((m["speaker"], m["style"]) for m in manifest)
    print("总计", len(manifest))
    for k in sorted(c):
        print(" ", k, c[k])


if __name__ == "__main__":
    main()
