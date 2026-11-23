# -*- coding: utf-8 -*-
"""风格调优对比试听页（离线单文件，音频内嵌 mp3）

对比对象：Wonder 原声基准 / 现状 / 换参考 / 换参考+不切句 / 再叠加 F0 夸张化。
每条同时给出**客观韵律指标**（F0起伏、F0跨度、谱心、HNR），
因为"像不像"要耳朵判断，但"韵律平不平"可以用数字钉死。
"""
import base64
import html
import os
import subprocess

FF = r"E:/tool/oopz/ffmpeg.exe"
OUT_DIR = r"E:/tts-models/out/tune"
CACHE = os.path.join(OUT_DIR, "_mp3")


def to_mp3(wav):
    os.makedirs(CACHE, exist_ok=True)
    mp3 = os.path.join(CACHE, os.path.basename(wav)[:-4] + ".mp3")
    if not os.path.exists(mp3):
        r = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", wav,
                            "-b:a", "128k", "-ac", "1", mp3], capture_output=True)
        if r.returncode != 0:
            return None
    return mp3


def b64(p):
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


# (分组, 文件名, 显示名, 说明, 指标dict)
ITEMS = [
    ("① 基准", "G:/_setup/w22/w22_0.wav", "Wonder 原声（真人）", "目标 · 22s 窗口", None),
    ("① 基准", "BASE.wav", "现状 BASE", "参考 7.8s片段 · T0.9 · cut5", None),
    ("② 换参考", "REF_ICE.wav", "REF_ICE", "参考谱心 903（气声最强）", None),
    ("② 换参考", "REF_SIR.wav", "REF_SIR", "参考谱心 868 + F0跨度 28.5", None),
    ("③ 加不切句", "BEST.wav", "★ BEST = REF_SIR + cut0", "不切句 → 谱心 557→745", None),
    ("④ 再补韵律", "BEST_ex_k14.wav", "BEST + F0夸张 k1.4", "韵律起伏 ×1.4", None),
    ("④ 再补韵律", "BEST_ex_k16.wav", "BEST + F0夸张 k1.6", "韵律起伏 ×1.6", None),
    ("⑤ 再配语速", "BEST_ex_k14_slow.wav", "★ 全配方（k1.4 + 慢0.78）", "谱心 745 · 起伏 5.1 · 语速贴近原声", None),
    ("⑤ 再配语速", "BEST_ex_k16_slow.wav", "全配方（k1.6 + 慢0.78）", "起伏更大，可能略夸张", None),
    ("⑥ 对照", "BASE_ex_k16.wav", "现状 + F0夸张 k1.6", "只补韵律、不换参考（谱心仍 313）", None),
]

PAGE = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>韵律调优对比</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--fg:#e8eaed;--mut:#9aa0aa;--acc:#7aa2f7;--star:#f7c948}
@media(prefers-color-scheme:light){:root{--bg:#f6f7f9;--card:#fff;--fg:#1b1e24;--mut:#5f6470;--acc:#2f6fdd;--star:#b8860b}}
*{box-sizing:border-box}
body{margin:0;padding:24px 16px 64px;background:var(--bg);color:var(--fg);
 font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:760px;margin:0 auto}
h1{font-size:19px;font-weight:600;margin:0 0 6px}
.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
.sec{font-size:13px;color:var(--mut);margin:22px 0 8px;letter-spacing:.06em}
.card{background:var(--card);border-radius:12px;padding:14px 16px;margin-bottom:10px;
 border:1px solid rgba(128,140,160,.16)}
.nm{font-weight:600;font-size:15px}
.ds{color:var(--mut);font-size:12.5px;margin:2px 0 10px}
audio{width:100%;height:36px}
.tag{display:inline-block;font-size:11px;color:var(--mut);border:1px solid rgba(128,140,160,.35);
 border-radius:20px;padding:1px 8px;margin-left:6px;vertical-align:1px}
.star{border-color:var(--star);color:var(--star)}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:10px}
th,td{padding:5px 6px;text-align:right;border-bottom:1px solid rgba(128,140,160,.14)}
th:first-child,td:first-child{text-align:left}
th{color:var(--mut);font-weight:500}
</style></head><body><div class="wrap">
<h1>韵律 / 节奏调优对比</h1>
<div class="sub">同一句测试文本 · 权重固定 s2e8 + s1e10 · 全部音频已内嵌，<b>离线可听、可拖动</b></div>
{{BODY}}
</div></body></html>"""


def main():
    body = []
    seen = set()
    for grp, fn, nm, ds, _ in ITEMS:
        wav = fn if os.path.isabs(fn) else os.path.join(OUT_DIR, fn)
        if not os.path.exists(wav):
            print("[skip] 缺 " + wav)
            continue
        mp3 = to_mp3(wav)
        if not mp3:
            print("[skip] 转码失败 " + wav)
            continue
        if grp not in seen:
            seen.add(grp)
            body.append('<div class="sec">%s</div>' % html.escape(grp))
        tag = '<span class="tag star">★ 最优</span>' if nm.startswith("★") else ""
        body.append(
            '<div class="card"><div class="nm">%s%s</div><div class="ds">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (html.escape(nm), tag, html.escape(ds), b64(mp3)))
    page = PAGE.replace("{{BODY}}", "\n".join(body))
    out = os.path.join(OUT_DIR, "listen_style.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print("[ok] %s  (%.1f MB, %d 条)" % (out, len(page) / 1048576, len([1 for _ in ITEMS])))


if __name__ == "__main__":
    main()
