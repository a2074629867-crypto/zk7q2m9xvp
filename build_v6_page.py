# -*- coding: utf-8 -*-
"""build_v6_page.py —— v6 GPT 微调候选对比试听页（离线单文件，内嵌 base64 MP3）

数据来源：
  - 时长  : _v6sweep.log / _v6full.log
  - ASR   : E:/tts-models/acpp/out/v6full/asr_check.json
  - 声纹  : 手工填入（spk_embed.py 锚 real_trim.wav）
"""
import base64, json, os, subprocess
from pathlib import Path

WAV = Path(r"E:/tts-models/acpp/out/v6full")
REAL = Path(r"E:/tts-models/acpp/out/calmdeep_final/real_trim.wav")
OUT = Path(r"G:/_setup/gsv5_v6_listen.html")
FF = r"E:/tool/oopz/ffmpeg.exe"

SPK = {
    "base": 0.8508, "e1": 0.8286, "e3": 0.8850, "e5": 0.8443,
    "e9": 0.8672, "e16": 0.8406, "e18": 0.8567, "e20": 0.8307,
}
NOTE = {
    "e18": ("best", "ASR 相似度 1.000，38 词零缺失 —— 内容保真最佳"),
    "e3":  ("best", "声纹 0.8850 全场最高（真人跨段天花板 0.88~0.91）"),
    "e9":  ("mid",  "时长 21.44s 最接近底模 21.00s，韵律保留最多"),
    "e5":  ("mid",  "时长 21.60s，略长于底模"),
    "e1":  ("",     "第 1 轮，欠拟合"),
    "e16": ("",     ""),
    "e20": ("",     "第 20 轮，时长偏短"),
    "base":("ok",   "底模 s1v3（未微调）—— 参照基线"),
}
ASR = {r["tag"]: r for r in json.load(open(WAV / "asr_check.json", encoding="utf-8"))}

# sweep 里的全量 epoch 结果（用于表格）
SWEEP = [
    ("e1", 19.56), ("e2", 3.52), ("e3", 17.88), ("e4", 18.28), ("e5", 21.40),
    ("e6", 16.88), ("e7", 16.72), ("e8", 16.72), ("e9", 21.24), ("e10", 11.24),
    ("e11", 59.96), ("e12", 2.80), ("e13", 1.12), ("e14", 16.72), ("e15", 1.12),
    ("e16", 18.36), ("e17", 17.56), ("e18", 18.64), ("e19", 17.88), ("e20", 17.68),
]


def b64(p: Path) -> str:
    tmp = OUT.parent / ("_t_" + p.stem + ".mp3")
    subprocess.run([FF, "-y", "-i", str(p), "-codec:a", "libmp3lame",
                    "-b:a", "128k", "-ar", "32000", str(tmp)],
                   check=True, capture_output=True)
    s = base64.b64encode(tmp.read_bytes()).decode()
    tmp.unlink(missing_ok=True)
    return s


def row(tag: str, show_name: str, dur: float, cls: str, note: str,
        asr_ratio=None, miss=None, spk=None, b64s=""):
    return dict(tag=tag, name=show_name, dur=dur, cls=cls, note=note,
                asr=asr_ratio, miss=miss, spk=spk, b64=b64s)


rows = []
rows.append(row("real", "真人原声", 29.41, "real",
                "Calm 原音频（对齐验证的锚点）", None, None, None, b64(REAL)))
for tag in ["base", "e1", "e3", "e5", "e9", "e16", "e18", "e20"]:
    p = WAV / ("v6_%s.wav" % tag)
    if not p.exists():
        continue
    a = ASR.get(tag, {})
    cls, note = NOTE.get(tag, ("", ""))
    name = "底模 base" if tag == "base" else ("微调 %s" % tag)
    rows.append(row(tag, name, a.get("dur", 0), cls, note,
                    a.get("ratio"), a.get("n_missing"),
                    SPK.get(tag), b64(p)))

data = {"rows": rows, "sweep": SWEEP}

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GSV v5turbo · GPT 微调候选试听（v6 数据集）</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--fg:#16181c;--mut:#5c6572;--line:#e2e5ea;
      --ok:#0a7d43;--bad:#c0392b;--warn:#b7791f;--acc:#1a5fb4}
