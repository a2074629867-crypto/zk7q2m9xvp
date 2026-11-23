import re, statistics, json
from pathlib import Path
D = Path('G:/_setup/gsv5probe/logs/mcconaughey_v5full_df3hp')
rows = []
for fn in ['6-name2semantic.tsv','6-name2semantic_filtered.tsv']:
    p = D/fn
    if not p.exists(): continue
    hzs=[]; toks=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        parts = line.strip().split('\t')
        if len(parts) < 2: continue
        m = re.search(r'_(\d+)_(\d+)\.wav$', parts[0])
        if not m: continue
        dur = (int(m.group(2)) - int(m.group(1)))/32000.0
        ids = [int(x) for x in parts[1].split()]
        hzs.append(len(ids)/dur); toks.append(len(ids))
        rows.append((fn, dur, len(ids), len(ids)/dur))
    print(f'--- {fn}  n={len(hzs)} ---')
    print(f'  token 数: min={min(toks)} med={statistics.median(toks)} max={max(toks)}')
    print(f'  帧率 Hz : min={min(hzs):.2f} med={statistics.median(hzs):.2f} max={max(hzs):.2f} mean={statistics.mean(hzs):.2f}')
# 也看看 base s1v3 推理时用的语义token（参考音频）
