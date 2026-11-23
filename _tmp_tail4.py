import json,io,sys
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
for name in ["wb6f61cfe8fabb1c105a583014ca547.jsonl"]:
    p=r"D:\wb2api-cli\account-01\projects\c-Users-86178-WorkBuddy-2026-10-05-00-50-22\\"+name
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
    for role,t in out:
        if role=="user":
            print("=== USER len",len(t))
            print(t[:2500].replace("\n"," | "))
            print()
