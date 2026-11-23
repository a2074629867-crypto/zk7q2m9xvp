import re, statistics, collections
from pathlib import Path
D = Path('G:/_setup/gsv5probe/logs/mcconaughey_v5full_df3hp')

def load(fn):
    seqs=[]
    for line in (D/fn).read_text(encoding='utf-8').splitlines():
        p=line.strip().split('\t')
        if len(p)<2: continue
        seqs.append([int(x) for x in p[1].split()])
    return seqs

for fn in ['6-name2semantic.tsv','6-name2semantic_filtered.tsv']:
    seqs = load(fn)
    if not seqs: continue
    print(f'###### {fn}  n={len(seqs)} ######')
    tot = collections.Counter()
    for s in seqs: tot.update(s)
    print('  全部 token Top10:', tot.most_common(10))
    print(f'  唯一 token 数={len(tot)}  总量={sum(tot.values())}')
    # 开头 12 个
    first12 = collections.Counter()
    for s in seqs: first12.update(s[:12])
    print('  前12 token Top8 :', first12.most_common(8))
    # 末尾 12 个
    last12 = collections.Counter()
    for s in seqs: last12.update(s[-12:])
    print('  末12 token Top8 :', last12.most_common(8))
    # 头尾集中度
    print(f'  前12集中度: {first12.most_common(3)[0][1]/max(1,sum(first12.values())):.3f}')
    print(f'  末12集中度: {last12.most_common(3)[0][1]/max(1,sum(last12.values())):.3f}')
    # 长度分布
    L=[len(s) for s in seqs]
    print(f'  长度: min={min(L)} med={statistics.median(L):.0f} max={max(L)}  总={sum(L)}')
    # 每个序列开头有多少个"静音token"(用全局Top1当静音代理)
    silence_ids = {tot.most_common(1)[0][0]}
    lead=[]
    for s in seqs:
        c=0
        for t in s:
            if t in silence_ids: c+=1
            else: break
        lead.append(c)
    print(f'  开头连续静音token: med={statistics.median(lead):.0f} mean={statistics.mean(lead):.1f} 占比>25的={sum(1 for x in lead if x>25)}/{len(lead)}')
    print()
