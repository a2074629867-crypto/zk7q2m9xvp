# -*- coding: utf-8 -*-
"""build_ref_page.py —— 参考音频扫描结果试听页（离线单文件，内嵌 MP3）

每行同时给：参考音频本身 + 该参考生成的成品 + 三项指标
"""
import base64, json, subprocess
from pathlib import Path

REFDIR = Path(r"E:/tts-models/acpp/out/refs")
OUTDIR = Path(r"E:/tts-models/acpp/out/refsweep")
REAL = Path(r"E:/tts-models/acpp/out/calmdeep_final/real_trim.wav")
OUT = Path(r"G:/_setup/gsv5_ref_listen.html")
FF = r"E:/tool/oopz/ffmpeg.exe"
TARGET = open(r"G:/_setup/scene_calmdeep.txt", encoding="utf-8").read().strip()

SPK = {"baseA_oldnoisy_8.3s": 0.8567, "baseB_df3hp_8.3s": 0.8452,
       "ref00_06.3s_6_8s": 0.6762, "ref01_05.8s_4p5_6s": 0.4012,
       "ref02_04.9s_4p5_6s": 0.7948, "ref03_06.1s_6_8s": 0.7719,
       "ref04_09.8s_8_10s": 0.8414, "ref05_06.2s_6_8s": 0.8375,
       "ref06_05.1s_4p5_6s": 0.7851, "ref07_06.4s_6_8s": 0.8410,
       "ref08_05.4s_4p5_6s": 0.8296}
DESC = {
    "baseA_oldnoisy_8.3s": "① 现在在用的（未降噪）—— 声纹最高、内容完美",
    "baseB_df3hp_8.3s": "② 同一段换成 DF3 降噪版 —— 降噪反而略伤音色",
    "ref01_05.8s_4p5_6s": "F0 波动只有 ±11Hz（其余 35~65）—— 音色严重劣化，说明参考段的选择影响巨大",
}


def b64(p: Path) -> str:
    tmp = OUT.parent / ("_r_" + p.stem + ".mp3")
    subprocess.run([FF, "-y", "-i", str(p), "-codec:a", "libmp3lame",
                    "-b:a", "128k", "-ar", "32000", str(tmp)],
                   check=True, capture_output=True)
    s = base64.b64encode(tmp.read_bytes()).decode()
    tmp.unlink(missing_ok=True)
    return s


rows = []
for r in json.load(open(OUTDIR / "verify.json", encoding="utf-8")):
    tag = r["tag"]
    outp = OUTDIR / (tag + ".wav")
    if not outp.exists():
        continue
    refp = Path(r["ref_path"])
    rows.append(dict(tag=tag, ref_dur=r["ref_dur"], out_dur=r["out_dur"],
                     asr=r["asr"], miss=r["n_missing"], spk=SPK.get(tag),
                     kind=r.get("kind", "new"), desc=DESC.get(tag, ""),
                     ref_b64=b64(refp) if refp.exists() else "",
                     out_b64=b64(outp)))

data = {"rows": rows, "real": b64(REAL), "target": TARGET}

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>参考音频扫描 · 音色克隆</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--fg:#16181c;--mut:#5c6572;--line:#e2e5ea;
      --ok:#0a7d43;--bad:#c0392b;--warn:#b7791f;--acc:#1a5fb4}
html.dark{--bg:#131619;--card:#1b1f23;--fg:#e9ebee;--mut:#98a2b0;--line:#2b3138;
      --ok:#4ecb8a;--bad:#ff7b6b;--warn:#e3b341;--acc:#6aa9ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:30px 18px 90px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
h2{font-size:17px;margin:30px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.hint{color:var(--mut);font-size:12.5px;margin:6px 0 14px}
.row{background:var(--card);border:1px solid var(--line);border-radius:12px;
     padding:13px 16px;margin:10px 0}
.row.best{border-left:4px solid var(--ok)}
.row.bad{border-left:4px solid var(--bad)}
.row.neutral{border-left:4px solid var(--line)}
.top{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.nm{font-weight:700;min-width:210px;font-size:14px}
.metrics{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--mut)}
.metrics b{color:var(--fg);font-variant-numeric:tabular-nums;font-size:14px}
.badge{font-size:11.5px;padding:2px 9px;border-radius:20px;border:1px solid var(--line);color:var(--mut)}
.badge.g{color:var(--ok);border-color:var(--ok)}
.badge.r{color:var(--bad);border-color:var(--bad)}
.audio2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px}
@media(max-width:720px){.audio2{grid-template-columns:1fr}}
.acell{font-size:12px;color:var(--mut)}
.acell .lb{display:flex;justify-content:space-between;margin-bottom:3px}
audio{height:32px;width:100%}
.note{color:var(--mut);font-size:12.5px;margin-top:8px}
.toggle{position:fixed;top:13px;right:15px;background:var(--card);border:1px solid var(--line);
        color:var(--fg);border-radius:8px;padding:6px 12px;cursor:pointer;font-size:13px;z-index:9}
.q{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc);
   border-radius:11px;padding:14px 18px;margin:10px 0;font-size:13.5px}
