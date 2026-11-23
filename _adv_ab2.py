# -*- coding: utf-8 -*-
"""_adv_ab2.py —— 给「判据灰区」的几条做原版 vs 重生 A/B 试听页（单文件、内嵌 MP3）。

挑选规则：原版 margin < 1.15（FLAT + MID + 勉强 STRONG）的单元，
每条取重生版里 margin 最高的一版做对照。
页面上把两轴实测值都写出来，方便边听边对数字。
"""
import base64
import glob
import json
import os
import subprocess
import sys

ROOT = "G:/_setup"
OUT = os.path.join(ROOT, "_adv_ab2")
FF = "E:/tool/oopz/ffmpeg.exe"
TMP = os.path.join(OUT, "mp3")


def to_mp3(wav, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        return True
    r = subprocess.run([FF, "-y", "-v", "error", "-i", wav, "-ac", "1", "-ar", "44100",
                        "-b:a", "64k", dst], capture_output=True)
    return os.path.exists(dst) and os.path.getsize(dst) > 1000


def b64(p):
    return "data:audio/mpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()


def main():
    orig = json.load(open(os.path.join(ROOT, "_adv_prom_orig.json"), encoding="utf-8"))["rows"]
    reg = json.load(open(os.path.join(ROOT, "_adv_prom_regen.json"), encoding="utf-8"))["rows"]
    best_reg = {}
    for r in reg:
        if r["verdict"] in ("UNMEASURED", "NO_AUDIO"):
            continue
        if r["uid"] not in best_reg or r["margin"] > best_reg[r["uid"]]["margin"]:
            best_reg[r["uid"]] = r

    pick = [r for r in orig if r.get("margin", 0) < 1.15 and r["verdict"] != "UNMEASURED"]
    pick.sort(key=lambda r: r["margin"])

    st = json.load(open(os.path.join(ROOT, "_mt_adv_state.json"), encoding="utf-8"))["units"]
    wavmap = {}
    for f in glob.glob(os.path.join(ROOT, "_mt_raw_s*", "*.wav")):
        u = os.path.basename(f)[:-4]
        d = os.path.basename(os.path.dirname(f))
        rank = 0 if d.endswith("s1234") else 1
        if u not in wavmap or rank < wavmap[u][0]:
            wavmap[u] = (rank, f)
    regdir = {"2025": "_mt_adv_s2025", "2027": "_mt_adv_s2027", "2029": "_mt_adv_s2029"}

    cards = []
    for r in pick:
        u = r["uid"]
        if u not in wavmap:
            continue
        a_mp3 = os.path.join(TMP, "%s_orig.mp3" % u)
        if not to_mp3(wavmap[u][1], a_mp3):
            continue
        takes = [("原版", a_mp3, r)]
        br = best_reg.get(u)
        if br:
            w = os.path.join(ROOT, regdir[br["set"]], u + ".wav")
            if os.path.exists(w):
                b_mp3 = os.path.join(TMP, "%s_s%s.mp3" % (u, br["set"]))
                if to_mp3(w, b_mp3):
                    takes.append(("重生 s" + br["set"], b_mp3, br))
        cards.append(dict(uid=u, text=st[u]["text"], adv=r["adv"], takes=takes))

    def num(v, suf=""):
        return "—" if v is None else ("%+.2f%s" % (v, suf) if isinstance(v, float) else str(v))

    rows_html = []
    for c in cards:
        aud = []
        for name, p, r in c["takes"]:
            aud.append("""
      <div class="take">
        <div class="tk-h"><b>%s</b>
          <span class="badge %s">%s</span></div>
        <div class="tk-n">loc %s 半音 · dur_z %s σ · margin %s</div>
        <audio controls preload="none" src="%s"></audio>
      </div>""" % (name, r["verdict"].lower(), r["verdict"],
                   num(r.get("loc")), num(r.get("dur_z")), r.get("margin"), b64(p)))
        rows_html.append("""
  <section class="card">
    <div class="hd"><span class="uid">%s</span><span class="adv">%s</span></div>
    <div class="txt">%s</div>
    <div class="takes">%s</div>
  </section>""" % (c["uid"], c["adv"], c["text"].replace("<", "&lt;"), "".join(aud)))

    html = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>副词灰区 A/B 试听</title>
<style>
:root{--bg:#f6f7f9;--fg:#1b1f24;--mut:#5f6b7a;--line:#e2e6ec;--card:#fff;
--ok:#197a4b;--mid:#9a6b00;--flat:#b03030;}
@media(prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e8ecf2;--mut:#93a0b0;
--line:#2a313a;--card:#1b1f26;--ok:#4cc38a;--mid:#e0a83a;--flat:#ef6b6b;}}
*{box-sizing:border-box}
body{margin:0;padding:28px 18px 60px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,"Segoe UI",system-ui,"Microsoft YaHei",sans-serif}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:19px;margin:0 0 6px}
.lead{color:var(--mut);font-size:13.5px;margin:0 0 22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 16px;margin:0 0 14px}
.hd{display:flex;gap:10px;align-items:center;margin-bottom:6px}
.uid{font:600 12.5px/1 ui-monospace,Consolas,monospace;color:var(--mut);
letter-spacing:.04em}
.adv{font-weight:700;font-size:15px}
.txt{color:var(--mut);font-size:13px;margin-bottom:10px;word-break:break-word}
.takes{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:640px){.takes{grid-template-columns:1fr}}
.take{border:1px solid var(--line);border-radius:9px;padding:9px 11px}
.tk-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}
.tk-n{font:11.5px/1.4 ui-monospace,Consolas,monospace;color:var(--mut);margin-bottom:6px}
badge,.badge{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11px;
font-weight:600;border:1px solid currentColor}
.badge.strong{color:var(--ok)}.badge.mid{color:var(--mid)}.badge.flat{color:var(--flat)}
audio{width:100%%;height:32px}
</style></head><body><div class="wrap">
<h1>副词灰区 A/B 试听</h1>
<p class="lead">只放原版 margin &lt; 1.15 的条目（FLAT / MID / 勉强 STRONG），
有重生版的并列对照。判据只看两个物理量：<code>loc</code> 是 F0 峰相对本地上下文的半音数（≥2 可听），
<code>dur_z</code> 是每音节时长相对「同音节数应有值」的 σ 偏差（≥+1 明显更慢）。</p>
@ROWS@
</div></body></html>""".replace("%", "%%").replace("@ROWS@", "".join(rows_html)).replace("%%", "%")

    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "试听-灰区13条.html")
    open(p, "w", encoding="utf-8").write(html)
    print("卡片 %d 条，字节 %.1f KB → %s" % (len(cards), os.path.getsize(p) / 1024.0, p))
    for c in cards:
        print("  %s %-13s %s" % (c["uid"], c["adv"],
                                 " / ".join(t[0] + " " + t[2]["verdict"] for t in c["takes"])))


if __name__ == "__main__":
    main()
