import json, os
for b in ['B000','B001']:
    p=f'G:/_setup/_narr_new/rep/{b}.json'
    if os.path.exists(p):
        d=json.load(open(p,encoding='utf-8'))
        print(f"=== {b} 停顿移植报告 ===")
        print(json.dumps(d,ensure_ascii=False,indent=1)[:900])
        print()