code{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;background:var(--bg);
     border:1px solid var(--line);border-radius:5px;padding:1px 6px}
</style></head><body>
<button class="toggle" onclick="document.documentElement.classList.toggle('dark')">◐ 主题</button>
<div class="wrap">
<h1>参考音频扫描 · McConaughey 音色克隆</h1>
<div class="sub">GPT 固定 <code>v6-e18</code> · SoVITS 固定零样本 <code>s2Gv5turbo</code> · 只换参考音频 · 全 CPU · seed 42</div>

<div class="q">
  <b>结论：换成别的参考音频一个都没赢过现有的。</b><br>
  现有 8.3s 那段（未降噪）声纹 <b>0.8567</b>、ASR <b>1.000</b>，是全组最优；
  同段做 DF3 降噪反而掉到 0.8452 ⇒ <b>降噪处理本身会损伤音色线索</b>。<br>
  跨度也测出来了：参考音频选得不好，声纹能掉到 <b>0.40</b>（ref01，F0 波动仅 ±11Hz）——
  可见<b>参考音频是音色的第一主导因素</b>，但现有那段已经接近真人跨段天花板（0.88~0.91）。
</div>

<h2>① 真人参照 + 目标文本</h2>
<div class="row neutral">
  <div class="top"><div class="nm">real_trim.wav（真人 29.4s，声纹锚点）</div></div>
  <div class="audio2" style="grid-template-columns:1fr">
    <div class="acell"><audio controls preload="none" src="data:audio/mpeg;base64,__REAL__"></audio></div>
  </div>
  <div class="note">目标文本（38 词）：__TARGET__</div>
</div>

<h2>② 各参考音频 → 成品对照</h2>
<div class="hint">每行左：参考音频本身；右：用该参考生成的成品。指标对应成品。</div>
<div id="A"></div>
</div>
<script>
const D = __DATA__;
function render(el, list){
  el.innerHTML = list.map(r => {
    const cls = r.kind.startsWith('baseline') ? (r.tag.startsWith('baseA') ? 'best' : 'neutral')
                : (r.spk < 0.6 ? 'bad' : (r.spk >= 0.84 ? 'best' : 'neutral'));
    return `<div class="row ${cls}">
      <div class="top">
        <div class="nm">${r.tag}</div>
        <div class="metrics">
          <span>参考 <b>${r.ref_dur.toFixed(2)}s</b></span>
          <span>成品 <b>${r.out_dur.toFixed(2)}s</b></span>
          <span>ASR <b>${r.asr.toFixed(3)}</b></span>
          <span>缺词 <b>${r.miss}</b></span>
          <span>声纹 <b>${r.spk ? r.spk.toFixed(4) : '-'}</b></span>
        </div>
        ${r.tag.startsWith('baseA') ? '<span class="badge g">当前在用 · 最优</span>' : ''}
        ${r.spk && r.spk < 0.6 ? '<span class="badge r">音色崩塌</span>' : ''}
      </div>
      <div class="audio2">
        <div class="acell"><div class="lb"><span>参考音频</span></div>
          <audio controls preload="none" src="data:audio/mpeg;base64,${r.ref_b64}"></audio></div>
        <div class="acell"><div class="lb"><span>成品</span></div>
          <audio controls preload="none" src="data:audio/mpeg;base64,${r.out_b64}"></audio></div>
      </div>
      ${r.desc ? `<div class="note">${r.desc}</div>` : ''}
    </div>`;
  }).join('');
}
render(document.getElementById('A'), D.rows);
</script>
</body></html>"""

html = (html.replace("__REAL__", data["real"])
            .replace("__TARGET__", data["target"])
            .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
OUT.write_text(html, encoding="utf-8")
print("OK %s (%.2f MB)" % (OUT, OUT.stat().st_size / 1024 / 1024))
