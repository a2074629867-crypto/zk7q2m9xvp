# -*- coding: utf-8 -*-
"""cut_cues.py —— 从「视频 + 字幕」批量切出每句台词的音频。

给谁用：剪辑外语视频、建声纹参考库、做逐句语音分析。

一条命令：
    python cut_cues.py --video film.mkv --srt film.srt --out work/cues

产物：
    work/cues/cues.json        每句的 i / t0 / t1 / dur / text / multi / sfx / path
    work/cues/c000_0021.2_0025.3.wav

三条规则（都是踩过坑写进去的）
------------------------------
1. `-` 开头 = 换说话人 → multi=True。这类 cue 是双人对白，
   **不能当声纹参考**（实测把混人 cue 当参考，四个模型全部 5/8）。
2. 文本含 `(...)` 是音效/非台词 → sfx=True，同样不能当参考。
3. 前后各留余量：pad0=0.12s 防吞首音，pad1=0.20s 防吞尾音。
   不留余量时首字爆音、末字被切是常态。

字幕兼容：BOM / CRLF / 多行 cue / `<i>` 等标签 / 花括号注释 /
         `HH:MM:SS,mmm` 与 `HH:MM:SS.mmm` 与 `MM:SS,mmm`
"""
import argparse
import json
import os
import re
import subprocess
import sys

FF = "E:/tool/oopz/ffmpeg.exe"      # 本机 ffmpeg；不在 PATH 时改这里或用 --ffmpeg

TAG = re.compile(r"<[^>]+>|\{[^}]*\}")
TIME = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
TIME_SHORT = re.compile(r"^(\d{1,2}):(\d{2})[,.](\d{1,3})$")


def _t(s):
    """时间码 → 秒。兼容 HH:MM:SS,mmm / HH:MM:SS.mmm / MM:SS,mmm"""
    s = s.strip()
    m = TIME.search(s)
    if m:
        h, mi, se, ms = m.groups()
        return int(h) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000.0
    m = TIME_SHORT.match(s)
    if m:
        mi, se, ms = m.groups()
        return int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000.0
    return None


END_PUNCT = re.compile(r"[.?!…:;»\"']\s*$")
# 句中说话人切换：句末标点之后紧跟 `-XXXX`（法语片常见 ". -Mais non"，英文 ". - Hello"）
MID_DASH = re.compile(r"[.!?…]\s*-\s*\S")


def merge_fragments(cues, max_gap=0.45, max_dur=12.0, max_chain=3):
    """把被字幕断行切碎的同一句话合回一条。

    字幕习惯把一句台词折成 2–3 条 cue（时间紧邻、前条不以句末标点结尾），
    例如 "and being paid every" + "week, not to worry about."。
    直接按 cue 切会得到碎片音频 —— 声纹判不准、TTS 也会按碎片表演（用户明确
    要求不许拆句）。判据刻意保守：紧邻 + 前条无句末标点 + 后条不是新说话人
    （`-`）+ 两条都非多人 + 合并后不超长 + 最多连并 3 条。
    """
    out = []
    for c in cues:
        if out:
            p = out[-1]
            gap = c["t0"] - p["t1"]
            ok = (gap <= max_gap
                  and not END_PUNCT.search(p["text"])
                  and not c["text"].lstrip().startswith("-")
                  and not p["multi"] and not c["multi"]
                  and p.get("_chain", 1) < max_chain
                  and (c["t1"] - p["t0"]) <= max_dur)
            if ok:
                p["t1"] = c["t1"]
                p["dur"] = round(p["t1"] - p["t0"], 3)
                p["text"] = (p["text"] + " " + c["text"]).strip()
                p["_chain"] = p.get("_chain", 1) + 1
                continue
        c["_chain"] = 1
        out.append(c)
    for i, c in enumerate(out):
        c["i"] = i
        c.pop("_chain", None)
    return out


