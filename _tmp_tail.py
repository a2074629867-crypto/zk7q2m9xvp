import json,sys
p=r"D:\wb2api-cli\account-01\projects\c-Users-86178-WorkBuddy-2026-10-05-00-50-22\wb6f61cfe8fabb1c105a583014ca547.jsonl"
lines=open(p,encoding="utf-8",errors="replace").read().splitlines()
print("total lines",len(lines))
def text(m):
    c=m.get("content")
    if isinstance(c,str): return c
    out=[]
    if isinstance(c,list):
        for b in c:
            if isinstance(b,dict):
                if b.get("type")=="text": out.append(b.get("text",""))
                elif b.get("type")=="tool_use": out.append("[TOOL %s]"%b.get("name"))
                elif b.get("type")=="tool_result": out.append("[RESULT]")
    return " ".join(out)
msgs=[]
for ln in lines:
    try: o=json.loads(ln)
    except: continue
    msg=o.get("message") or o
    role=msg.get("role") or o.get("type")
    t=text(msg).strip()
    if t: msgs.append((role,t))
for role,t in msgs[-14:]:
    print("=== ",role," len",len(t))
    print(t[:1200])
