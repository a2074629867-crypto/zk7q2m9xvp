set -e
cd /home/aistudio
curl -sL -o regen11.jsonl 'https://ntfy.sh/file/tag1f7yDJrF2.ndjson'
echo "LINES=$(wc -l < regen11.jsonl)"
mkdir -p out_bak_r4
python3 - <<'PY'
import json, os, shutil
n = 0
ids = []
for l in open('regen11.jsonl'):
    l = l.strip()
    if not l:
        continue
    i = json.loads(l)['id']
    ids.append(i)
    p = 'out/%s.wav' % i
    if os.path.exists(p):
        shutil.copy(p, 'out_bak_r4/')
        n += 1
print('BACKUP', n)
for i in ids:
    for p in ('out/%s.wav' % i, 'out/%s.wav.edit.wav' % i):
        if os.path.exists(p):
            os.remove(p)
print('CLEARED', len(ids))
PY
python3 loops.py --plan regen11.jsonl --only dialog 2>&1 | tail -20
