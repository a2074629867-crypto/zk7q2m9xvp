set -e
cd /home/aistudio
curl -sL -o newrefs.tgz 'https://ntfy.sh/file/egh24Fykbsl2.gz'
cp -a voice_lib voice_lib_bak_new
tar xzf newrefs.tgz -C voice_lib
echo "REFS=$(ls voice_lib/*.wav | wc -l)  PROMPT=$(wc -l < voice_lib/prompt_text)"
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
    ('n1', "I don't want to go down there. Something is wrong.", 'Charles_nervous_1'),
    ('w1', "Why are you following me? Keep your mouth shut.", 'Charles_wary_1'),
    ('d1', "I told you to get out. I never want to see you again!", 'Charles_defiant_1'),
    ('t1', "Let's go up. I'm not afraid. Come on, hurry.", 'Thomas_nervous_1'),
    ('t2', "You should have noticed we were gone by now.", 'Thomas_wary_1'),
]
for name, txt, v in tests:
    p = '/tmp/%s.wav' % name
    try:
        print('%-4s %-20s bytes=%d' % (name, v, gen(txt, v, p)))
    except Exception as e:
        print('%-4s %-20s ERR %s' % (name, v, str(e)[:90]))
PY
