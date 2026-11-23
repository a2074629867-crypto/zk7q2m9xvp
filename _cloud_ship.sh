cd /home/aistudio
tar czf /home/aistudio/cand_bcg.tgz -C /home/aistudio cand
ls -lh /home/aistudio/cand_bcg.tgz
python3 - <<'PY'
import json
rows=json.load(open("/home/aistudio/cand/manifest.json",encoding="utf-8"))
ok=[r for r in rows if r.get("dur")]
short=[r for r in ok if r["dur"]<0.7]
print("候选 %d，dur<0.7s 的 %d 条"%(len(ok),len(short)))
print("dur 中位 %.2f"%sorted(r["dur"] for r in ok)[len(ok)//2])
PY
U=$(curl -sS --max-time 600 -A "Mozilla/5.0" -F "reqtype=fileupload" -F "time=72h" -F "fileToUpload=@/home/aistudio/cand_bcg.tgz" https://litterbox.catbox.moe/resources/internals/api.php)
echo "URL=$U"
