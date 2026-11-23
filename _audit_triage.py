"""双 ASR 仲裁（difflib 词级对齐版）：真问题 / ASR 噪声 / 待查。"""
import collections
import difflib
import io
import json
import re
import sys

sys.path.insert(0, "G:/_setup")


def norm(t):
    t = (t or "").lower().replace("\u2019", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    t = t.replace("'", "")
    return [w for w in t.split() if w]


def align(ref, hyp):
    a, b = norm(ref), norm(hyp)
    if not a:
        return 0.0, 0, 0, 0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = sm.get_opcodes()
    matched = sum(i2 - i1 for tag, i1, i2, j1, j2 in ops if tag == "equal")
    lead = 0
    tail = 0
    miss = 0
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        if tag == "insert" and i1 == 0 and j1 == 0:
            lead = j2 - j1
        elif tag == "delete":
            miss += i2 - i1
            if i2 == len(a):
                tail = i2 - i1
        elif tag == "replace":
            miss += max(0, (i2 - i1) - (j2 - j1))
            if i2 == len(a):
                tail = max(0, (i2 - i1) - (j2 - j1))
    return matched / float(len(a)), lead, int(miss), int(tail)


def main():
    rows = {r["id"]: r for r in json.load(io.open("G:/_setup/_dlg_audit.json", encoding="utf-8"))}
    wh = json.load(io.open("G:/_setup/_audit_whisper.json", encoding="utf-8"))
    out = []
    for i, ws in wh.items():
        r = rows.get(i)
        if not r:
            continue
        hyp = " ".join(w for w, _a, _b in ws)
        rc, ld, ms, tl = align(r["text"], hyp)
        pc, pld, pms, ptl = align(r["text"], r["said"])
        if rc >= 0.85 and ld < 2 and tl <= 1:
            v = "ASR噪声"
        elif ld >= 2 or tl >= 2 or rc < 0.60:
            v = "真问题"
        else:
            v = "待查"
        out.append(dict(id=i, who=r["who"], emo=r["emo"], dur=r["dur"],
                        pc=round(pc, 2), prc=round(rc, 2), lead=ld, tail=tl, miss=ms,
                        flags=r["flags"], verdict=v, text=r["text"], pk=r["said"], wk=hyp))
    print("判定：", dict(collections.Counter(x["verdict"] for x in out)), "共", len(out))
    for v in ("真问题", "待查"):
        sub = [x for x in out if x["verdict"] == v]
        print("\n=== %s（%d）" % (v, len(sub)))
        for x in sorted(sub, key=lambda y: (y["tail"], -y["lead"], y["prc"])):
            print("%-9s %-7s %-6s %5.2fs PK%.2f WH%.2f lead%d miss%d tail%d [%s]" % (
                x["id"], x["who"], x["emo"], x["dur"], x["pc"], x["prc"], x["lead"], x["miss"], x["tail"],
                ",".join(x["flags"])))
            print("    原: %s" % x["text"][:96])
            print("    PK: %s" % x["pk"][:96])
            print("    WH: %s" % x["wk"][:96])
    json.dump(out, io.open("G:/_setup/_audit_triage.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出 _audit_triage.json")


if __name__ == "__main__":
    main()
