import json, collections
lib=json.load(open(r'G:/_setup/_emo_refs_all.json',encoding='utf-8'))
have={r:set(v.keys()) for r,v in lib.items() if isinstance(v,dict)}
print("== 参考库现有档 ==")
for r,s in have.items(): print(f"  {r:10s} {sorted(s)}")

EMO2EN={'激动反抗':['loud','defiant','angry','scold'],'平静':['calm','neutral','normal'],
        '紧张':['nervous','panic'],'警惕':['wary'],'委屈':['soft','wronged','begging'],'兴奋':['excited']}
plan=[json.loads(l) for l in open(r'G:/_setup/_castle_en_ch123_plan_v2.jsonl',encoding='utf-8') if l.strip()]
dlg=[r for r in plan if r.get('speaker')!='narrator']
print(f"\n== 缺档统计（对白 {len(dlg)} 条）==")
miss=collections.Counter()
for r in dlg:
    role='Thomas' if r['speaker']=='Edmund' else r['speaker']
    emo=r.get('emo')
    cands=EMO2EN.get(emo,[])
    if role in have:
        ok=any(c in have[role] for c in cands)
        if not ok:
            miss[(role,emo)]+=1
print("角色/情绪组合 → 库内无对应档：")
tot=0
for (role,emo),n in sorted(miss.items(), key=lambda x:-x[1]):
    print(f"  {role:10s} {emo:8s} {n:3d} 条   库内有: {sorted(have.get(role,[]))}")
    tot+=n
print(f"  合计 {tot} 条 / {len(dlg)} = {tot/len(dlg)*100:.1f}% 无档可用")
