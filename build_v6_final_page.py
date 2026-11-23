# -*- coding: utf-8 -*-
"""build_v6_final_page.py —— 最终汇总页：推荐配置 + GPT 候选 + SoVITS 对照 + 扫描表 + 方法学

输出：G:/_setup/gsv5_v6_final.html（离线单文件，内嵌 base64 MP3）
"""
import base64, json, subprocess
from pathlib import Path

V6FULL = Path(r"E:/tts-models/acpp/out/v6full")
SOVFIN = Path(r"E:/tts-models/acpp/out/v6sovfinal")
REAL = Path(r"E:/tts-models/acpp/out/calmdeep_final/real_trim.wav")
OUT = Path(r"G:/_setup/gsv5_v6_final.html")
FF = r"E:/tool/oopz/ffmpeg.exe"

SPK = {"base": 0.8508, "e1": 0.8286, "e3": 0.8850, "e5": 0.8443, "e9": 0.8672,
       "e16": 0.8406, "e18": 0.8567, "e20": 0.8307}
NOTE = {
    "e18": ("best", "ASR 1.000 / 38 词零缺失 —— 内容保真最佳"),
    "e3":  ("best", "声纹 0.8850 全场最高（真人跨段天花板 0.88~0.91）"),
    "e9":  ("mid",  "21.44s 最接近底模 21.00s，预训练韵律保留最多"),
    "e5":  ("mid",  "21.60s，略长于底模"),
    "e1":  ("",     "第 1 轮，欠拟合"),
    "e16": ("",     ""),
    "e20": ("",     "第 20 轮，时长偏短"),
    "base":("ok",   "底模 s1v3（未微调）—— 参照基线"),
}
ASR = {r["tag"]: r for r in json.load(open(V6FULL / "asr_check.json", encoding="utf-8"))}

SOV_SPK = {"base": 0.8567, "e2_s232": 0.5193, "e4_s464": 0.5169,
           "e6_s696": 0.5011, "e8_s928": 0.5078}

SWEEP = [("e1",19.56),("e2",3.52),("e3",17.88),("e4",18.28),("e5",21.40),
         ("e6",16.88),("e7",16.72),("e8",16.72),("e9",21.24),("e10",11.24),
         ("e11",59.96),("e12",2.80),("e13",1.12),("e14",16.72),("e15",1.12),
         ("e16",18.36),("e17",17.56),("e18",18.64),("e19",17.88),("e20",17.68)]


def b64(p: Path) -> str:
    tmp = OUT.parent / ("_t_" + p.stem + ".mp3")
    subprocess.run([FF, "-y", "-i", str(p), "-codec:a", "libmp3lame",
                    "-b:a", "128k", "-ar", "32000", str(tmp)],
                   check=True, capture_output=True)
    s = base64.b64encode(tmp.read_bytes()).decode()
    tmp.unlink(missing_ok=True)
    return s


gpt_rows = [dict(tag="real", name="真人原声", dur=29.41, cls="real",
                 note="Calm 原音频（对齐验证锚点）", b64=b64(REAL))]
for tag in ["base", "e1", "e3", "e5", "e9", "e16", "e18", "e20"]:
    p = V6FULL / ("v6_%s.wav" % tag)
    if not p.exists():
        continue
    a = ASR.get(tag, {})
    cls, note = NOTE.get(tag, ("", ""))
    gpt_rows.append(dict(tag=tag, name="底模 base" if tag == "base" else "微调 %s" % tag,
                         dur=a.get("dur", 0), cls=cls, note=note,
                         asr=a.get("ratio"), miss=a.get("n_missing"),
                         spk=SPK.get(tag), n=a.get("nw"), b64=b64(p)))

sov_rows = []
for key, label in [("base", "base 零样本 s2Gv5turbo"), ("e2_s232", "微调 LoRA e2"),
                   ("e4_s464", "微调 LoRA e4"), ("e6_s696", "微调 LoRA e6"),
                   ("e8_s928", "微调 LoRA e8")]:
    p = SOVFIN / ("sf_%s.wav" % key)
    if not p.exists():
        continue
    cls = "best" if key == "base" else "bad"
    note = ("零样本 —— 声纹保持最好，推荐" if key == "base"
            else "LoRA 微调后声纹掉到 0.50 附近，明显劣化")
    sov_rows.append(dict(tag=key, name=label, dur=18.84, cls=cls, note=note,
                         spk=SOV_SPK.get(key), b64=b64(p)))

data = {"gpt": gpt_rows, "sov": sov_rows, "sweep": SWEEP}

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GSV v5turbo · 麦康纳音色克隆 · v6 最终结果</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--fg:#16181c;--mut:#5c6572;--line:#e2e5ea;
      --ok:#0a7d43;--bad:#c0392b;--warn:#b7791f;--acc:#1a5fb4}
