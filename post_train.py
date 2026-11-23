# -*- coding: utf-8 -*-
"""训练完成后的一键流水线：

  1) 扫 GPT_weights_v2 / SoVITS_weights_v2，自动组 plan（官方底模 Z0 + 微调若干档）
  2) 跑 infer_compare.py 出样
  3) 说话人相似度（WeSpeaker CAM++，锚点 = 90s 干净人声）
  4) 音色分析（F0 / HNR / 频谱）
  5) 生成**离线单文件**试听页（音频 base64 内嵌，file:// 直接能听能拖）

用法：python -u post_train.py [--out E:/tts-models/out/gsv] [--keep N]
"""
import argparse
import base64
import glob
import html
import json
import os
import re
import subprocess
import sys
import time

REPO = r"G:/GPT-SoVITS"
PY = r"G:/Python310/python.exe"
# ⚠️ spk_embed.py 依赖 kaldi_native_fbank + onnxruntime，**只装在托管 venv 里**，
#    G:/Python310 里没有 → 必须用 venv 的 python，否则静默失败（踩过：解析出 0 个）
PY_VENV = r"C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
LAB = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab"
FF = r"E:/tool/oopz/ffmpeg.exe"
ANCHOR = r"E:/tts-models/refs/mcconaughey/anchor.wav"          # 90s 正常说话（F0≈124Hz）
# ★ 同源锚点：Wonder 旁白本人的声音（F0≈78Hz 气声低语），91s
#   两个锚点必须都算 —— 只用跨音区锚点会得到严重误导的低分（0.39 vs 0.84，踩过）
ANCHOR_WONDER = r"E:/tts-models/refs/mcconaughey/anchor_wonder.wav"
OLD_CHAMP = r"E:/tts-models/out/para3/P3_cb_e50_RVC_EQ.wav"   # 旧冠军（Chatterbox+RVC+EQ）
REF = r"G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0023447040_0023696640.wav"

ENV = dict(os.environ)
ENV["PATH"] = "E:/tool/oopz;" + ENV.get("PATH", "")
ENV["NLTK_DATA"] = "G:/nltk_data"
ENV["HF_HOME"] = "G:/hf_cache"
ENV["HF_ENDPOINT"] = "https://hf-mirror.com"
ENV["PYTHONUNBUFFERED"] = "1"
for k in ("http_proxy", "https_proxy"):
    ENV.pop(k, None)


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def glob_weights():
    s2 = sorted(glob.glob(os.path.join(REPO, "SoVITS_weights_v2", "*.pth")),
                key=lambda p: (int(re.search(r"_e(\d+)", p).group(1)) if re.search(r"_e(\d+)", p) else -1,
                               os.path.getmtime(p)))
    s1 = sorted(glob.glob(os.path.join(REPO, "GPT_weights_v2", "*.ckpt")),
                key=lambda p: (int(re.search(r"-e(\d+)\.", p).group(1)) if re.search(r"-e(\d+)\.", p) else -1,
                               os.path.getmtime(p)))
    return s1, s2


def build_plan(keep=2, sweep=False):
    s1, s2 = glob_weights()
    log("SoVITS 权重 %d 个: %s" % (len(s2), [os.path.basename(x) for x in s2]))
    log("GPT    权重 %d 个: %s" % (len(s1), [os.path.basename(x) for x in s1]))
    plan = [{"tag": "Z0_pretrained_zeroshot", "s1": None, "s2": None}]
    if s1 and s2:
        best2 = s2[-1]   # s2 取最后一个（epoch 最多）
        if sweep:
            # ★ 只扫 GPT 的 epoch，s2 固定在最好那档 —— 隔离"多训几个 epoch 有没有用"
            for a in s1:
                e1 = re.search(r"-e(\d+)\.", a).group(1)
                e2 = re.search(r"_e(\d+)", best2).group(1)
                plan.append({"tag": "T_s2e%s_s1e%s" % (e2, e1),
                             "s1": os.path.relpath(a, REPO).replace("\\", "/"),
                             "s2": os.path.relpath(best2, REPO).replace("\\", "/")})
        else:
            picks2 = s2[-keep:]
            picks1 = s1[-keep:]
            for a, b in zip(picks1, picks2):
                e1 = re.search(r"-e(\d+)\.", a).group(1)
                e2 = re.search(r"_e(\d+)", b).group(1)
                plan.append({"tag": "T_s2e%s_s1e%s" % (e2, e1),
                             "s1": os.path.relpath(a, REPO).replace("\\", "/"),
                             "s2": os.path.relpath(b, REPO).replace("\\", "/")})
    return plan


