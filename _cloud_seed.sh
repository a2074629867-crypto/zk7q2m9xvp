cd /home/aistudio
python3 - <<'PY'
import json, urllib.request, hashlib, time
U="http://127.0.0.1:8080/v1/audio/speech"
def gen(body):
    req=urllib.request.Request(U,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    t0=time.time()
    try:
        with urllib.request.urlopen(req,timeout=300) as r: d=r.read()
        return hashlib.md5(d).hexdigest()[:12], len(d), round(time.time()-t0,2)
    except Exception as e:
        return "ERR %s"%e, 0, round(time.time()-t0,2)
t="C'est mon pere qui va te mettre dehors."
base={"model":"dots","input":t,"voice":"Thomas_loud_1"}
print("run1", gen(base))
print("run2", gen(base))
b2=dict(base); b2["seed"]=7
print("seed7", gen(b2))
b3=dict(base); b3["seed"]=11
print("seed11", gen(b3))
PY
