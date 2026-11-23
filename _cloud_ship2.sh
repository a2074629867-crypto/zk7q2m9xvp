cd /home/aistudio
tar czf /home/aistudio/cand_loud.tgz -C /home/aistudio cand_loud
ls -lh /home/aistudio/cand_loud.tgz
U=$(curl -sS --max-time 900 -A "Mozilla/5.0" -F "reqtype=fileupload" -F "time=72h" -F "fileToUpload=@/home/aistudio/cand_loud.tgz" https://litterbox.catbox.moe/resources/internals/api.php)
echo "URL=$U"
