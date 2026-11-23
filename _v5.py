import json, collections
d=json.load(open(r'G:/_setup/_emo_refs_all.json',encoding='utf-8'))
print("type",type(d))
if isinstance(d,dict):
    print("顶层键:",list(d.keys())[:12])
    # 探测结构
    k0=list(d.keys())[0]
    print("样例",k0,":",json.dumps(d[k0],ensure_ascii=False)[:300])
