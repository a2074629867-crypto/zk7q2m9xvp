import json
b=json.load(open(r'G:/_setup/_rhythm_bands.json',encoding='utf-8'))
print(json.dumps(b, ensure_ascii=False, indent=2)[:2000])
