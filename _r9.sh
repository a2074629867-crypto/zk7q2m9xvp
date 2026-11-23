cd /home/aistudio
python3 - <<'PY'
import json,os
ids=[json.loads(l)['id'] for l in open('refill33.jsonl') if l.strip()]
part=ids[8:16]
for k,chunk in enumerate([part[:4],part[4:]],1):
    files=' '.join('out/%s.wav'%i for i in chunk)
    os.system('tar czf r6_%d.tgz %s'%(k,files))
    print(k,len(chunk),round(os.path.getsize('r6_%d.tgz'%k)/1048576,2),'MB',chunk)
PY
for k in 1 2; do curl -s -T r6_$k.tgz -H "Filename: r6_$k.tgz" https://ntfy.sh/tts_o7k2mq; echo " <- p$k"; sleep 4; done
