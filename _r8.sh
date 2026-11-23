cd /home/aistudio
python3 - <<'PY'
import json,os
ids=[json.loads(l)['id'] for l in open('refill33.jsonl') if l.strip()]
chunks=[ids[i:i+8] for i in range(0,len(ids),8)]
for k,chunk in enumerate(chunks,1):
    files=' '.join('out/%s.wav'%i for i in chunk)
    os.system('tar czf r5_%d.tgz %s'%(k,files))
    print(k,len(chunk),round(os.path.getsize('r5_%d.tgz'%k)/1048576,2),'MB')
PY
for k in 1 2 3 4 5; do [ -f r5_$k.tgz ] && { curl -s -T r5_$k.tgz -H "Filename: r5_$k.tgz" https://ntfy.sh/tts_o7k2mq; echo " <- pkg$k"; sleep 3; }; done
