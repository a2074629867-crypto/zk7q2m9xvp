cd /home/aistudio/up && mkdir -p in && cd in
curl -sSL --max-time 180 -o a1.bin 'https://ntfy.sh/file/Kxo4up1Xm4BT.json'
curl -sSL --max-time 180 -o a2.bin 'https://ntfy.sh/file/orzayao6XcdZ.txt'
cp a1.bin /home/aistudio/dlg_in/spec.json
cp a2.bin /home/aistudio/_cloud_gen.py
ls -l /home/aistudio/dlg_in/spec.json /home/aistudio/_cloud_gen.py
head -c 120 /home/aistudio/_cloud_gen.py
echo
python3 -c "import json;d=json.load(open('/home/aistudio/dlg_in/spec.json'));print('items',len(d['items']))"
