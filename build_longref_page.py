# -*- coding: utf-8 -*-
"""build_longref_page.py —— 「参考音频能多长」实验结果页（离线单文件，内嵌 MP3）"""
import base64, json, subprocess
from pathlib import Path

OUTDIR = Path(r"E:/tts-models/acpp/out/refs_long/out")
REAL = Path(r"E:/tts-models/acpp/out/calmdeep_final/real_trim.wav")
OUT = Path(r"G:/_setup/gsv5_longref_listen.html")
FF = r"E:/tool/oopz/ffmpeg.exe"

SPK = {"R08": 0.8567, "R11": 0.7951, "R15": 0.7865, "R21": 0.7333, "R28": None}
NOTE = {
    "R08": "现有最优参考，原样复现 —— 基准",
    "R11": "多了一句，输出塌缩到 10.24s",
    "R15": "再多一句，塌缩到 6.80s",
    "R21": "21.5s 反而回弹到 18.40s，但声纹掉到 0.7333 —— 仍是长参考里唯一勉强可用的",
    "R28": "彻底崩：0.72s / 13 token，只够吐一个音",
}


def b64(p: Path) -> str:
    tmp = OUT.parent / ("_lr_" + p.stem + ".mp3")
    subprocess.run([FF, "-y", "-i", str(p), "-codec:a", "libmp3lame",
                    "-b:a", "128k", "-ar", "32000", str(tmp)],
                   check=True, capture_output=True)
    s = base64.b64encode(tmp.read_bytes()).decode()
    tmp.unlink(missing_ok=True)
    return s


sweep = {r["tag"]: r for r in json.load(open(OUTDIR / "long_sweep.json", encoding="utf-8"))}
rows = []
for tag in ["R08", "R11", "R15", "R21", "R28"]:
    r = sweep.get(tag)
    if not r or "out_dur" not in r:
        continue
    outp = OUTDIR / (tag + ".wav")
    refp = Path(r["ref_path"])
    rows.append(dict(tag=tag, ref_dur=r["ref_dur"], out_dur=r["out_dur"], n=r["n"],
                     spk=SPK.get(tag), note=NOTE.get(tag, ""),
                     ref_b64=b64(refp) if refp.exists() else "",
                     out_b64=b64(outp) if outp.exists() else ""))

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>参考音频能有多长 · 实测</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--fg:#16181c;--mut:#5c6572;--line:#e2e5ea;
      --ok:#0a7d43;--bad:#c0392b;--warn:#b7791f;--acc:#1a5fb4}
