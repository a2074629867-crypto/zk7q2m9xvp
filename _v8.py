import json
b=json.load(open(r'G:/_setup/_narr_blocks.json',encoding='utf-8'))
print("type",type(b))
if isinstance(b,dict): print("keys",list(b.keys())[:5])
blocks = b if isinstance(b,list) else (b.get('blocks') or [])
print("块数",len(blocks))
print("\n字段:",list(blocks[0].keys()))
for x in blocks[:2]:
    print(f"\n--- {x['bid']} ch={x['chapter']} n={x['n']} words={x['words']}")
    print(x['text'][:300])
