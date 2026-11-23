cd /home/aistudio/up/in
curl -sSL --max-time 180 -o u01.bin 'https://ntfy.sh/file/Xkvmg2gJY6Cg.json'
cp u01.bin /home/aistudio/dlg_in/spec_e.json
cd /home/aistudio
rm -rf cand_e && mkdir -p cand_e
sed 's#/home/aistudio/cand#/home/aistudio/cand_e#' _cloud_gen.py > _gen_e.py
(setsid nohup python3 -u _gen_e.py /home/aistudio/dlg_in/spec_e.json > gen_e.log 2>&1 </dev/null &)
sleep 20
tail -2 gen_e.log
ls cand_e/*.wav | wc -l
