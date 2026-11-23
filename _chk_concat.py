import json, os
blocks=json.load(open(r'G:/_setup/_narr_blocks.json',encoding='utf-8'))
plan={json.loads(l)['id']:json.loads(l) for l in open(r'G:/_setup/_castle_en_ch123_plan_v2.jsonl',encoding='utf-8') if l.strip()}
bad=0; okc=0
for b in blocks:
    ids=b['ids']
    txt=' '.join((plan.get(i) or {}).get('text','') for i in ids).strip()
    t1=' '.join(txt.split())
    t2=' '.join(b['text'].split())
    if t1!=t2:
        bad+=1
        if bad<=3:
            print(f"[差异] {b['bid']} 缺句:{[i for i in ids if i not in plan]}")
            # 找第一个不同位置
            for k in range(min(len(t1),len(t2))):
                if t1[k]!=t2[k]:
                    print(f"   首个差异@{k}: block={t2[max(0,k-30):k+50]!r}")
                    print(f"                  concat={t1[max(0,k-30):k+50]!r}")
                    break
            else:
                print(f"   长度不同 block={len(t2)} concat={len(t1)}")
    else:
        okc+=1
print(f"\n完全一致 {okc}/{len(blocks)}，不一致 {bad}")
# 音频是否齐全
miss=[]
for b in blocks:
    for i in b['ids']:
        p=f"G:/_setup/_audio_ch123/out/{i}.wav"
        if not os.path.exists(p): miss.append(i)
print("缺失音频:",len(miss), miss[:5])
