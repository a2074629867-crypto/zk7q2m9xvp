import io
newp = "/home/aistudio/up/prompt_text"
oldp = "/home/aistudio/voice_lib/prompt_text"
new = {}
for ln in io.open(newp, encoding="utf-8"):
    ln = ln.strip("\n")
    if "|" in ln:
        k, v = ln.split("|", 1)
        new[k] = v
keep, seen = [], set()
for ln in io.open(oldp, encoding="utf-8"):
    ln = ln.strip("\n")
    if "|" not in ln:
        continue
    k = ln.split("|", 1)[0]
    keep.append("%s|%s" % (k, new[k]) if k in new else ln)
    seen.add(k)
for k, v in new.items():
    if k not in seen:
        keep.append("%s|%s" % (k, v))
io.open(oldp, "w", encoding="utf-8", newline="\n").write("\n".join(keep) + "\n")
print("prompt lines", len(keep), "new", len(set(new) - seen))
