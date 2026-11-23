set -e
cd /home/aistudio
curl -sL -o regen7.jsonl 'https://ntfy.sh/file/AUQrj2pYfOea.ndjson'
echo "LINES=$(wc -l < regen7.jsonl) BACKUP=$(ls out_bak_r3 | wc -l)"
python3 - <<'PY'
import json, os
n = 0
for l in open('regen7.jsonl'):
    l = l.strip()
    if not l:
        continue
    i = json.loads(l)['id']
    for p in ('out/%s.wav' % i, 'out/%s.wav.edit.wav' % i):
        if os.path.exists(p):
            os.remove(p)
            n += 1
print('CLEARED', n)
PY
echo "REMAIN=$(ls out/*.wav | wc -l)"
python3 loops.py --plan regen7.jsonl --only dialog 2>&1 | tail -22
