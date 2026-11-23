cd /home/aistudio
mkdir -p dlg_in dlg_out
cat > dlg_in/test.jsonl <<'JSON'
{"id":"t1","text":"C'est mon pere qui va te mettre dehors.","voice":"Thomas_loud_1"}
{"id":"t2","text":"C'est mon pere qui va te mettre dehors.","voice":"Thomas_defiant_1"}
JSON
python3 loops.py --plan dlg_in/test.jsonl --only dialog --out /home/aistudio/dlg_out --tmp /home/aistudio/posttmp --log /home/aistudio/dlg_test.jsonl 2>&1 | tail -12
echo "=== FILES ==="
ls -l /home/aistudio/dlg_out/t*.wav
