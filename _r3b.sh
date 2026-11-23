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

CURLY = "\u2018I don\u2019t know.\u2019"
STRAIGHT = "\'I don\'t know.\'"
PLAIN = "I do not know."
tests = [
    ('A_curly', CURLY, 'Charles_excited_1'),
    ('B_straight', STRAIGHT, 'Charles_excited_1'),
    ('C_plain', PLAIN, 'Charles_excited_1'),
    ('D_neutral_curly', CURLY, 'Charles_neutral_1'),
    ('E_soft_curly', CURLY, 'Charles_soft_1'),
]
for name, txt, v in tests:
    p = '/tmp/%s.wav' % name
    try:
        sz = gen(txt, v, p)
        print('%-16s %-18s bytes=%-7d' % (name, v, sz))
    except Exception as e:
        print('%-16s %-18s ERR %s' % (name, v, str(e)[:90]))
PY
