# -*- coding: utf-8 -*-
"""_cloud_gen.py —— 云端批量生成候选（跑在 V100，不在本机）。

输入 /home/aistudio/dlg_in/spec.json
   {"items":[{"id","text","voices":[...],"seeds":[...]}]}
输出 /home/aistudio/cand/<id>__<voice>__s<seed>.wav  （已归一到 voiced RMS −24dBFS）
      /home/aistudio/cand/manifest.json

归一必须与本地 `norm_dlg.vdb` 同一把尺子（相对阈值 = 峰值−35dB），
否则本机闸测的是增益不是内容（DECISIONS 17:15 已踩过）。

用法（云端）：python3 _cloud_gen.py [spec路径]
"""
import json
import os
import sys
import time
import urllib.request

import numpy as np

U = "http://127.0.0.1:8080/v1/audio/speech"
OUT = "/home/aistudio/cand"
TARGET = -24.0
PEAK_MAX = 0.891
SRC = sys.argv[1] if len(sys.argv) > 1 else "/home/aistudio/dlg_in/spec.json"


def wav_write(path, y, sr):
    import wave
    y = np.clip(y, -1.0, 1.0)
    with wave.open(path + ".part", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767.0).astype("<i2").tobytes())
    os.replace(path + ".part", path)


def wav_read(path):
    import wave
    with wave.open(path) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def vdb(y, sr):
    """voiced RMS，相对阈值（峰值−35dB），与本地 norm_dlg.voiced_mask 同口径。"""
    f = max(1, int(0.02 * sr))
    n = len(y) // f
    if n == 0:
        return -99.0
    e = np.sqrt((y[:n * f].reshape(n, f) ** 2).mean(1))
    db = 20 * np.log10(np.maximum(e, 1e-9))
    thr = max(float(db.max()) - 35.0, -60.0)
    m = db > thr
    if not m.any():
        return -99.0
    return float(20 * np.log10(np.sqrt((e[m] ** 2).mean()) + 1e-9))


def soft_clip(y, ceiling):
    a = np.abs(y)
    over = a > ceiling * 0.7
    y2 = y.copy()
    x = a[over] / (ceiling * 0.7)
    y2[over] = np.sign(y[over]) * (ceiling * 0.7) * (1.0 / (1.0 + np.exp(-3.0 * (x - 1.0))) * 0.3 + 0.7 * np.tanh(x * 0.9))
    return np.clip(y2, -ceiling, ceiling)


def gen(text, voice, seed):
    body = {"model": "dots", "input": text, "voice": voice, "seed": seed}
    req = urllib.request.Request(U, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = r.read()
    return data, time.time() - t0


def main():
    spec = json.load(open(SRC, encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    rows = []
    jobs = [(it, v, s) for it in spec["items"] for v in it["voices"] for s in it["seeds"]]
    k = 0
    for it, voice, seed in jobs:
        k += 1
        name = "%s__%s__s%d.wav" % (it["id"], voice, seed)
        p = os.path.join(OUT, name)
        rec = dict(id=it["id"], voice=voice, seed=seed, file=name)
        if os.path.exists(p):
            rec["skip"] = True
            rows.append(rec)
            continue
        try:
            data, el = gen(it["text"], voice, seed)
        except Exception as e:
            rec["err"] = str(e)[:120]
            print("[%d/%d] %-8s %-20s s%d FAIL %s" % (k, len(jobs), it["id"], voice, seed, e), flush=True)
            rows.append(rec)
            continue
        tmp = p + ".raw"
        with open(tmp, "wb") as f:
            f.write(data)
        y, sr = wav_read(tmp)
        r0 = vdb(y, sr)
        gain = TARGET - r0
        if abs(gain) > 20.0:
            rec["note"] = "gain %.1fdB 超限未处理" % gain
            os.replace(tmp, p)
        else:
            y1 = y * (10 ** (gain / 20.0))
            pk = float(np.abs(y1).max())
            clip = pk > PEAK_MAX
            if clip:
                y1 = soft_clip(y1, PEAK_MAX)
            wav_write(p, y1, sr)
            os.remove(tmp)
            rec.update(rms0=round(r0, 2), gain=round(gain, 1), clip=bool(clip))
        y, sr = wav_read(p)
        rec.update(dur=round(len(y) / sr, 2), sr=sr, peak=round(float(np.abs(y).max()), 3),
                   rms=round(vdb(y, sr), 2), sec=round(el, 2))
        rows.append(rec)
        print("[%d/%d] %-8s %-20s s%-3d %5.2fs %.2fs %s" % (
            k, len(jobs), it["id"], voice, seed, el, rec["dur"],
            "clip" if rec.get("clip") else ""), flush=True)
    json.dump(rows, open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = [r for r in rows if r.get("dur")]
    print("\n生成 %d / %d  失败 %d" % (len(ok), len(jobs), len(jobs) - len(ok)))


if __name__ == "__main__":
    main()
