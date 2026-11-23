import json, os, soundfile as sf
plan = {}
for l in open("_dlg_plan_v2.jsonl", encoding="utf-8"):
    l = l.strip()
    if l:
        o = json.loads(l); plan[o["id"]] = o
def words(t):
    t = (t or "").replace("\u2018", " ").replace("\u2019", "'")
    return len([k for k in t.split() if any(c.isalpha() for c in k)])
t = json.load(open("_regen_r3.json", encoding="utf-8"))
print("%-8s %-20s %4s %6s %6s %6s" % ("id", "voice", "词", "旧wpm", "新wpm", "新s"))
out = []
for x in t:
    i = x["id"]
    p, o = "_regen_r3_out/%s.wav" % i, "_audio_ch123/out/%s.wav" % i
    if not os.path.exists(p):
        print(i, "缺"); continue
    w = words(plan[i]["text"])
    dn, do = sf.info(p).duration, sf.info(o).duration
    wn, wo = w / dn * 60, w / do * 60
    flag = ""
    if wn < 90 or wn > 260: flag = "  <== 语速异常"
    print("%-8s %-20s %4d %6.0f %6.0f %6.2f%s" % (i, x["voice"], w, wo, wn, dn, flag))
    if flag: out.append(i)
print("异常:", out)