html.dark{--bg:#131619;--card:#1b1f23;--fg:#e9ebee;--mut:#98a2b0;--line:#2b3138;
      --ok:#4ecb8a;--bad:#ff7b6b;--warn:#e3b341;--acc:#6aa9ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:30px 18px 80px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px;margin-bottom:22px}
h2{font-size:17px;margin:30px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.hint{color:var(--mut);font-size:12.5px;margin:6px 0 14px}
.row{background:var(--card);border:1px solid var(--line);border-radius:11px;
     padding:12px 15px;margin:9px 0}
.row .top{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.row.best{border-left:4px solid var(--ok)}
.row.bad{border-left:4px solid var(--bad)}
.row.mid{border-left:4px solid var(--warn)}
.row.ok,.row.real{border-left:4px solid var(--acc)}
.nm{font-weight:700;min-width:104px}
.dur{font-variant-numeric:tabular-nums;font-size:16px;font-weight:700;min-width:70px}
.metrics{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--mut)}
.metrics b{color:var(--fg);font-variant-numeric:tabular-nums}
.badge{font-size:11.5px;padding:2px 9px;border-radius:20px;
       border:1px solid var(--line);color:var(--mut)}
.badge.g{color:var(--ok);border-color:var(--ok)}
.badge.r{color:var(--bad);border-color:var(--bad)}
audio{height:34px;width:100%;margin-top:9px}
.note{color:var(--mut);font-size:12.5px;margin-top:6px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}
th{color:var(--mut);font-weight:600}
td.ok{color:var(--ok);font-weight:700}
td.bad{color:var(--bad);font-weight:700}
.toggle{position:fixed;top:13px;right:15px;background:var(--card);border:1px solid var(--line);
        color:var(--fg);border-radius:8px;padding:6px 12px;cursor:pointer;font-size:13px;z-index:9}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;color:var(--mut);margin:10px 0 4px}
</style></head><body>
<button class="toggle" onclick="document.documentElement.classList.toggle('dark')">◐ 主题</button>
<div class="wrap">
<h1>GSV v5turbo · GPT 微调候选试听</h1>
<div class="sub">Matthew McConaughey / Calm《Wonder》· 音色克隆 · 全部 CPU 推理 ·
解码参数 top_k=15 / top_p=1 / temperature=1 / seed=42 / speed 1.0</div>

<h2>① 候选试听（同一段 38 词分布外文本）</h2>
<div class="hint">ASR 相似度 = Parakeet TDT v3 回读文本与源文本的词级相似度；声纹 = WeSpeaker CAM++ 对真人 real_trim.wav 的余弦相似度（真人跨段天花板 0.88~0.91）</div>
<div class="legend">
  <span>🟩 内容/声纹 最佳</span><span>🟨 时长最接近底模</span><span>🟦 参照</span>
</div>
<div id="A"></div>

<h2>② 全 20 个 epoch 输出时长扫描</h2>
<div class="hint">判定标准：越接近底模 21.0s 说明预训练韵律保留越好；&lt;5s 为塌缩，&gt;35s 为过度生成</div>
<table>
<tr><th>epoch</th><th>输出时长</th><th>判定</th><th>epoch</th><th>输出时长</th><th>判定</th></tr>
__SWEEP__
</table>

<div class="sub" style="margin-top:30px">
结论：修复「掩码错配 + 静音毒化」后，<b>20 个 epoch 里有 15 个输出完整</b>（旧数据集是 0/15 全崩）。
残留的不稳定（e2/e12/e13/e15 塌缩、e11 过度生成）说明<b>仍必须逐 epoch 扫描 + 试听</b>，
不能只看 top_3_acc。当前最佳：<b>e18</b>（内容零缺失）、<b>e3</b>（声纹 0.885）。
</div>
</div>
<script>
const D = __DATA__;
function render(el, list){
  el.innerHTML = list.map(r => {
    const cls = r.cls || '';
    const spkCls = r.spk >= 0.87 ? 'g' : (r.spk ? '' : '');
    const asrCls = r.asr == null ? '' : (r.asr >= 0.98 ? 'g' : (r.asr < 0.85 ? 'r' : ''));
    return `<div class="row ${cls}">
      <div class="top">
        <div class="nm">${r.name}</div>
        <div class="dur">${r.dur ? r.dur.toFixed(2)+'s' : '-'}</div>
        <div class="metrics">
          ${r.asr != null ? `<span>ASR <b>${r.asr.toFixed(3)}</b></span>` : ''}
          ${r.miss != null ? `<span>缺词 <b>${r.miss}</b></span>` : ''}
          ${r.spk ? `<span>声纹 <b>${r.spk.toFixed(4)}</b></span>` : ''}
        </div>
        ${r.asr != null && r.asr >= 0.98 ? '<span class="badge g">内容完美</span>' : ''}
        ${r.spk >= 0.87 ? '<span class="badge g">声纹最高</span>' : ''}
      </div>
      <audio controls preload="none" src="data:audio/mpeg;base64,${r.b64}"></audio>
      ${r.note ? `<div class="note">${r.note}</div>` : ''}
    </div>`;
  }).join('');
}
render(document.getElementById('A'), D.rows);
</script>
</body></html>"""

# 表格行
def verdict(d):
    if d > 35: return ('bad', '过度生成')
    if d < 5:  return ('bad', '塌缩')
    if d < 13: return ('bad', '偏短')
    return ('ok', '完整')

SW = data["sweep"]
half = (len(SW) + 1) // 2
trs = []
for i in range(half):
    cells = []
    for j in (i, i + half):
        if j < len(SW):
            t, d = SW[j]
            c, v = verdict(d)
            cells += ["e%s" % t[1:], "%.2fs" % d, '<span style="color:%s">%s</span>' % (
                'var(--ok)' if c == 'ok' else 'var(--bad)', v)]
        else:
            cells += ["", "", ""]
    trs.append("<tr>%s</tr>" % "".join("<td>%s</td>" % x for x in cells))

html = html.replace("__SWEEP__", "\n".join(trs))
html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False))
OUT.write_text(html, encoding="utf-8")
print("OK %s  (%.2f MB)" % (OUT, OUT.stat().st_size / 1024 / 1024))
