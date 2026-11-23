#!/bin/bash
# pinned-IP multi-range downloader, resumes from existing .partN (N=8 layout)
# usage: bash dlpin.sh 18.65.214.105,18.65.214.128 8
cd /home/aistudio || exit 1
URL=https://dl.fbaipublicfiles.com/speech_expressivity_evaluation/EmphAssess/EmphaClass/EmphaClass-en.tar.gz
OUT=/home/aistudio/models/EmphaClass/EmphaClass-en.tar.gz
T=3571288236
IPS=${1:-18.65.214.105}
N=${2:-8}
SPAN=$((T/N))
IFS=, read -ra ARR <<< "$IPS"
CN=${#ARR[@]}
for i in $(seq 0 $((N-1))); do
  S=$((i*SPAN)); E=$((S+SPAN-1)); [ $i -eq $((N-1)) ] && E=$((T-1)); P=$OUT.part$i
  IP=${ARR[$((i%CN))]}
  ( while :; do
      H=$(stat -c%s "$P" 2>/dev/null || echo 0)
      S2=$((S+H)); [ "$S2" -gt "$E" ] && break
      curl -sS --max-time 900 --retry 2 --retry-delay 2 --resolve dl.fbaipublicfiles.com:443:$IP -r $S2-$E "$URL" >> "$P" 2>/dev/null
      H2=$(stat -c%s "$P" 2>/dev/null || echo 0)
      [ "$H2" -le "$H" ] && sleep 2
    done ) &
done
wait
C=0; for i in $(seq 0 $((N-1))); do C=$((C + $(stat -c%s "$OUT.part$i" 2>/dev/null || echo 0))); done
if [ "$C" = "$T" ]; then
  rm -f "$OUT"; for i in $(seq 0 $((N-1))); do cat "$OUT.part$i" >> "$OUT"; done
  for i in $(seq 0 $((N-1))); do rm -f "$OUT.part$i"; done
  echo "MERGED $(stat -c%s $OUT)"
else
  echo "INCOMPLETE $C / $T"
fi
