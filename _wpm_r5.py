import json, os, soundfile as sf
plan = {}
for l in open("_dlg_plan_v2.jsonl", encoding="utf-8"):
    l = l.strip()
    if l:
        o = json.loads(l); plan[o["id"]] = o
def words(t):
    t = (t or "").replace("\u2018", " ").replace("\u2019", "'")
    return len([k for k in t.split() if any(c.isalpha() for c in k)])
t = json.load(open("_regen_r5.json", encoding="utf-8"))
print("%-8s %4s %7s %7s %6s  %s" % ("id", "词", "旧wpm", "新wpm", "新s", "判断"))
bad = []
for x in t:
    i = x["id"]
    a, b = "_audio_ch123/out/%s.wav" % i, "_regen_r5_out/%s.wav" % i
    w = words(plan[i]["text"])
    do, dn = sf.info(a).duration, sf.info(b).duration
    wo, wn = w / do * 60, w / dn * 60
    flag = ""
    if wn < 90:
        flag = "<== 新偏慢"
    elif wn > 260:
        flag = "<== 新偏快(疑截断)"
    elif not (90 <= wo <= 260):
        flag = "旧越界，新正常 ✓"
    print("%-8s %4d %7.0f %7.0f %6.2f  %s" % (i, w, wo, wn, dn, flag))
    if "<==" in flag:
        bad.append(i)
print("\n需处理:", bad)
