set -e
cd /home/aistudio
curl -sL -o regen4.jsonl 'https://ntfy.sh/file/foWwcwYVk81n.ndjson'
echo "LINES=$(wc -l < regen4.jsonl)"
mkdir -p out_bak_r6
python3 - <<'PY'
import json, os, shutil
ids=[json.loads(l)['id'] for l in open('regen4.jsonl') if l.strip()]
n=0
for i in ids:
    p='out/%s.wav'%i
    if os.path.exists(p):
        shutil.copy(p,'out_bak_r6/'); n+=1
print('BACKUP',n,'of',len(ids))
for i in ids:
    for p in ('out/%s.wav'%i,'out/%s.wav.edit.wav'%i):
        if os.path.exists(p): os.remove(p)
print('CLEARED')
PY
python3 loops.py --plan regen4.jsonl --only dialog 2>&1 | tail -16
echo "=== 打包 ==="
python3 - <<'PY'
import json,os
ids=[json.loads(l)['id'] for l in open('regen4.jsonl') if l.strip()]
files=' '.join('out/%s.wav'%i for i in ids)
os.system('tar czf r10.tgz '+files)
print('SIZE',round(os.path.getsize('r10.tgz')/1024,1),'KB')
PY
curl -s -T r10.tgz -H "Filename: r10.tgz" https://ntfy.sh/tts_o7k2mq
echo
