cd /home/aistudio/up/in
curl -sSL --max-time 180 -o u01.bin 'https://ntfy.sh/file/oTfEdxWtL4BZ.json'
cp u01.bin /home/aistudio/dlg_in/spec_g.json
cd /home/aistudio
rm -rf cand_g && mkdir -p cand_g
sed 's#/home/aistudio/cand#/home/aistudio/cand_g#' _cloud_gen.py > _gen_g.py
(setsid nohup python3 -u _gen_g.py /home/aistudio/dlg_in/spec_g.json > gen_g.log 2>&1 </dev/null &)
sleep 25
tail -2 gen_g.log
ls cand_g/*.wav 2>/dev/null | wc -l
