cd /home/aistudio
grep -c '^Thomas_defiant_1|' voice_lib/prompt_text
cat > dlg_in/t2.jsonl <<'JSON'
{"id":"t3","text":"C'est mon pere qui va te mettre dehors.","voice":"Thomas_defiant_1"}
{"id":"t4","text":"C'est mon pere qui va te mettre dehors.","voice":"Charles_neutral_4"}
JSON
python3 loops.py --plan dlg_in/t2.jsonl --only dialog --out /home/aistudio/dlg_out --tmp /home/aistudio/posttmp --log /home/aistudio/dlg_test.jsonl 2>&1 | grep -E '^\[|LOOPS|QC' 
python3 - <<'PY'
import wave
for n in ("t3","t4"):
    try:
        w=wave.open("/home/aistudio/dlg_out/%s.wav"%n)
        print(n, "%.2fs"%(w.getnframes()/w.getframerate()), w.getframerate())
    except Exception as e: print(n,"ERR",e)
PY
