U=$(curl -sS --max-time 900 -A "Mozilla/5.0" -F "reqtype=fileupload" -F "time=72h" -F "fileToUpload=@/home/aistudio/cand_e.tgz" https://litterbox.catbox.moe/resources/internals/api.php)
echo "URL=$U"
