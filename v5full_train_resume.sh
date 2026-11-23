#!/usr/bin/env bash
# v5full_train_resume.sh —— 从已完成的标注继续（跳过切片与 ASR）
#
# 前置：$DSROOT/wonder_v5full_norm.list 已存在（整段转写切分 + 文本规范化后的标注）
# 流程：1-get-text → 2-get-hubert → 3-get-semantic → s2_train_v3_lora(v5turbo LoRA) → s1_train
set -u

REPO=/g/_setup/gsv5probe
PY="G:/Python310/python.exe"
DSROOT="G:/GPT-SoVITS/_dataset_v5full"
SLICED="$DSROOT/sliced"
LIST="$DSROOT/wonder_v5full_norm.list"
EXP="mcconaughey_v5full"
VER="v5turbo"
LOG=/g/_setup/v5full_train_resume.log

export PATH="/e/tool/oopz:$PATH"
export NLTK_DATA=G:/nltk_data
export HF_HOME="C:/Users/86178/.cache/huggingface"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export version="$VER"
export EXP="$EXP"
export PYTHONUNBUFFERED=1

cd "$REPO" || exit 1
mkdir -p TEMP logs "$DSROOT" "SoVITS_weights_$VER" "GPT_weights_$VER"

ts() { date +"%H:%M:%S"; }
say() { echo "[$(ts)] $*"; }

# ---- 前置检查 ----
if [ ! -s "$LIST" ]; then
  say "ERROR: 标注文件不存在或为空: $LIST"; exit 1
fi
NLIST=$(wc -l < "$LIST")
NSLICED=$(ls "$SLICED" 2>/dev/null | wc -l)
say "前置检查通过：标注 $NLIST 条 | 切片 $NSLICED 个"
if [ "$NLIST" -lt 300 ]; then
  say "WARN: 标注条数偏少（$NLIST），确认是否要按此继续"; sleep 3
fi

OPT="logs/$EXP"
# 清掉上次跑一半的残留（1-get-text 曾因空 list 产生空产物）
rm -rf "$OPT"
mkdir -p "$OPT"

say "=========== 1. 1-get-text ==========="
inp_text="$LIST" inp_wav_dir="$SLICED" exp_name="$EXP" opt_dir="$OPT" \
bert_pretrained_dir="GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large" \
is_half="False" i_part="0" all_parts="1" _CUDA_VISIBLE_DEVICES="0" \
"$PY" -s GPT_SoVITS/prepare_datasets/1-get-text.py
mv -f "$OPT/2-name2text-0.txt" "$OPT/2-name2text.txt" 2>/dev/null
say "2-name2text.txt: $(wc -l < "$OPT/2-name2text.txt" 2>/dev/null) 行"
if [ ! -s "$OPT/2-name2text.txt" ]; then say "ERROR: 2-name2text.txt 为空，中止"; exit 1; fi

say "=========== 2. 2-get-hubert-wav32k ==========="
inp_text="$LIST" inp_wav_dir="$SLICED" exp_name="$EXP" opt_dir="$OPT" \
cnhubert_base_dir="GPT_SoVITS/pretrained_models/chinese-hubert-base" sv_path="" \
is_half="False" i_part="0" all_parts="1" _CUDA_VISIBLE_DEVICES="0" \
"$PY" -s GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py
say "4-cnhubert: $(ls "$OPT/4-cnhubert" 2>/dev/null | wc -l) 个"

say "=========== 3. 3-get-semantic（v5turbo 预训练 SoVITS 提语义）==========="
inp_text="$LIST" exp_name="$EXP" opt_dir="$OPT" \
pretrained_s2G="GPT_SoVITS/pretrained_models/gsv-v5-pretrained/s2Gv5turbo.pth" \
s2config_path="GPT_SoVITS/configs/s2.json" \
is_half="False" i_part="0" all_parts="1" _CUDA_VISIBLE_DEVICES="0" \
"$PY" -s GPT_SoVITS/prepare_datasets/3-get-semantic.py
[ -f "$OPT/6-name2semantic-0.tsv" ] && cp -f "$OPT/6-name2semantic-0.tsv" "$OPT/6-name2semantic.tsv"
say "6-name2semantic.tsv: $(wc -l < "$OPT/6-name2semantic.tsv" 2>/dev/null) 行"

