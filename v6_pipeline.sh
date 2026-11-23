#!/usr/bin/env bash
# v6_pipeline.sh —— 用 max_sil_kept=700 重切后的数据重建训练集
#
# 背景：旧切片 max_sil_kept=3000 ⇒ 语音占比中位仅 0.558、52% 的片含 >1s 静音
#       新切片 max_sil_kept=700 ⇒ 语音占比 0.708、仅 2% 含 >1s 静音
# 流程：生成锚点 → 词流重挂 → 1-get-text → 2-get-hubert → 3-get-semantic
set -u

REPO=/g/_setup/gsv5probe
PY="G:/Python310/python.exe"
DSROOT="G:/GPT-SoVITS/_dataset_v5full"
SLICED="$DSROOT/sliced_v6"
WORDS="$DSROOT/wonder_hp.json"          # 全局词流（含 windows/slices[].words）
EXP="mcconaughey_v6"
VER="v5turbo"
LOG=/g/_setup/v6_pipeline.log

export PATH="/e/tool/oopz:$PATH"
export NLTK_DATA=G:/nltk_data
export HF_HOME="C:/Users/86178/.cache/huggingface"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export version="$VER"
export EXP="$EXP"
export PYTHONUNBUFFERED=1

cd "$REPO" || exit 1
ts() { date +"%H:%M:%S"; }
say() { echo "[$(ts)] $*"; }

# ---- 0. 生成新切片锚点 ----
say "=========== 0. 生成 slices_v6.json ==========="
"$PY" - <<'PYEOF'
import json, re, os
D = 'G:/GPT-SoVITS/_dataset_v5full'
SR = 32000
out = []
for f in sorted(os.listdir(D + '/sliced_v6')):
    if not f.endswith('.wav'): continue
    m = re.search(r'_(\d+)_(\d+)\.wav$', f)
    if not m: continue
    out.append({'file': f, 't0': int(m.group(1))/SR, 't1': int(m.group(2))/SR})
json.dump({'slices': out}, open(D + '/slices_v6.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('slices_v6.json: %d 段, 总 %.1f min' % (len(out), sum(s['t1']-s['t0'] for s in out)/60))
PYEOF

# ---- 1. 词流重挂到新切片 ----
say "=========== 1. 词流重挂 ==========="
"$PY" -u /g/_setup/v5full_reassign.py \
  --words-json "$WORDS" \
  --slices-json "$DSROOT/slices_v6.json" \
  --sliced-dir "$SLICED" \
  --out "$DSROOT/wonder_v6" \
  --speaker Calm --lang en
say "wonder_v6.list: $(wc -l < "$DSROOT/wonder_v6.list" 2>/dev/null) 行"
if [ ! -s "$DSROOT/wonder_v6.list" ]; then say "ERROR: list 为空"; exit 1; fi

LIST="$DSROOT/wonder_v6.list"
OPT="logs/$EXP"
rm -rf "$OPT"; mkdir -p "$OPT"

say "=========== 2. 1-get-text ==========="
inp_text="$LIST" inp_wav_dir="$SLICED" exp_name="$EXP" opt_dir="$OPT" \
bert_pretrained_dir="GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large" \
is_half="False" i_part="0" all_parts="1" _CUDA_VISIBLE_DEVICES="0" \
"$PY" -s GPT_SoVITS/prepare_datasets/1-get-text.py
mv -f "$OPT/2-name2text-0.txt" "$OPT/2-name2text.txt" 2>/dev/null
say "2-name2text.txt: $(wc -l < "$OPT/2-name2text.txt" 2>/dev/null) 行"
[ -s "$OPT/2-name2text.txt" ] || { say "ERROR: 2-name2text 为空"; exit 1; }

say "=========== 3. 2-get-hubert-wav32k ==========="
inp_text="$LIST" inp_wav_dir="$SLICED" exp_name="$EXP" opt_dir="$OPT" \
cnhubert_base_dir="GPT_SoVITS/pretrained_models/chinese-hubert-base" sv_path="" \
is_half="False" i_part="0" all_parts="1" _CUDA_VISIBLE_DEVICES="0" \
"$PY" -s GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py
say "4-cnhubert: $(ls "$OPT/4-cnhubert" 2>/dev/null | wc -l) 个"

say "=========== 4. 3-get-semantic ==========="
inp_text="$LIST" exp_name="$EXP" opt_dir="$OPT" \
pretrained_s2G="GPT_SoVITS/pretrained_models/gsv-v5-pretrained/s2Gv5turbo.pth" \
s2config_path="GPT_SoVITS/configs/s2.json" \
is_half="False" i_part="0" all_parts="1" _CUDA_VISIBLE_DEVICES="0" \
"$PY" -s GPT_SoVITS/prepare_datasets/3-get-semantic.py
[ -f "$OPT/6-name2semantic-0.tsv" ] && cp -f "$OPT/6-name2semantic-0.tsv" "$OPT/6-name2semantic.tsv"
say "6-name2semantic.tsv: $(wc -l < "$OPT/6-name2semantic.tsv" 2>/dev/null) 行"

say "=========== 完成，可开始训练 ==========="
say "OPT=$OPT"
say "ALLDONE"
