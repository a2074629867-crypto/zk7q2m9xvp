import json
p=r"D:\wb2api-cli\account-01\projects\c-Users-86178-WorkBuddy-2026-10-05-00-50-22\wb6f61cfe8fabb1c105a583014ca547.jsonl"
lines=open(p,encoding="utf-8",errors="replace").read().splitlines()
for i,ln in enumerate(lines[:3]+lines[-6:]):
    try: o=json.loads(ln)
    except Exception as e:
        print(i,"ERR",e); continue
    print("----",i,type(o))
    print(json.dumps(o,ensure_ascii=False)[:800])