@media(prefers-color-scheme:dark){:root{--bg:#131519;--card:#1b1e24;--fg:#e6e8ec;
      --mut:#98a2b3;--line:#2b3038;--ok:#3fbf7f;--bad:#e06c5a;--warn:#d9a343;--acc:#6aa6f5}}
*{box-sizing:border-box}
body{margin:0;padding:28px 20px 60px;background:var(--bg);color:var(--fg);
     font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:940px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}
.sub{color:var(--mut);font-size:13.5px;margin-bottom:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
      padding:18px 20px;margin-bottom:14px}
.rule{border-left:3px solid var(--acc);padding-left:14px;margin:18px 0}
code{background:rgba(127,127,127,.14);padding:1px 5px;border-radius:4px;font-size:12.5px}
.row{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.tag{font-weight:600;font-size:15px;min-width:56px}
.chip{font-size:12px;padding:2px 9px;border-radius:20px;border:1px solid var(--line);color:var(--mut)}
.chip.ok{color:var(--ok);border-color:var(--ok)}
.chip.bad{color:var(--bad);border-color:var(--bad)}
.chip.warn{color:var(--warn);border-color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:8px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:500;font-size:12.5px}
audio{height:32px;width:250px}
.note{color:var(--mut);font-size:12.5px;margin-top:8px}
.bar{height:7px;border-radius:4px;background:var(--line);position:relative;overflow:hidden;flex:1;min-width:120px}
.bar i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--acc)}
.bar i.bad{background:var(--bad)}
.mono{font-variant-numeric:tabular-nums}
</style></head><body><div class="wrap">
<h1>参考音频能有多长？—— 实测答案</h1>
<div class="sub">固定 GPT=v6-e18 + 零样本 s2Gv5turbo，只改参考音频长度。全部从母带 566.00s 起切，前 8.30s 与现有最优参考逐采样相同。</div>

<div class="card">
<div class="rule">
<b>官方规定：3 ~ 10 秒，硬编码。</b><br>
<code>GPT_SoVITS/TTS_infer_pack/TTS.py</code> 的 <code>_set_prompt_semantic()</code>：<br>
<code>if wav16k.shape[-1] &gt; 160000 or &lt; 48000: raise OSError("参考音频在3~10秒范围外")</code><br>
16kHz 下 160000 点 = <b>10.0 秒</b>，48000 点 = <b>3.0 秒</b>。WebUI 标签同样是「请上传3~10秒内参考音频，超过会报错！」，
Changelog 2024.01.28 commit <code>b8ae5a27</code>「排除不合理的参考音频长度」引入。
</div>
<div class="note">我们把上限改成可配置（<code>GSV_REF_MAX_SEC</code>）后，实测证明 <b>10 秒不只是 UI 限制，是真实的技术边界</b>。
下方每个长度都用同一段话递增，参考本身可以点开听。</div>
</div>

<div class="card"><table>
<tr><th>版本</th><th>参考时长</th><th>参考音频</th><th>生成成品</th><th>输出时长</th><th>token</th><th>声纹</th></tr>
__ROWS__
</table></div>

<div class="card">
<b>结论</b>
<div class="note" style="margin-top:10px;line-height:1.9">
① <b>参考越长，输出越短、音色越差</b> —— 11.9s 塌到 10.24s，15.1s 塌到 6.80s，28.2s 直接 0.72s（只够吐一个音）。<br>
② 21.5s 是唯一回弹到 18.40s 的，但声纹 0.7333 比 8.30s 的 0.8567 低 12 个点，仍不划算。<br>
③ 机制：AR 的 prefix = 文本 token + 参考语义 token。参考越长远超训练样本的常见 prefix 长度，模型开始提前收尾。<br>
④ <b>所以「参考弄长一点」这条路封死了</b>——10 秒是天花板，而现在的 8.30s 已经贴着上限。
</div>
</div>

<div class="card">
<b>顺带：官方还有一条关于参考音频的反直觉规定</b>
<div class="note" style="margin-top:8px;line-height:1.8">
<code>docs/cn/README.md</code> v2 新特性 #4：「<b>对低音质参考音频（尤其是来源于网络的高频严重缺失、听着很闷的音频）合成出来音质更好</b>」。<br>
这正好印证我们的实测：现有参考是<b>未降噪</b>的（带宽只到 11kHz）→ 0.8567；同一段过 DF3 降噪后 → 0.8452。
<b>参考音频不该走降噪链。</b>
</div>
</div>

<div class="card">
<b>真人基准对照（同一段话）</b>
<div class="row" style="margin-top:8px"><span class="tag">真人</span><audio controls src="data:audio/mp3;base64,__REAL__"></audio>
<span class="chip">29.41s</span><span class="chip ok">声纹天花板 0.88~0.91</span></div>
</div>

</div></body></html>"""

trs = []
for r in rows:
    ok = r["n"] and r["n"] > 400
    chip = "ok" if ok else ("warn" if r["n"] and r["n"] > 150 else "bad")
    spk = ("%.4f" % r["spk"]) if r["spk"] else "—"
    trs.append(
        '<tr>'
        '<td><b>%s</b></td>'
        '<td class="mono">%.2fs</td>'
        '<td><audio controls src="data:audio/mp3;base64,%s"></audio></td>'
        '<td><audio controls src="data:audio/mp3;base64,%s"></audio></td>'
        '<td class="mono"><span class="chip %s">%.2fs</span></td>'
        '<td class="mono">%s</td>'
        '<td class="mono">%s</td>'
        '</tr><tr><td colspan="7" class="note">%s</td></tr>'
        % (r["tag"], r["ref_dur"], r["ref_b64"], r["out_b64"], chip, r["out_dur"],
           r["n"], spk, r["note"]))

html = html.replace("__ROWS__", "\n".join(trs)).replace("__REAL__", b64(REAL))
OUT.write_text(html, encoding="utf-8")
print("已写 %s  (%.1f KB)" % (OUT, OUT.stat().st_size / 1024))
