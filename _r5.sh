cd /home/aistudio
IDS="c2_0265 c2_0295 c2_0309 c2_0314 c2_0358 c2_0467 c2_0469 c3_0625 c3_0629 c3_0655 c3_0872"
FILES=""
for i in $IDS; do FILES="$FILES out/$i.wav"; done
tar czf r4.tgz $FILES
ls -l r4.tgz
curl -s -T r4.tgz -H "Filename: r4.tgz" https://ntfy.sh/tts_o7k2mq