say "=========== 4. 构建 s2 训练配置 ==========="
"$PY" - <<'PYEOF'
import json, os
VER = os.environ['version']; EXP = os.environ['EXP']
d = json.load(open('GPT_SoVITS/configs/s2.json', encoding='utf-8'))
t = d['train']
t['fp16_run'] = False
t['batch_size'] = 4
t['epochs'] = 8
t['text_low_lr_rate'] = 0.4
t['log_interval'] = 10
t['eval_interval'] = 500
t['save_every_epoch'] = 1
t['if_save_latest'] = True
t['if_save_every_weights'] = True
t['grad_ckpt'] = False
t['lora_rank'] = 32
t['gpu_numbers'] = '0'
t['pretrained_s2G'] = 'GPT_SoVITS/pretrained_models/gsv-v5-pretrained/s2Gv5turbo.pth'
t['pretrained_s2D'] = ''
d['model']['version'] = VER
d['data']['exp_dir'] = d['s2_ckpt_dir'] = 'logs/%s' % EXP
d['save_weight_dir'] = 'SoVITS_weights_%s' % VER
d['name'] = EXP
d['version'] = VER
json.dump(d, open('TEMP/tmp_s2.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('  写出 TEMP/tmp_s2.json  batch=%s epochs=%s lora=%s ver=%s'
      % (t['batch_size'], t['epochs'], t['lora_rank'], VER))
PYEOF

say "=========== 5. 训练 SoVITS（v5turbo LoRA r32, 8 epoch）==========="
say "    目标模块 = net_g.cfm (22 层 DiT)，其余冻结"
"$PY" -s GPT_SoVITS/s2_train_v3_lora.py --config TEMP/tmp_s2.json
say "SoVITS 训练结束"
ls -la "SoVITS_weights_$VER/" 2>/dev/null

say "=========== 6. 构建 s1 训练配置 ==========="
"$PY" - <<'PYEOF'
import yaml, os
VER = os.environ['version']; EXP = os.environ['EXP']
d = yaml.load(open('GPT_SoVITS/configs/s1longer-v2.yaml', encoding='utf-8'), Loader=yaml.FullLoader)
d['train']['precision'] = '32'
d['train']['batch_size'] = 8
d['train']['epochs'] = 15
d['train']['save_every_n_epoch'] = 1
d['train']['if_save_every_weights'] = True
d['train']['if_save_latest'] = True
d['train']['if_dpo'] = False
d['train']['half_weights_save_dir'] = 'GPT_weights_%s' % VER
d['train']['exp_name'] = EXP
d['pretrained_s1'] = 'GPT_SoVITS/pretrained_models/s1v3.ckpt'
d['train_semantic_path'] = 'logs/%s/6-name2semantic.tsv' % EXP
d['train_phoneme_path'] = 'logs/%s/2-name2text.txt' % EXP
d['output_dir'] = 'logs/%s/logs_s1_%s' % (EXP, VER)
yaml.dump(d, open('TEMP/tmp_s1.yaml', 'w', encoding='utf-8'), default_flow_style=False)
print('  写出 TEMP/tmp_s1.yaml  batch=%s epochs=%s' % (d['train']['batch_size'], d['train']['epochs']))
PYEOF

say "=========== 7. 训练 GPT（t2s, 15 epoch）==========="
_CUDA_VISIBLE_DEVICES=0 hz=25hz "$PY" -s GPT_SoVITS/s1_train.py --config_file TEMP/tmp_s1.yaml
say "GPT 训练结束"
ls -la "GPT_weights_$VER/" 2>/dev/null

say "ALLDONE"
