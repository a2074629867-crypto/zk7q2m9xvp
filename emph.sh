#!/bin/bash
# EmphaClass-en weight download helper (persistent at /home/aistudio/emph.sh)
# usage: bash /home/aistudio/emph.sh resume | verify | status
M=/home/aistudio/models/EmphaClass
U=https://dl.fbaipublicfiles.com/speech_expressivity_evaluation/EmphAssess/EmphaClass/EmphaClass-en.tar.gz
T=3571288236
F=$M/EmphaClass-en.tar.gz
case "$1" in
resume)
  cd /home/aistudio || exit 1
  if pgrep -f dl_range.py >/dev/null; then echo ALREADY_RUNNING; pgrep -af dl_range.py; exit 0; fi
  setsid python3 -u dl_range.py $U $T $F 8 >> /home/aistudio/dl_en.log 2>&1 < /dev/null &
  sleep 3
  pgrep -af dl_range.py
  tail -n 2 /home/aistudio/dl_en.log
  ;;
verify)
  ls -l $F 2>/dev/null
  S=$(stat -c%s $F 2>/dev/null || echo 0)
  echo "SIZE=$S EXPECT=$T"
  if [ "$S" = "$T" ]; then echo SIZE_OK; else echo SIZE_BAD; fi
  if [ -f $F ]; then gzip -t $F && echo GZIP_OK || echo GZIP_BAD; tar -tzf $F | head -5; tar -tzf $F | wc -l; fi
  ;;
status)
  pgrep -af dl_range.py
  tail -n 3 /home/aistudio/dl_en.log
  du -sh $M 2>/dev/null
  ;;
*)
  echo "usage: emph.sh resume|verify|status"
  ;;
esac
