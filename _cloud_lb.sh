cd /home/aistudio/dlg_out
ls -l
curl -sS --max-time 120 -A "Mozilla/5.0" -F "reqtype=fileupload" -F "time=72h" -F "fileToUpload=@t4.wav" https://litterbox.catbox.moe/resources/internals/api.php
echo
echo "--- catbox try ---"
curl -sS --max-time 120 -A "Mozilla/5.0" -F "reqtype=fileupload" -F "fileToUpload=@t4.wav" https://catbox.moe/user/api.php
echo
