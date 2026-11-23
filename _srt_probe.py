# -*- coding: utf-8 -*-
"""解析 srt，打印指定时间点附近的字幕（用于核对切点/台词/说话人）"""
import re
import sys

SRT = r"G:/NEW MOVIE/我是城堡之王/Je.suis.le.seigneur.du.chateau.1989.WEB-DL.1080p.FR.srt"


def ts(s):
    m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", s.strip())
    if not m:
        return None
    h, mi, se, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")[:3]) / 1000.0


def load():
    raw = open(SRT, encoding="utf-8-sig").read().replace("\r\n", "\n")
    out = []
    for blk in raw.split("\n\n"):
        lines = [l for l in blk.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        i = 0
        if re.fullmatch(r"\d+", lines[0].strip()):
            i = 1
        if i >= len(lines) or "-->" not in lines[i]:
            continue
        a, b = lines[i].split("-->")
        t0, t1 = ts(a), ts(b)
        if t0 is None or t1 is None:
            continue
        out.append((t0, t1, " / ".join(lines[i + 1:])))
    return out


def fmt(t):
    return "%02d:%02d:%06.3f" % (int(t // 3600), int(t % 3600 // 60), t % 60)


def main():
    subs = load()
    points = [float(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else []
    if not points:
        print("共 %d 条字幕" % len(subs))
        return
    for p in points:
        print("=" * 70)
        print("时间点 %s" % fmt(p))
        for t0, t1, txt in subs:
            if t1 < p - 12 or t0 > p + 12:
                continue
            mark = " <<<" if t0 <= p <= t1 else ""
            print("  %s - %s  %s%s" % (fmt(t0), fmt(t1), txt, mark))


if __name__ == "__main__":
    main()
