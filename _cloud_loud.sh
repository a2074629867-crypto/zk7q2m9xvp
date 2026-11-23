cd /home/aistudio/up/in
curl -sSL --max-time 180 -o u01.bin 'https://ntfy.sh/file/Tscsu6GqQksR.json'
cp u01.bin /home/aistudio/dlg_in/spec_loud.json
wc -c /home/aistudio/dlg_in/spec_loud.json
cd /home/aistudio
rm -rf cand_loud && mkdir -p cand_loud
sed 's#/home/aistudio/cand#/home/aistudio/cand_loud#' _cloud_gen.py > _gen_loud.py
grep -n 'cand_loud' _gen_loud.py | head -2
(setsid nohup python3 -u _gen_loud.py /home/aistudio/dlg_in/spec_loud.json > gen_loud.log 2>&1 </dev/null &)
sleep 15
tail -3 gen_loud.log
ls cand_loud/*.wav 2>/dev/null | wc -l
