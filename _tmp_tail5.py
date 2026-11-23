import json,io,sys
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
p=r"D:\wb2api-cli\account-01\projects\c-Users-86178-WorkBuddy-2026-10-05-00-50-22\wb6f61cfe8fabb1c105a583014ca547.jsonl"
lines=open(p,encoding="utf-8",errors="replace").read().splitlines()
out=[]
for ln in lines:
    try:o=json.loads(ln)
    except:continue
    if o.get("type")!="message":continue
    role=o.get("role");c=o.get("content")
    t=""
    if isinstance(c,str):t=c
    elif isinstance(c,list):
        t=" ".join(b.get("text","") for b in c if isinstance(b,dict) and b.get("type") in ("input_text","output_text","text"))
    t=t.strip()
    if t:out.append((role,t))
# print everything from the 16:41:03 user msg onward
idx=None
for i,(role,t) in enumerate(out):
    if "base不要0.8" in t: idx=i
print("idx",idx,"total",len(out))
for role,t in out[idx:]:
    print("##### ",role,"len",len(t))
    print(t[:3000])
    print()
