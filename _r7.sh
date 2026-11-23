set -e
cd /home/aistudio
curl -sL -o refill33.jsonl 'https://ntfy.sh/file/f3PQey5YDcVn.ndjson'
echo "LINES=$(wc -l < refill33.jsonl)"
mkdir -p out_bak_r5
python3 - <<'PY'
import json, os, shutil
ids=[]
for l in open('refill33.jsonl'):
    l=l.strip()
    if l: ids.append(json.loads(l)['id'])
n=0
for i in ids:
    p='out/%s.wav'%i
    if os.path.exists(p):
        shutil.copy(p,'out_bak_r5/'); n+=1
print('BACKUP',n,'of',len(ids))
for i in ids:
    for p in ('out/%s.wav'%i,'out/%s.wav.edit.wav'%i):
        if os.path.exists(p): os.remove(p)
print('CLEARED')
PY
python3 loops.py --plan refill33.jsonl --only dialog 2>&1 | tail -18
echo "OUT=$(ls out/*.wav | wc -l)"
