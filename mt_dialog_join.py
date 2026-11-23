# -*- coding: utf-8 -*-
"""mt_dialog_join.py —— 多角色对白装配：逐条归一 → 按说话人切停顿 → 拼成场景。

和叙述拼接（mt_chapter_join）的区别只有一条：**停顿由「换不换人」决定**，
而不是由标点决定。叙述里句号就该停 1.7s；对白里同一人连着说两句停 0.5s 就够，
换人时反而要留出接话的空隙。

停顿口径（可用 --turn / --same / --cont 改）：
    换人          0.75s   —— 接话空隙，太长会像念稿
    同人·句末     0.50s   —— 同一个人连着两句
    同人·句中     0.30s   —— 逗号/分号结尾，几乎连读

电平：每条先按 voiced RMS 归一到 −24 dBFS 再拼。不逐条归一，
不同角色/不同 seed 的 take 会差 5~10dB（历史实测跨 9.3dB），拼起来一会儿大一会儿小。

用法：
    python mt_dialog_join.py --plan _ch123_final.json --audio _dlg_out --out _scene.wav
    python mt_dialog_join.py --plan _ch123_final.json --dry
"""
import argparse
import json
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mt_final_pause as FP  # noqa: E402
from mt_chapter_join import level_norm  # noqa: E402

SR_OUT = 48000
TARGET_DB = -24.0


def read_wav(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    if sw != 2:
        raise SystemExit("只支持 16bit PCM：%s" % p)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def resample(a, sr, sr_out=SR_OUT):
    if sr == sr_out:
        return a
    n = int(round(len(a) * sr_out / sr))
    return np.interp(np.linspace(0, len(a) - 1, n),
                     np.arange(len(a), dtype=np.float64), a).astype(np.float32)


def trim(a, sr, head_pad=0.05, tail_pad=0.20, fade=0.005):
    """裁掉首尾静音。dots.tts 每条开头都有 0.8~1.4s 静音，不裁换人处会拖成 2s。"""
    db, _, hop = FP.frame_db(a, sr)
    if len(db) < 5:
        return a, 0.0, 0.0
    on = db > (np.percentile(db, 90) - 25.0)
    if not on.any():
        return a, 0.0, 0.0
    s0 = int(np.argmax(on)) * hop
    e0 = (len(on) - int(np.argmax(on[::-1]))) * hop
    s = max(0.0, s0 - head_pad)
    e = min(len(a) / sr, e0 + tail_pad)
    if e - s < 0.15:
        return a, 0.0, 0.0
    y = a[int(s * sr):int(e * sr)].copy()
    nf = max(1, int(fade * sr))
    if len(y) > 2 * nf:
        ramp = np.linspace(0.0, 1.0, nf, dtype=np.float32)
        y[:nf] *= ramp
        y[-nf:] *= ramp[::-1]
    return y, s, e


def gap_after(text, same_speaker, a):
    t = (text or "").rstrip()
    if not same_speaker:
        return a.turn, "turn"
    if t and t[-1] in ".?!":
        return a.same, "same_sent"
    if t and t[-1] in ",;:\u2013\u2014-":
        return a.cont, "same_clause"
    return a.cont, "same_none"


def find_wav(audio, uid, who):
    for name in ("%s_%s.wav" % (who, uid), "%s_%s.wav" % (uid, who), "%s.wav" % uid):
        p = os.path.join(audio, name)
        if os.path.exists(p):
            return p
    for root, _d, files in os.walk(audio):
        for name in ("%s_%s.wav" % (who, uid), "%s_%s.wav" % (uid, who), "%s.wav" % uid):
            if name in files:
                return os.path.join(root, name)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="_ch123_final.json")
    ap.add_argument("--audio", default="_dlg_out")
    ap.add_argument("--out", default="_scene_dialog.wav")
    ap.add_argument("--timeline", default=None, help="时间轴 json（默认 <out>.timeline.json）")
    ap.add_argument("--turn", type=float, default=0.75, help="换人停顿秒")
    ap.add_argument("--same", type=float, default=0.50, help="同人句末停顿秒")
    ap.add_argument("--cont", type=float, default=0.30, help="同人句中停顿秒")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    items = []
    if isinstance(plan, dict):
        for uid, v in plan.items():
            if isinstance(v, dict) and v.get("text"):
                items.append((uid, v.get("who") or "N", v["text"]))
    else:
        for v in plan:
            items.append((str(v.get("uid")), v.get("who") or "N", v.get("text") or ""))

    pieces, tl, miss = [], [], []
    prev_who = None
    t = 0.0
    for uid, who, text in items:
        p = find_wav(a.audio, uid, who)
        if not p:
            miss.append(uid)
            continue
        x, sr = read_wav(p)
        x, s0, e0 = trim(x, sr)
        x = resample(x, sr)
        x, g = level_norm(x, SR_OUT, TARGET_DB)
        pieces.append(x)
        dur = len(x) / SR_OUT
        tl.append(dict(uid=uid, who=who, start=round(t, 3), dur=round(dur, 3),
                       gain=g, src=p, text=text[:60]))
        t += dur
        same = (prev_who == who)
        gsec, kind = gap_after(text, same, a)
        if gsec > 0:
            pieces.append(np.zeros(int(gsec * SR_OUT), dtype=np.float32))
            t += gsec
        tl[-1]["gap_after"] = round(gsec, 3)
        tl[-1]["gap_kind"] = kind
        prev_who = who

    if miss:
        print("!! 缺 %d 条音频：%s" % (len(miss), miss[:8]), file=sys.stderr)
    if not pieces:
        print("!! 没有可拼的音频", file=sys.stderr)
        return 2

    y = np.concatenate(pieces)
    peak = float(np.abs(y).max())
    if peak > 0.95:
        y = y * (0.95 / peak)
        print("  峰值 %.2f 已压到 0.95" % peak)

    from collections import Counter
    print("拼装 %d 条，总时长 %.1f 秒（%.1f 分）" % (len(tl), len(y) / SR_OUT, len(y) / SR_OUT / 60))
    print("  停顿分布 %s" % dict(Counter(x["gap_kind"] for x in tl)))
    print("  角色分布 %s" % dict(Counter(x["who"] for x in tl)))
    print("  增益范围 %.1f ~ %.1f dB" % (min(x["gain"] for x in tl), max(x["gain"] for x in tl)))

    if a.dry:
        print("（dry，不写文件）")
        return 0

    with wave.open(a.out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR_OUT)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    tp = a.timeline or (os.path.splitext(a.out)[0] + ".timeline.json")
    json.dump(tl, open(tp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s 和 %s" % (a.out, tp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