def run(cmd, logpath=None, timeout=None):
    log("> " + " ".join(cmd[:6]) + (" ..." if len(cmd) > 6 else ""))
    if logpath:
        with open(logpath, "w", encoding="utf-8", errors="ignore") as f:
            p = subprocess.run(cmd, cwd=REPO, env=ENV, stdout=f,
                               stderr=subprocess.STDOUT, timeout=timeout)
        txt = open(logpath, encoding="utf-8", errors="ignore").read()
    else:
        p = subprocess.run(cmd, cwd=REPO, env=ENV, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        txt = p.stdout.decode("utf-8", "ignore")
    return p.returncode, txt


def score_sim(wavs, anchor=ANCHOR_WONDER):
    rc, txt = run([PY_VENV, "-u", os.path.join(LAB, "spk_embed.py"), "--cmn", anchor] + wavs)
    out = {}
    for ln in txt.splitlines():
        m = re.match(r"^(\S.*?\.wav)\s+([01]\.\d+)\s+(\S+)\s*$", ln.strip())
        if m:
            out[m.group(1).strip()] = (float(m.group(2)), m.group(3))
    if not out:
        print("!! 相似度解析为 0，原始输出尾部：\n" + txt[-1200:], flush=True)
    return out, txt


def score_timbre(wavs):
    rc, txt = run([PY, "-u", os.path.join(LAB, "timbre.py"), ANCHOR] + wavs)
    out = {}
    for ln in txt.splitlines():
        m = re.match(r"^(\S.*?\.wav)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(-?[\d.]+)\s*$", ln.strip())
        if m:
            out[m.group(1)] = dict(dur=float(m.group(2)), peak=float(m.group(3)), f0=float(m.group(4)),
                                   hnr=float(m.group(5)), voiced=float(m.group(6)), f0std=float(m.group(7)),
                                   f0rng=float(m.group(8)), cent=float(m.group(9)), tilt=float(m.group(10)))
    return out, txt


PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPT-SoVITS 微调 vs 零样本 — 麦康纳《Wonder》</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--line:#262a33;--fg:#e8eaed;--dim:#9aa0aa;--acc:#7cc4ff;--star:#ffd479;--ok:#6ee7a8;--bad:#ff8a8a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;padding:22px 16px 60px}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:20px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:20px}
.sub code{background:#22262e;padding:1px 5px;border-radius:4px;color:var(--acc)}
h2{font-size:15px;margin:26px 0 10px;color:var(--dim);font-weight:600;letter-spacing:.4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 15px;margin-bottom:10px;cursor:pointer;transition:.16s}
.card:hover{border-color:#3a4150}
.card.on{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc) inset}
.card.star{border-color:#6b5a2a}
.card.star.on{border-color:var(--star);box-shadow:0 0 0 1px var(--star) inset}
.tt{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.nm{font-weight:600;font-size:15px}
.tag{font-size:11px;color:var(--star);border:1px solid #6b5a2a;border-radius:99px;padding:1px 8px}
.meta{margin-top:8px;display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--dim);font-variant-numeric:tabular-nums}
.meta b{color:var(--fg);font-weight:600}
.bar{height:3px;background:#242832;border-radius:99px;margin-top:9px;overflow:hidden}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#4a8fd4,#7cc4ff)}
audio{width:100%;margin-top:11px;display:none}
.card.on audio{display:block}
.hint{color:var(--dim);font-size:12px;margin-top:6px}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:right}
th:first-child,td:first-child{text-align:left}
th{color:var(--dim);font-weight:500}
details{margin-top:18px}
summary{cursor:pointer;color:var(--dim);font-size:13px}
pre{background:#14171d;border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;font-size:11.5px;line-height:1.5;max-height:420px}
</style></head><body><div class="wrap">
<h1>GPT-SoVITS 微调 vs 零样本</h1>
<div class="sub">音色：Matthew McConaughey（Calm《Wonder》睡前故事 21 分钟） ·
测试文本与 P1~P4 <b>完全相同</b> · 参考音频 <code>{{REFNAME}}</code>（{{REFDUR}}s）<br>
所有音频已内嵌，<b>离线可听、可拖动</b>。</div>
{{BODY}}
</div>
<script>
var cards=[].slice.call(document.querySelectorAll('.card'));
cards.forEach(function(c){
  var a=c.querySelector('audio');
  c.addEventListener('click',function(e){
    if(e.target.tagName==='AUDIO')return;
    var wasOn=c.classList.contains('on');
    cards.forEach(function(o){o.classList.remove('on');o.querySelector('audio').pause();});
    if(!wasOn){c.classList.add('on');a.play();}
  });
});
</script></body></html>
"""


def wav_b64(p):
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def to_mp3(wav, cache_dir):
    """wav 太大，试听页内嵌用 128k mp3（页面从几十 MB 降到几 MB）"""
    os.makedirs(cache_dir, exist_ok=True)
    mp3 = os.path.join(cache_dir, os.path.splitext(os.path.basename(wav))[0] + ".mp3")
    if os.path.exists(mp3) and os.path.getmtime(mp3) >= os.path.getmtime(wav):
        return mp3
    r = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", wav,
                        "-c:a", "libmp3lame", "-b:a", "128k", mp3], capture_output=True)
    if r.returncode != 0:
        print("!! mp3 转码失败 %s: %s" % (wav, r.stderr.decode("utf-8", "ignore")[-200:]), flush=True)
        return None
    return mp3


def build_page(out_dir, sim, tim, extra_txt, sim2=None):
    wavs = sorted(glob.glob(os.path.join(out_dir, "*.wav")))
    order = [w for w in wavs if not w.endswith("_slow80.wav")] + [w for w in wavs if w.endswith("_slow80.wav")]
    cards = []
    best = max([v[0] for v in sim.values()], default=0)
    for p in order:
        b = os.path.basename(p)
        s, verdict = sim.get(b, (None, None))
        t = tim.get(b, {})
        mp3 = to_mp3(p, os.path.join(out_dir, "_mp3"))
        if mp3 is None:
            continue
        b64 = wav_b64(mp3)
        slow = b.endswith("_slow80.wav")
        nm = b[:-4].replace("_slow80", " · 0.80×")
        cls = "card"
        tags = ""
        if b.startswith("Z0"):
            tags = '<span class="tag" style="color:#9aa0aa;border-color:#3a4150">没训练 · 零样本</span>'
        else:
            cls += " star"
            tags = '<span class="tag">★ 微调</span>'
        if slow:
            tags += '<span class="tag" style="color:#9aa0aa;border-color:#3a4150">放慢</span>'
        meta = []
        if s is not None:
            meta.append('相似度 <b>%.4f</b> <span style="color:%s">%s</span>'
                        % (s, "var(--ok)" if s >= 0.55 else "var(--bad)", verdict))
            if best > 0:
                meta.append('<div class="bar" style="flex-basis:100%%"><i style="width:%.0f%%"></i></div>'
                            % (100.0 * s / max(best, 1e-6)))
        if t:
            meta.append("F0 <b>%.1f</b>Hz" % t.get("f0", 0))
            meta.append("HNR <b>%.2f</b>" % t.get("hnr", 0))
            meta.append("时长 <b>%.1f</b>s" % t.get("dur", 0))
        cards.append(
            '<div class="%s" data-f="%s"><div class="tt"><span class="nm">%s</span>%s</div>'
            '<div class="meta">%s</div>'
            '<audio controls preload="none" src="data:audio/mpeg;base64,%s"></audio></div>'
            % (cls, html.escape(b), html.escape(nm), tags, "".join(meta), b64))

    # 表格
    rows = ['<table><tr><th>文件</th><th>同源锚点</th><th>跨音区锚点</th><th>判定</th><th>F0</th><th>HNR</th><th>时长</th></tr>']
    for p in order:
        b = os.path.basename(p)
        s, v = sim.get(b, (None, "-"))
        s2 = (sim2 or {}).get(b, (None, "-"))[0]
        t = tim.get(b, {})
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            html.escape(b),
            ("<b>%.4f</b>" % s) if s is not None else "-",
            ("%.4f" % s2) if s2 is not None else "-",
            v or "-",
            ("%.1f" % t.get("f0", 0)) if t else "-",
            ("%.2f" % t.get("hnr", 0)) if t else "-",
            ("%.1f" % t.get("dur", 0)) if t else "-"))
    rows.append("</table>")
    rows.append('<div class="hint"><b>同源锚点</b>（91s）= Wonder 旁白本人的声音（F0≈78Hz 气声低语），'
                '这是判断"像不像这本书的朗读者"的正确尺子。'
                '<br><b>跨音区锚点</b>（90s）= 他正常说话的音区（F0≈124Hz）——'
                '训练语料与它差了将近一个音区，所以这一列整体偏低，<b>只能用来横向比，不能当绝对水平看</b>。'
                '<br>相似度 = WeSpeaker CAM++（VoxCeleb en）+ CMN 的余弦相似：'
                '&gt;0.70 同一人 / 0.55~0.70 很像 / 0.40~0.55 有点像。</div>')

    body = '<h2>一、同文本对比（点卡片播放）</h2>' + "".join(cards)
    body += '<h2>二、明细</h2>' + "".join(rows)
    body += ('<details><summary>原始日志（相似度 / 音色分析）</summary><pre>%s</pre></details>'
             % html.escape(extra_txt[-12000:]))

    refdur = 0.0
    try:
        import wave
        w = wave.open(REF)
        refdur = w.getnframes() / w.getframerate()
        w.close()
    except Exception:
        pass

    # ⚠️ 不能用 `%` 格式化：模板里的 CSS 有大量 `width:100%`，会被当成格式符
    #    （踩过：ValueError: unsupported format character ';'）
    page = (PAGE.replace("{{BODY}}", body)
                .replace("{{REFNAME}}", os.path.basename(REF))
                .replace("{{REFDUR}}", "%.2f" % refdur))
    out = os.path.join(out_dir, "listen_gsv.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    log("试听页 -> %s (%.1f MB)" % (out, os.path.getsize(out) / 1048576))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"E:/tts-models/out/gsv")
    ap.add_argument("--keep", type=int, default=2)
    ap.add_argument("--sweep", action="store_true",
                    help="扫 GPT 各 epoch（s2 固定在最后一档），隔离'多训几个 epoch 有没有用'")
    ap.add_argument("--skip-infer", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    plan = build_plan(a.keep, sweep=a.sweep)
    planp = os.path.join(r"G:/_setup", "plan.json")
    json.dump(plan, open(planp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("plan (%d 组) -> %s" % (len(plan), planp))
    for j in plan:
        log("   " + j["tag"])

    if not a.skip_infer:
        rc, txt = run([PY, "-u", r"G:/_setup/infer_compare.py", "--plan", planp, "--out", a.out],
                      logpath=os.path.join(r"G:/_setup", "infer.log"))
        log("推理退出码 %d" % rc)
        print(txt[-1500:], flush=True)

    wavs = sorted(glob.glob(os.path.join(a.out, "*.wav")))
    if not wavs:
        log("!! 没有产出音频，结束")
        return 1
    log("产出 %d 个 wav" % len(wavs))

    sim, simtxt = score_sim(wavs, ANCHOR_WONDER)
    log("同源锚点相似度算完 %d 个" % len(sim))
    sim2, sim2txt = score_sim(wavs, ANCHOR)
    log("跨音区锚点相似度算完 %d 个" % len(sim2))
    tim, timtxt = score_timbre(wavs)
    log("音色算完 %d 个" % len(tim))

    page = build_page(a.out, sim, tim, simtxt + "\n\n" + sim2txt + "\n\n" + timtxt, sim2=sim2)

    # 旧冠军一并呈现，便于 A/B
    if os.path.exists(OLD_CHAMP):
        log("旧冠军参考: %s" % OLD_CHAMP)

    log("全部完成 -> %s" % page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
