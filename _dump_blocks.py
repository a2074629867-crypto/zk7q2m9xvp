import json, collections
blocks=json.load(open(r'G:/_setup/_narr_blocks.json',encoding='utf-8'))
by=collections.OrderedDict()
for x in blocks: by.setdefault(x['chapter'],[]).append(x)
with open(r'G:/_setup/_narr_blocks_view.txt','w',encoding='utf-8') as f:
    for ch,bs in by.items():
        f.write(f"\n########## {ch}  ({len(bs)} 块, {sum(b['words'] for b in bs)} 词) ##########\n")
        for b in bs:
            f.write(f"\n[{b['bid']}] n={b['n']} words={b['words']}\n{b['text']}\n")
print("written", sum(len(v) for v in by.values()), "blocks")
for ch,bs in by.items(): print(ch, len(bs), sum(b['words'] for b in bs))
