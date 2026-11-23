set -e
cd /home/aistudio
python3 - <<'PY'
import json, os, urllib.request
U = 'http://127.0.0.1:8080/v1/audio/speech'
def gen(text, voice, out):
    body = json.dumps({"model": "dots", "input": text, "voice": voice}).encode()
    req = urllib.request.Request(U, data=body, headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=300)
    open(out, 'wb').write(r.read())
    return os.path.getsize(out)
tests = [
    ('x1', "I do not know.", 'Charles_excited_2'),
    ('x2', "I do not know.", 'Charles_excited_3'),
    ('x3', "Do not be stupid.", 'Charles_excited_2'),
    ('x4', "I do not want to.", 'Charles_excited_2'),
]
for name, txt, v in tests:
    p = '/tmp/%s.wav' % name
    try:
        print('%-4s %-18s bytes=%d' % (name, v, gen(txt, v, p)))
    except Exception as e:
        print('%-4s ERR %s' % (name, str(e)[:80]))
PY