def parse_srt(path):
    raw = open(path, "r", encoding="utf-8-sig", errors="replace").read()
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        a, b = lines[ti].split("-->")[:2]
        t0, t1 = _t(a), _t(b)
        if t0 is None or t1 is None or t1 <= t0:
            continue
        body_lines = [TAG.sub("", l).strip() for l in lines[ti + 1:]]
        body_lines = [l for l in body_lines if l]
        if not body_lines:
            continue
        body = " ".join(body_lines).strip()
        cues.append({"t0": round(t0, 3), "t1": round(t1, 3), "text": body,
                     "_lines": body_lines})
    cues.sort(key=lambda c: c["t0"])
    for i, c in enumerate(cues):
        c["i"] = i
        c["dur"] = round(c["t1"] - c["t0"], 3)
        # `-` = 说话人分隔符。必须在 join 前按行判（join 之后行首 `-` 变成句中，
        # 只看开头会漏掉 64/403 条双人对白 —— 实测旧版就漏了，把混人 cue 当单人 ref）。
        # 「空格 + 连字符」判据不会误伤法语连字符：c'est-à-dire / peut-être 都没有空格。
        bl = c.pop("_lines")
        n_start = sum(1 for l in bl if l.lstrip().startswith("-"))
        n_mid = len(MID_DASH.findall(c["text"]))
        # `-` 在不同字幕组的含义不一样，判据必须同时兼容：
        #   法语片（城堡之王）：`-` 是「新说话人开始」，一个 cue 内只有一个 = 单人，
        #       两条以上 = 双人。原判据只要看到 `-` 就标 multi，过度标记 118/403。
        #   英语片（Careful）：`-` 只是「这是对白」的标记，1478 条里 697 条以此开头，
        #       真正双人只有 9 条。原判据标了 708 条 —— 用 --only-single 会把可用素材
        #       从 770 砍到 62，等于把片子废掉。
        # 现判据：句中切换（标点后 `-`）→ 必定双人；或标记总数 ≥2 → 双人。
        c["multi"] = n_mid >= 1 or (n_start + n_mid) >= 2
        c["sfx"] = c["text"].startswith("(") or c["text"].startswith("[")
    return cues


def cut(video, t0, t1, dst, pad0, pad1, ffmpeg=FF):
    a = max(0.0, t0 - pad0)
    b = t1 + pad1
    cmd = [ffmpeg, "-y", "-v", "quiet", "-ss", "%.3f" % a, "-t", "%.3f" % (b - a),
           "-i", video, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst]
    subprocess.run(cmd, capture_output=True)
    return os.path.exists(dst) and os.path.getsize(dst) > 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="源视频（mkv/mp4/...，也要能直接是音频）")
    ap.add_argument("--srt", required=True, help="字幕文件")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--min-dur", type=float, default=1.0)
    ap.add_argument("--max-dur", type=float, default=12.0)
    ap.add_argument("--pad0", type=float, default=0.12, help="前留余量（秒），防吞首音")
    ap.add_argument("--pad1", type=float, default=0.20, help="后留余量（秒），防吞尾音")
    ap.add_argument("--only-single", action="store_true", help="只切非多人的 cue（建 ref 库时用）")
    ap.add_argument("--merge-frag", action="store_true",
                    help="合并被字幕断行切碎的同一句（紧邻 + 前条无句末标点 + 不换人）")
    ap.add_argument("--ffmpeg", default=FF)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    cues = parse_srt(a.srt)
    if not cues:
        sys.exit("字幕解析为空：%s" % a.srt)

    n_merge = 0
    if a.merge_frag:
        before = len(cues)
        cues = merge_fragments(cues, max_dur=a.max_dur)
        n_merge = before - len(cues)
        print("断句合并：%d → %d 条（合掉 %d 条碎片）" % (before, len(cues), n_merge))

    todo = [c for c in cues if a.min_dur <= c["dur"] <= a.max_dur]
    if a.only_single:
        todo = [c for c in todo if not c["multi"]]

    n_multi = sum(1 for c in cues if c["multi"])
    n_sfx = sum(1 for c in cues if c["sfx"])
    print("解析 %d 条 cue（%.1f–%.1fs）" % (len(cues), cues[0]["t0"], cues[-1]["t1"]))
    print("  多人对白 %d（%.0f%%）  音效标注 %d  时长合格 %d" %
          (n_multi, 100 * n_multi / len(cues), n_sfx, len(todo)))
    if n_multi > len(cues) * 0.4:
        print("  ⚠ 多人对白占比高，建 ref 库务必 --only-single")

    done = []
    for i, c in enumerate(todo):
        dst = os.path.join(a.out, "c%03d_%07.1f_%07.1f.wav" % (c["i"], c["t0"], c["t1"]))
        if not (os.path.exists(dst) and os.path.getsize(dst) > 1000):
            if not cut(a.video, c["t0"], c["t1"], dst, a.pad0, a.pad1, a.ffmpeg):
                continue
        done.append(dict(c, path=dst))
        if (i + 1) % 50 == 0:
            print("  %d/%d" % (i + 1, len(todo)), flush=True)

    idx = os.path.join(a.out, "cues.json")
    json.dump(done, open(idx, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    clean = [r for r in done if not r["multi"] and not r["sfx"]]
    print("切出 %d 条 -> %s" % (len(done), a.out))
    print("可直接当 ref 候选的（非多人 / 非音效）: %d" % len(clean))
    print("索引 -> %s" % idx)


if __name__ == "__main__":
    main()
