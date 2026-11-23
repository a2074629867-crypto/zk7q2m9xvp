import json
d=json.load(open(r'G:/_setup/_emo_refs_all.json',encoding='utf-8'))
for role,v in d.items():
    if isinstance(v,dict):
        print(role, "->", list(v.keys()))
        k=list(v.keys())[0]
        print("    sample entry type:", type(v[k]).__name__, str(v[k])[:120])
    elif isinstance(v,list):
        print(role,"-> list len",len(v), str(v[0])[:150] if v else "")
