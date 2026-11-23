# -*- coding: utf-8 -*-
"""_cloud_upl.py —— 把「本地有、云端没有」的参考条打包切片上传（ntfy 附件 2MB 上限）。

用法：
    python _cloud_upl.py                 # 自动算差集
    python _cloud_upl.py Charles_wary_2  # 只传指定的 voice

输出：_cloud_upl.json = {urls: [...], voices: [...], nbytes: N}
云端取回见 _cloud_fetch.sh（按 url 顺序 cat 再解包）。
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request

HERE = "G:/_setup"
PKG = os.path.join(HERE, "_cloud_up")
WORK = os.path.join(HERE, "_cloud_up", "voice_lib")
LIMIT = 1_850_000
OUT = "https://ntfy.sh/tts_o7k2mq"

# 云端现有 voice（2026-11-14 00:05 实测 ls 结果）
CLOUD = set("""Charles_angry_1 Charles_defiant_1 Charles_defiant_2 Charles_excited_1
Charles_excited_2 Charles_excited_3 Charles_nervous_1 Charles_neutral_1 Charles_neutral_2
Charles_neutral_3 Charles_soft_1 Charles_soft_2 Charles_soft_3 Charles_wary_1 Charles_wronged_1
Fielding_defiant_1 Fielding_defiant_2 Fielding_defiant_3 Fielding_excited_1 Fielding_excited_2
Fielding_excited_3 Fielding_nervous_1 Fielding_nervous_2 Fielding_nervous_3 Fielding_wary_1
Fielding_wary_2 Fielding_wary_3 Fielding_wronged_1 Fielding_wronged_2 Fielding_wronged_3
Helena_defiant_1 Helena_defiant_2 Helena_defiant_3 Helena_excited_1 Helena_excited_2
Helena_excited_3 Helena_nervous_1 Helena_nervous_2 Helena_nervous_3 Helena_wary_1 Helena_wary_2
Helena_wary_3 Helena_wronged_1 Helena_wronged_2 Helena_wronged_3 Joseph_defiant_1
Joseph_defiant_2 Joseph_defiant_3 Joseph_excited_1 Joseph_excited_2 Joseph_excited_3
Joseph_nervous_1 Joseph_nervous_2 Joseph_nervous_3 Joseph_normal_1 Joseph_normal_2
Joseph_normal_3 Joseph_wary_1 Joseph_wary_2 Joseph_wary_3 Joseph_wronged_1 Joseph_wronged_2
Joseph_wronged_3 Thomas_begging_1 Thomas_begging_2 Thomas_begging_3 Thomas_begging_4
Thomas_calm_1 Thomas_calm_2 Thomas_calm_3 Thomas_calm_4 Thomas_loud_1 Thomas_loud_2
Thomas_loud_3 Thomas_loud_4 Thomas_nervous_1 Thomas_nervous_2 Thomas_scold_1 Thomas_scold_2
Thomas_scold_3 Thomas_wary_1 Thomas_wary_2 Thomas_wronged_1 narr_mc_1""".split())

lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
local = {}
for role in lib:
    for emo, items in lib[role].items():
        for k, it in enumerate(items, 1):
            p = it.get("path") if isinstance(it, dict) else it
            t = (it.get("text") or "") if isinstance(it, dict) else ""
            local["%s_%s_%d" % (role, emo, k)] = ((p or "").replace("/", os.sep), " ".join(t.split()))

want = sys.argv[1:] or [v for v in local if v not in CLOUD]
want = [v for v in want if v in local]
if os.path.isdir(PKG):
    shutil.rmtree(PKG)
os.makedirs(WORK, exist_ok=True)

lines, total = [], 0
for v in sorted(want):
    p, t = local[v]
    if not os.path.exists(p):
        print("缺文件", v, p)
        continue
    shutil.copy2(p, os.path.join(WORK, v + ".wav"))
    lines.append("%s|%s" % (v, t))
    total += os.path.getsize(p)
with open(os.path.join(PKG, "prompt_text"), "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")

tarp = os.path.join(PKG, "up.tar.gz")
subprocess.run(["tar", "-czf", tarp, "-C", PKG, "voice_lib", "prompt_text"], check=True)
data = open(tarp, "rb").read()
print("要传 %d 条参考，原 %.1f MB，压缩后 %.1f MB" % (len(lines), total / 1e6, len(data) / 1e6))

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urls, off, part = [], 0, 0
while off < len(data):
    chunk = data[off:off + LIMIT]
    part += 1
    ok = False
    for attempt in range(3):
        req = urllib.request.Request(OUT, data=chunk, method="PUT")
        req.add_header("Filename", "p%02d.bin" % part)
        req.add_header("Content-Type", "application/octet-stream")
        try:
            with op.open(req, timeout=300) as r:
                d = json.loads(r.read().decode())
            urls.append(d["attachment"]["url"])
            ok = True
            break
        except Exception as e:
            print("  分片 %d 第 %d 次失败 %s" % (part, attempt + 1, e))
    if not ok:
        raise SystemExit("分片 %d 上传失败，中止" % part)
    print("  分片 %d ok  %.2f MB" % (part, len(chunk) / 1e6))
    off += LIMIT

res = dict(urls=urls, voices=sorted(want), nbytes=len(data))
json.dump(res, open(os.path.join(HERE, "_cloud_up.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n分片 %d 个：%s" % (len(urls), urls))