html.dark{--bg:#131619;--card:#1b1f23;--fg:#e9ebee;--mut:#98a2b0;--line:#2b3138;
      --ok:#4ecb8a;--bad:#ff7b6b;--warn:#e3b341;--acc:#6aa9ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1010px;margin:0 auto;padding:30px 18px 90px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
h2{font-size:17px;margin:32px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.hint{color:var(--mut);font-size:12.5px;margin:6px 0 14px}
.hero{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);
      border-radius:12px;padding:16px 20px;margin-bottom:8px}
.hero .t{font-weight:700;font-size:16px;margin-bottom:8px}
.hero code{background:var(--bg);border:1px solid var(--line);border-radius:6px;
           padding:2px 8px;font-size:13px}
.hero .grid{display:flex;gap:22px;flex-wrap:wrap;font-size:13px;color:var(--mut);margin-top:10px}
.hero .grid b{color:var(--fg);font-size:15px;font-variant-numeric:tabular-nums}
.row{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:12px 15px;margin:9px 0}
.row .top{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.row.best{border-left:4px solid var(--ok)}
.row.bad{border-left:4px solid var(--bad)}
.row.mid{border-left:4px solid var(--warn)}
.row.ok,.row.real{border-left:4px solid var(--acc)}
.nm{font-weight:700;min-width:150px}
.dur{font-variant-numeric:tabular-nums;font-size:16px;font-weight:700;min-width:70px}
.metrics{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--mut)}
.metrics b{color:var(--fg);font-variant-numeric:tabular-nums}
.badge{font-size:11.5px;padding:2px 9px;border-radius:20px;border:1px solid var(--line);color:var(--mut)}
.badge.g{color:var(--ok);border-color:var(--ok)}
.badge.r{color:var(--bad);border-color:var(--bad)}
audio{height:34px;width:100%;margin-top:9px}
.note{color:var(--mut);font-size:12.5px;margin-top:6px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}
th{color:var(--mut);font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:15px 18px;margin:10px 0}
.card .t{font-weight:700;margin-bottom:6px}
.card.bad{border-left:4px solid var(--bad)}
.card.warn{border-left:4px solid var(--warn)}
.toggle{position:fixed;top:13px;right:15px;background:var(--card);border:1px solid var(--line);
        color:var(--fg);border-radius:8px;padding:6px 12px;cursor:pointer;font-size:13px;z-index:9}
code{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
</style></head><body>
<button class="toggle" onclick="document.documentElement.classList.toggle('dark')">◐ 主题</button>
<div class="wrap">
<h1>GSV v5turbo · McConaughey 音色克隆 · v6 最终结果</h1>
<div class="sub">Calm《Wonder》· 全 CPU · RX580 未参与 · top_k=15 / top_p=1 / temperature=1 / seed=42 / speed 1.0 · 参考音频 8.3s</div>

<div class="hero">
  <div class="t">✅ 推荐配置</div>
  GPT：<code>GPT_weights_v6/mcconaughey_v6-e18.ckpt</code>　SoVITS：<code>pretrained_models/gsv-v5-pretrained/s2Gv5turbo.pth</code>（零样本，不微调）
  <div class="grid">
    <span>时长 <b>18.84s</b></span>
    <span>ASR 相似度 <b>1.000</b></span>
    <span>缺词 <b>0 / 38</b></span>
    <span>声纹 <b>0.8567</b></span>
  </div>
</div>
<div class="hint">声纹 = WeSpeaker CAM++ 对真人 real_trim.wav(29.4s) 的余弦相似度；真人跨段天花板 0.88~0.91。<br>
ASR = Parakeet TDT v3 回读 38 词文本与源文本的词级相似度。</div>

<h2>① GPT 候选（同一段 38 词分布外文本）</h2>
<div id="A"></div>

<h2>② SoVITS 权重对照（GPT 固定 v6-e18）</h2>
<div class="hint">五者时长完全相同（18.84s）—— 输出长度由 GPT 决定，SoVITS 只管音色。</div>
<div id="B"></div>

<h2>③ 全 20 个 epoch 输出时长扫描</h2>
<div class="hint">越接近底模 21.0s 说明预训练韵律保留越好；&lt;5s = 塌缩，&gt;35s = 过度生成。修复后 15/20 完整（旧数据集 0/15 全崩）。</div>
<table>
<tr><th>epoch</th><th>时长</th><th>判定</th><th>epoch</th><th>时长</th><th>判定</th></tr>
__SWEEP__
</table>

<h2>④ 方法学发现（两个坑，都会让结论完全错掉）</h2>

<div class="card bad">
  <div class="t">坑 1 · 冷启动伪影：新进程的第一次推理必定失控</div>
  同一权重 <code>e18</code>、同一 seed 42、同一输入，一个进程内连跑三次：<code>n = [1499, 466, 466]</code>。<br>
  第 1 次吐 <b>1499 token / 60.16s</b>，第 2、3 次稳定 <b>466 token / 18.64s</b>。<br>
  数字 <code>1499</code> 在四份互不相干的日志里反复出现 ⇒ 系统性伪影，不是随机波动。<br>
  <b>修法：正式推理前必须跑一次 warmup 并丢弃结果。</b>（本次 SoVITS 对照已按此重做，结果不变 ⇒ 微调 SoVITS 确实是负收益。）
</div>

<div class="card warn">
  <div class="t">坑 2 · <code>init_t2s_weights()</code> 硬编码 <code>hz = 50</code> 并覆写配置文件</div>
  <code>TTS.py:687</code> 里 <code>self.configs.hz = 50</code>，而 v5turbo 的语义帧率是 25Hz；
  <code>early_stop_num = hz × max_sec</code> 因此翻倍。<br>
  同时 <code>init_t2s_weights</code> / <code>init_vits_weights</code> 会调用 <code>save_configs()</code>，
  <b>把 <code>GPT_SoVITS/configs/tts_infer.yaml</code> 的 <code>custom:</code> 块覆写成当前脚本的路径</b> —— 跨进程状态污染。<br>
  <b>固定配方：</b><code>TTS(config: t2s=s1v3, vits=目标)</code> → <code>init_t2s_weights(微调 ckpt)</code> → warmup → <code>run()</code>。
</div>

<div class="card">
  <div class="t">已确认的根因（上一轮）</div>
  ① <b>PR#2537 掩码错配</b>：把左填充专用掩码用在了右填充数据上，作者自己警告过"会影响预训练权重微调"；
  已用 <code>GSV_LEGACY_ALIGN</code> 开关恢复 PR 前对齐。<br>
  ② <b>数据集被静音毒化</b>：<code>max_sil_kept</code> 3000ms 让语音占比中位仅 0.558、52% 的片含 &gt;1s 静音，
  训出「静音 token → EOS」的捷径吸引子；改 700ms 后语音占比 0.708、干净片 20% → 76%。<br>
  两者叠加后：训练被筛样本 20 → 2 条，完整输出 epoch 0/15 → 15/20。
</div>

</div>
<script>
const D = __DATA__;
function render(el, list){
  el.innerHTML = list.map(r => {
    const asrCls = r.asr == null ? '' : (r.asr >= 0.98 ? 'g' : (r.asr < 0.85 ? 'r' : ''));
    return `<div class="row ${r.cls||''}">
      <div class="top">
        <div class="nm">${r.name}</div>
        <div class="dur">${r.dur ? r.dur.toFixed(2)+'s' : '-'}</div>
        <div class="metrics">
          ${r.asr != null ? `<span>ASR <b>${r.asr.toFixed(3)}</b></span>` : ''}
          ${r.miss != null ? `<span>缺词 <b>${r.miss}</b></span>` : ''}
          ${r.spk ? `<span>声纹 <b>${r.spk.toFixed(4)}</b></span>` : ''}
        </div>
        ${r.asr != null && r.asr >= 0.98 ? '<span class="badge g">内容完美</span>' : ''}
        ${r.spk >= 0.88 ? '<span class="badge g">声纹最高</span>' : ''}
        ${r.spk && r.spk < 0.6 ? '<span class="badge r">音色劣化</span>' : ''}
      </div>
      <audio controls preload="none" src="data:audio/mpeg;base64,${r.b64}"></audio>
      ${r.note ? `<div class="note">${r.note}</div>` : ''}
    </div>`;
  }).join('');
}
render(document.getElementById('A'), D.gpt);
render(document.getElementById('B'), D.sov);
</script>
</body></html>"""


def verdict(d):
    if d > 35: return ('bad', '过度生成')
    if d < 5:  return ('bad', '塌缩')
    if d < 13: return ('bad', '偏短')
    return ('ok', '完整')

SW = data["sweep"]; half = (len(SW) + 1) // 2
trs = []
for i in range(half):
    cells = []
    for j in (i, i + half):
        if j < len(SW):
            t, d = SW[j]
            c, v = verdict(d)
            cells += ["e%s" % t[1:], "%.2fs" % d,
                      '<span style="color:%s">%s</span>' % ('var(--ok)' if c == 'ok' else 'var(--bad)', v)]
        else:
            cells += ["", "", ""]
    trs.append("<tr>%s</tr>" % "".join("<td>%s</td>" % x for x in cells))

html = html.replace("__SWEEP__", "\n".join(trs)).replace("__DATA__", json.dumps(data, ensure_ascii=False))
OUT.write_text(html, encoding="utf-8")
print("OK %s  (%.2f MB)" % (OUT, OUT.stat().st_size / 1024 / 1024))
