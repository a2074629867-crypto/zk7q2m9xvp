# -*- coding: utf-8 -*-
"""_adv_watch.py —— 生成「送听清单」页面：WATCH 项的内嵌 MP3 试听页。

回环的最后一环是人耳。声学指标只负责把可疑项排到前面，
所以每条只回答一件事：这个副词在你的耳朵里够不够。

读 `_mt_adv_state.json` 里的 judge/m2，抽 WATCH，音频取当前交付版 `_mt_pick`。
"""
import base64
import json
import os
import subprocess

ROOT = "G:/_setup"
OUT = os.path.join(ROOT, "_adv_ab2")
FF = "E:/tool/oopz/ffmpeg.exe"
TMP = os.path.join(OUT, "mp3")


def to_mp3(wav, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        return True
    subprocess.run([FF, "-y", "-v", "error", "-i", wav, "-ac", "1", "-ar", "44100",
                    "-b:a", "64k", dst], capture_output=True)
    return os.path.exists(dst) and os.path.getsize(dst) > 1000


def b64(p):
    return "data:audio/mpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()


def main():
    us = json.load(open(os.path.join(ROOT, "_mt_adv_state.json"), encoding="utf-8"))["units"]
    pick = []
    for u, x in us.items():
        if x.get("judge") != "WATCH":
            continue
        w = os.path.join(ROOT, "_mt_pick", u + ".wav")
        if not os.path.exists(w):
            continue
        m = x.get("m2") or {}
        pick.append((m.get("loc") if m.get("loc") is not None else -99, u, x, w))
    pick.sort()

    cards = []
    for _loc, u, x, w in pick:
        p = os.path.join(TMP, "%s_now.mp3" % u)
        if not to_mp3(w, p):
            continue
        m = x.get("m2") or {}
        cards.append(dict(uid=u, adv=x["adv"], text=x["text"], m=m,
                          audio=b64(p), by=x.get("judge_by")))

    def fmt(v, unit=""):
        return "—" if v is None else ("%+.2f%s" % (v, unit) if isinstance(v, float) else str(v))

    html_cards = []
    for c in cards:
        html_cards.append("""
  <section class="card">
    <div class="hd"><span class="uid">%s</span><span class="adv">%s</span>
      <span class="badge">%s</span></div>
    <div class="txt">%s</div>
    <div class="num">loc %s 半音 · dur_z %s σ · voiced %s s</div>
    <audio controls preload="none" src="%s"></audio>
  </section>""" % (c["uid"], c["adv"], c["by"] or "WATCH",
                   c["text"].replace("<", "&lt;"),
                   fmt(c["m"].get("loc")), fmt(c["m"].get("dur_z")),
                   fmt(c["m"].get("voiced")), c["audio"]))

    tpl = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>副词送听清单</title>
<style>
:root{--bg:#f6f7f9;--fg:#1b1f24;--mut:#5f6b7a;--line:#e2e6ec;--card:#fff;--acc:#8a5a00;}
@media(prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e8ecf2;--mut:#93a0b0;
--line:#2a313a;--card:#1b1f26;--acc:#e0a83a;}}
*{box-sizing:border-box}
body{margin:0;padding:28px 18px 60px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,"Segoe UI",system-ui,"Microsoft YaHei",sans-serif}
.wrap{max-width:820px;margin:0 auto}
h1{font-size:19px;margin:0 0 6px}
.lead{color:var(--mut);font-size:13.5px;margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:13px 16px;margin:0 0 13px}
.hd{display:flex;gap:10px;align-items:center;margin-bottom:5px}
.uid{font:600 12.5px/1 ui-monospace,Consolas,monospace;color:var(--mut);letter-spacing:.04em}
.adv{font-weight:700;font-size:15px}
.badge{margin-left:auto;font-size:11px;font-weight:600;color:var(--acc);
border:1px solid currentColor;border-radius:99px;padding:1px 8px}
.txt{color:var(--mut);font-size:13px;margin-bottom:6px;word-break:break-word}
.num{font:11.5px/1.4 ui-monospace,Consolas,monospace;color:var(--mut);margin-bottom:7px}
audio{width:100%;height:32px}
.foot{color:var(--mut);font-size:12.5px;margin-top:22px;border-top:1px solid var(--line);padding-top:12px}
</style></head><body><div class="wrap">
<h1>副词送听清单（WATCH %d 条）</h1>
<p class="lead">这些是「F0 平淡」的条目 —— <b>平淡不等于不合格</b>。
判据只把可疑项排到前面，够不够由你的耳朵定。按 loc 从低到高排。</p>
@ROWS@
<p class="foot">口径：loc ≥ 2.0 半音 = 可听的音高重音。
低于这个值只说明「没有明显的音高重音」，不代表读错了 ——
N0063 就是 loc 只有 +1.05 但你听过说没毛病，已锁为 LOCKED，不在本清单里。</p>
</div></body></html>"""

    html = tpl.replace("%d", str(len(cards)), 1).replace("@ROWS@", "".join(html_cards))
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "送听清单-WATCH.html")
    open(p, "w", encoding="utf-8").write(html)
    print("卡片 %d 条，%.1f KB → %s" % (len(cards), os.path.getsize(p) / 1024.0, p))
    for c in cards:
        print("  %-8s %-13s loc=%s" % (c["uid"], c["adv"], c["m"].get("loc")))


if __name__ == "__main__":
    main()
