#!/usr/bin/env bash
# v5full_train.sh —— 用 GSV v5turbo 在 Calm《Wonder》全量 26.92min 上做 LoRA 微调
#
# 流程：切片 → ASR → 1-get-text / 2-get-hubert → 3-get-semantic → s2_train_v3_lora → s1_train
# 切片参数：thr=-40 min_len=2000 min_interval=300 hop=10 max_sil_kept=3000
#           （max_sil_kept 由旧的 500 提到 3000 ⇒ 覆盖率 73% → 99%，真人句间停顿被保留）
set -u

REPO=/g/_setup/gsv5probe
PY="G:/Python310/python.exe"
SRC="G:/GPT-SoVITS/_dataset/wonder_train.wav"
DSROOT="G:/GPT-SoVITS/_dataset_v5full"
SLICED="$DSROOT/sliced"
LIST="$DSROOT/wonder_v5full.list"
EXP="mcconaughey_v5full"
VER="v5turbo"
LOG=/g/_setup/v5full_train.log

export PATH="/e/tool/oopz:$PATH"
export NLTK_DATA=G:/nltk_data
export HF_HOME="C:/Users/86178/.cache/huggingface"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export version="$VER"
export PYTHONUNBUFFERED=1

cd "$REPO" || exit 1
mkdir -p TEMP logs "$DSROOT" SoVITS_weights_v5turbo GPT_weights_v5turbo

ts() { date +"%H:%M:%S"; }
say() { echo "[$(ts)] $*"; }

say "=========== 0. 切片（max_sil_kept=3000，保留真人停顿）==========="
rm -rf "$SLICED"; mkdir -p "$SLICED"
"$PY" -s tools/slice_audio.py "$SRC" "$SLICED" -40 2000 300 10 3000 0.9 0.25 0 1
say "切片完成: $(ls "$SLICED" | wc -l) 段"

say "=========== 1. ASR（faster_whisper small.en）==========="
SLICED="$SLICED" OUTLIST="$LIST" "$PY" G:/_setup/v5full_asr.py
say "ASR 完成: $(wc -l < "$LIST") 条"

OPT="logs/$EXP"
mkdir -p "$OPT"

say "=========== 2. 1-get-text ==========="
inp_text="$LIST" inp_wav_dir="$SLICED" exp_name="$EXP" opt_dir="$OPT" \
bert_pretrained_dir="GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large" \
is_half="False" i_part="0" all_parts="1" _CUDA_VISIBLE_DEVICES="0" \
"$PY" -s GPT_SoVITS/prepare_datasets/1-get-text.py
mv -f "$OPT/2-name2text-0.txt" "$OPT/2-name2text.txt" 2>/dev/null
say "2-name2text.txt: $(wc -l < "$OPT/2-name2text.txt" 2>/dev/null) 行"

say "=========== 3. 2-get-hubert-wav32k ==========="
inp_text="$LIST" inp_wav_dir="$SLICED" exp_name="$EXP" opt_dir="$OPT" \
cnhubert_base_dir="GPT_SoVITS/pretrained_models/chinese-hubert-base" sv_path="" \
is_half="False" i_part="0" all_parts="1" _CUDA_VISIBLE_DEVICES="0" \
"$PY" -s GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py
say "4-cnhubert: $(ls "$OPT/4-cnhubert" 2>/dev/null | wc -l) 个"

say "=========== 4. 3-get-semantic（用 v5turbo 预训练 SoVITS 提语义）==========="
inp_text="$LIST" exp_name="$EXP" opt_dir="$OPT" \
pretrained_s2G="GPT_SoVITS/pretrained_models/gsv-v5-pretrained/s2Gv5turbo.pth" \
s2config_path="GPT_SoVITS/configs/s2.json" \
is_half="False" i_part="0" all_parts="1" _CUDA_VISIBLE_DEVICES="0" \
"$PY" -s GPT_SoVITS/prepare_datasets/3-get-semantic.py
if [ -f "$OPT/6-name2semantic-0.tsv" ]; then
  cp -f "$OPT/6-name2semantic-0.tsv" "$OPT/6-name2semantic.tsv"
fi
say "6-name2semantic.tsv: $(wc -l < "$OPT/6-name2semantic.tsv" 2>/dev/null) 行"

say "=========== 5. 构建 s2 训练配置 ==========="
"$PY" - <<'PYEOF'
import json, os
VER = os.environ['version']; EXP = os.environ['EXP']
d = json.load(open('GPT_SoVITS/configs/s2.json', encoding='utf-8'))
t = d['train']
t['fp16_run'] = False          # CPU，无 fp16
t['batch_size'] = 4            # webui 在非 half 下会 //2 ⇒ 实际 2
t['epochs'] = 8
t['text_low_lr_rate'] = 0.4
t['log_interval'] = 10         # 加密日志，便于尽早看清步耗时
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
print('  写出 TEMP/tmp_s2.json  batch_size=%s epochs=%s lora_rank=%s ver=%s'
      % (t['batch_size'], t['epochs'], t['lora_rank'], VER))
PYEOF

say "=========== 6. 训练 SoVITS（v5turbo LoRA r32, 8 epoch）==========="
say "    目标模块 = net_g.cfm (22 层 DiT)，其余全部冻结"
"$PY" -s GPT_SoVITS/s2_train_v3_lora.py --config TEMP/tmp_s2.json
say "SoVITS 训练结束"
ls -la "SoVITS_weights_$VER/" 2>/dev/null

say "=========== 7. 构建 s1 训练配置 ==========="
"$PY" - <<'PYEOF'
import yaml, os
VER = os.environ['version']; EXP = os.environ['EXP']
d = yaml.load(open('GPT_SoVITS/configs/s1longer-v2.yaml', encoding='utf-8'), Loader=yaml.FullLoader)
d['train']['precision'] = '32'
d['train']['batch_size'] = 8      # webui 非 half 下 //2 ⇒ 4
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

say "=========== 8. 训练 GPT（t2s, 15 epoch）==========="
_CUDA_VISIBLE_DEVICES=0 hz=25hz "$PY" -s GPT_SoVITS/s1_train.py --config_file TEMP/tmp_s1.yaml
say "GPT 训练结束"
ls -la "GPT_weights_$VER/" 2>/dev/null

say "ALLDONE"
