import json, collections
old={}
for l in open(r'G:/_setup/_dlg_plan.jsonl',encoding='utf-8'):
    l=l.strip()
    if not l: continue
    r=json.loads(l); old[r['id']]=r
final={}
for l in open(r'G:/_setup/_emo_vote/_emo_final.jsonl',encoding='utf-8'):
    l=l.strip()
    if not l: continue
    r=json.loads(l); final[r['id']]=r
common=set(old)&set(final)
print("旧 plan",len(old),"新投票",len(final),"交集",len(common))
chg=[k for k in common if old[k]['emo']!=final[k]['emo']]
print(f"\n情绪档变化: {len(chg)}/{len(common)} = {len(chg)/len(common)*100:.1f}%")
print("\n== 变化方向 (旧 → 新) ==")
cc=collections.Counter((old[k]['emo'],final[k]['emo']) for k in chg)
for (a,b),n in cc.most_common(20): print(f"  {a:6s} → {b:6s}  {n:3d}")
print("\n== 新分布 ==")
for k,v in collections.Counter(final[x]['emo'] for x in common).most_common(): print(f"  {k:6s} {v:3d}")
print("\n== 旧分布 ==")
for k,v in collections.Counter(old[x]['emo'] for x in common).most_common(): print(f"  {k:6s} {v:3d}")
print("\n== 样例变化（前 12）==")
for k in chg[:12]:
    print(f"  {k:10s} {old[k]['who']:8s} {old[k]['emo']} → {final[k]['emo']}  src={final[k]['src']} votes={final[k]['votes']}")
    print(f"      {final[k]['why'][:40]}  | {(old[k].get('text') or '')[:52]}")
