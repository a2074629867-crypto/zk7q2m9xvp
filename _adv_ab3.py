# -*- coding: utf-8 -*-
"""_adv_ab3.py —— 本轮「WATCH 重生」A/B 试听页（单文件、内嵌 MP3）。

三列结构：**原版（替换前交付）→ 已采纳版（现在的交付）→ 其余 take**。
原版音频从 `_mt_raw_*` 取，用的是 `_mt_proc` 缓存键里反查出的真实血缘
（缓存键格式 `uid_size_mtime_tempo`，size 与 raw 文件逐一比对）。
替换前的 loc 值来自采纳前那次 --report 的输出，作为基准写死在 PRE 里。
"""
import base64
import json
import os
import subprocess

ROOT = "G:/_setup"
STATE = os.path.join(ROOT, "_mt_adv_state.json")
OUT = os.path.join(ROOT, "_adv_ab3")
FF = "E:/tool/oopz/ffmpeg.exe"
TMP = os.path.join(OUT, "mp3")
SEEDS = {"2031", "2033", "2035"}

# uid: (原版所在 raw 目录, 替换前 loc, 采纳的 seed 或 None)
PRE = {
    "N0301": ("s42", 1.33, "2031"),
    "N0480": ("s42", 0.64, "2031"),
    "N0602": ("s1234", 1.84, "2031"),
    "N0634": ("s42", 0.35, "2035"),
    "N0666": ("s42", 1.68, "2031"),
    "N0824": ("s42", 4.56, None),   # 退路分支修好后本来就达标，未替换
    "N0219": ("s42", 0.90, None),   # 三轮全部换人，未替换
    "N0627": ("s42", -0.74, None),  # 最好只到 +1.87，未替换
}


def to_mp3(wav, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        return True
    subprocess.run([FF, "-y", "-v", "error", "-i", wav, "-ac", "1", "-ar", "44100",
                    "-b:a", "64k", dst], capture_output=True)
    return os.path.exists(dst) and os.path.getsize(dst) > 1000


def b64(p):
    return "data:audio/mpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()


def fnum(v, suf=""):
    if v is None:
        return "—"
    return ("%+.2f%s" % (v, suf)) if isinstance(v, float) else str(v)


def main():
    st = json.load(open(STATE, encoding="utf-8"))["units"]
    cards = []
    for u, (raw, pre_loc, adopted) in PRE.items():
        x = st[u]
        takes = []
        org = os.path.join(ROOT, "_mt_raw_" + raw, u + ".wav")
        if not os.path.exists(org):
            print("!! 缺原版 %s" % org)
            continue
        p = os.path.join(TMP, "%s_orig.mp3" % u)
        if to_mp3(org, p):
            takes.append(dict(name="原版（替换前）", loc=pre_loc, dur_z=None, spk=None,
                              tag="orig", mp3=p))
        cur = os.path.join(ROOT, "_mt_pick", u + ".wav")
        if adopted and os.path.exists(cur):
            p = os.path.join(TMP, "%s_cur.mp3" % u)
            m2 = x.get("m2") or {}
            if to_mp3(cur, p):
                takes.append(dict(name="已采纳 s%s" % adopted, loc=m2.get("loc"),
                                  dur_z=m2.get("dur_z"),
                                  spk=(x.get("active") or {}).get("spk"),
                                  tag="cur", mp3=p))
        for z in sorted(x.get("attempts") or [], key=lambda t: str(t.get("seed"))):
            sd = str(z.get("seed"))
            if sd not in SEEDS or (adopted and sd == adopted):
                continue
            w = z.get("wav")
            if not w or not os.path.exists(w):
                continue
            p = os.path.join(TMP, "%s_s%s.mp3" % (u, sd))
            if not to_mp3(w, p):
                continue
            takes.append(dict(name="s%s" % sd, loc=z.get("loc"), dur_z=z.get("dur_z"),
                              spk=z.get("spk"), tag=z.get("judge") or "take", mp3=p))
        cards.append(dict(uid=u, text=x["text"], adv=x["adv"], takes=takes))

    print("%-7s %-12s %s" % ("uid", "adv", "takes"))
    for c in cards:
        print("%-7s %-12s %s" % (c["uid"], c["adv"],
                                 "  ".join("%s[%s]" % (t["name"], fnum(t["loc"])) for t in c["takes"])))

    blocks = []
    for c in cards:
        aud = []
        for i, t in enumerate(c["takes"]):
            if t["tag"] == "orig":
                lab, cls = "基准", "warn"
            elif t["tag"] == "cur":
                lab, cls = "已采纳", "ok"
            elif t["tag"] == "PASS":
                lab, cls = "达标", "ok"
            elif t["tag"] == "FIX":
                lab, cls = "换人", "bad"
            else:
                lab, cls = "平淡", "warn"
            aud.append("""
      <div class="take%s">
        <div class="tk-h"><b>%s</b><span class="badge %s">%s</span></div>
        <div class="tk-n">loc %s 半音 · dur_z %s σ · 声纹 %s</div>
        <audio controls preload="none" src="%s"></audio>
      </div>""" % (" first" if i == 0 else "", t["name"], cls, lab,
                   fnum(t["loc"]), fnum(t["dur_z"]),
                   "—" if t["spk"] is None else "%.3f" % t["spk"], b64(t["mp3"])))
        blocks.append("""
  <section class="card">
    <div class="hd"><span class="uid">%s</span><span class="adv">%s</span></div>
    <div class="txt">%s</div>
    <div class="takes">%s</div>
  </section>""" % (c["uid"], c["adv"], c["text"].replace("<", "&lt;"), "".join(aud)))

    html = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>副词 WATCH 重生 A/B</title>
<style>
:root{--bg:#f6f7f9;--fg:#1b1f24;--mut:#5f6b7a;--line:#e2e6ec;--card:#fff;
--ok:#197a4b;--warn:#9a6b00;--bad:#b03030;}
@media(prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e8ecf2;--mut:#93a0b0;
--line:#2a313a;--card:#1b1f26;--ok:#4cc38a;--warn:#e0a83a;--bad:#ef6b6b;}}
*{box-sizing:border-box}
body{margin:0;padding:28px 18px 60px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,"Segoe UI",system-ui,"Microsoft YaHei",sans-serif}
.wrap{max-width:1120px;margin:0 auto}
h1{font-size:19px;margin:0 0 6px}
.lead{color:var(--mut);font-size:13.5px;margin:0 0 6px}
.lead code{background:rgba(127,127,127,.14);padding:1px 5px;border-radius:4px}
.tip{color:var(--mut);font-size:12.5px;margin:0 0 22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 16px;margin:0 0 14px}
.hd{display:flex;gap:10px;align-items:center;margin-bottom:6px}
.uid{font:600 12.5px/1 ui-monospace,Consolas,monospace;color:var(--mut);letter-spacing:.04em}
.adv{font-weight:700;font-size:15px}
.txt{color:var(--mut);font-size:13px;margin-bottom:10px;word-break:break-word}
.takes{display:flex;gap:10px;overflow-x:auto;padding-bottom:2px}
.take{flex:0 0 236px;border:1px solid var(--line);border-radius:9px;padding:9px 11px}
.take.first{background:rgba(127,127,127,.05)}
.tk-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;gap:6px}
.tk-n{font:11.5px/1.4 ui-monospace,Consolas,monospace;color:var(--mut);margin-bottom:6px}
.badge{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11px;
font-weight:600;border:1px solid currentColor;white-space:nowrap}
.badge.ok{color:var(--ok)}.badge.warn{color:var(--warn)}.badge.bad{color:var(--bad)}
audio{width:100%;height:32px}
</style></head><body><div class="wrap">
<h1>副词 WATCH 重生 A/B</h1>
<p class="lead">本轮 8 条「F0 平淡」全部重生成，seed 2031 / 2033 / 2035 各一轮，<b>文本一字未改</b>。
能替换的只有同时满足三条的：<code>loc ≥ 2.0</code>、<code>声纹 ≥ 0.65</code>、比现在更好。</p>
<p class="tip">最左边一列永远是<b>替换前</b>的版本，第二列是<b>现在实际交付</b>的版本。
只听一个判断：<b>那个副词是不是明显更重、更清楚，而且还是同一个人在念？</b>不认可就告诉我 uid，我退回去。</p>
@ROWS@
</div></body></html>""".replace("@ROWS@", "".join(blocks))

    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "试听-WATCH重生8条.html")
    open(p, "w", encoding="utf-8").write(html)
    print("\n页面 %d 条 → %s（%.1f KB）" % (len(cards), p, os.path.getsize(p) / 1024.0))


if __name__ == "__main__":
    main()
