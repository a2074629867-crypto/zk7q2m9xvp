# -*- coding: utf-8 -*-
"""GPT-SoVITS 两阶段训练驱动（CPU 模式，绕开 WebUI）

流程：
  1-get-text.py      -> 2-name2text.txt（文本→音素，英文不需要 BERT 特征）
  2-get-hubert-wav32k.py -> 4-cnhubert/ 5-wav32k/
  3-get-semantic.py  -> 6-name2semantic.tsv
  s2_train.py        -> SoVITS（声学模型）
  s1_train.py        -> GPT（语义→声学）

CPU 关键改动：
  s2: fp16_run=False, batch_size 小
  s1: precision="32", batch_size 小
"""
import os, sys, json, subprocess, time

REPO = r'G:/GPT-SoVITS'
PY = r'G:/Python310/python.exe'
EXP = 'mcconaughey_calm'
VERSION = 'v2'

LIST = REPO + '/_dataset/wonder.list'
SLICED = REPO + '/_dataset/sliced'
EXP_DIR = REPO + '/logs/' + EXP
LOG_DIR = r'G:/_setup'

BERT = 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'
HUBERT = 'GPT_SoVITS/pretrained_models/chinese-hubert-base'
S2G = 'GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth'
S2D = 'GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2D2333k.pth'
S1 = 'GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt'

S2_EPOCHS = int(os.environ.get('S2_EPOCHS', '8'))
S1_EPOCHS = int(os.environ.get('S1_EPOCHS', '15'))
BATCH_S2 = int(os.environ.get('BATCH_S2', '2'))
BATCH_S1 = int(os.environ.get('BATCH_S1', '2'))
SAVE_EVERY = int(os.environ.get('SAVE_EVERY', '4'))
NTHREAD = os.environ.get('NTHREAD', '10')

STEPS = sys.argv[1:] or ['prep', 's2', 's1']


def base_env():
    e = os.environ.copy()
    e.update({
        'inp_text': LIST,
        'inp_wav_dir': SLICED,
        'exp_name': EXP,
        'opt_dir': EXP_DIR,
        'bert_pretrained_dir': BERT,
        'cnhubert_base_dir': HUBERT,
        'pretrained_s2G': S2G,
        's2config_path': 'GPT_SoVITS/configs/s2.json',
        'i_part': '0',
        'all_parts': '1',
        'is_half': 'False',
        '_CUDA_VISIBLE_DEVICES': '0',
        'PYTHONPATH': REPO + '/GPT_SoVITS',
        'NLTK_DATA': 'G:/nltk_data',
        'HF_HOME': 'G:/hf_cache',
        'HF_ENDPOINT': 'https://hf-mirror.com',
        'PATH': 'E:/tool/oopz;' + os.environ.get('PATH', ''),
        'OMP_NUM_THREADS': NTHREAD,
        'MKL_NUM_THREADS': NTHREAD,
        'hz': '25hz',
        'version': VERSION,
    })
    e.pop('https_proxy', None)
    e.pop('http_proxy', None)
    return e


def run(tag, args, env=None, cwd=REPO):
    logp = os.path.join(LOG_DIR, 'train_%s.log' % tag)
    print('\n===== [%s] %s' % (tag, ' '.join(args)))
    print('      日志 -> %s' % logp)
    t0 = time.time()
    with open(logp, 'w', encoding='utf-8', errors='ignore') as f:
        p = subprocess.run(args, cwd=cwd, env=env or base_env(),
                           stdout=f, stderr=subprocess.STDOUT)
    el = time.time() - t0
    print('      退出码 %d，用时 %.0f 秒 (%.1f 分)' % (p.returncode, el, el / 60))
    if p.returncode != 0:
        print('      !! 失败，日志尾部：')
        try:
            with open(logp, encoding='utf-8', errors='ignore') as f:
                for ln in f.read().strip().split('\n')[-12:]:
                    print('        ' + ln)
        except Exception:
            pass
    return p.returncode


def merge_semantic():
    """★ 3-get-semantic.py 只写 6-name2semantic-<part>.tsv，
    WebUI 会带表头合并成 6-name2semantic.tsv（webui.py:1056），s1 读的是合并后的那个。
    漏了会在 s1 启动 60 秒时抛 FileNotFoundError（踩过）。"""
    merged = os.path.join(EXP_DIR, '6-name2semantic.tsv')
    parts = sorted(fn for fn in os.listdir(EXP_DIR)
                   if fn.startswith('6-name2semantic-') and fn.endswith('.tsv'))
    if not parts:
        print('!! 找不到 6-name2semantic-*.tsv，无法合并')
        return False
    rows = ['item_name\tsemantic_audio']
    for fn in parts:
        with open(os.path.join(EXP_DIR, fn), encoding='utf-8') as f:
            rows += f.read().strip('\n').split('\n')
    with open(merged, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows) + '\n')
    print('合并 -> %s (%d 行)' % (merged, len(rows) - 1))
    return True


def main():
    os.makedirs(EXP_DIR, exist_ok=True)
    for d in ('SoVITS_weights_v2', 'GPT_weights_v2'):
        os.makedirs(os.path.join(REPO, d), exist_ok=True)

    # ★★ 必须预先建好 —— WebUI 里是先 makedirs 再训练的（webui.py:610 / :696），
    #    我上一版漏了，导致 s2 训到第 4 epoch 存盘时 shutil.move 目标目录不存在：
    #    FileNotFoundError: .../logs_s2_v2/G_233333333333.pth  （白跑 52 分钟）
    for v in ('v1', 'v2', 'v3'):
        os.makedirs(os.path.join(EXP_DIR, 'logs_s2_%s' % v), exist_ok=True)
        os.makedirs(os.path.join(EXP_DIR, 'logs_s1_%s' % v), exist_ok=True)
    os.makedirs(os.path.join(EXP_DIR, 'logs_s1'), exist_ok=True)

    # ---------- 预处理 ----------
    if 'prep' in STEPS:
        if run('1gettext', [PY, '-u', 'GPT_SoVITS/prepare_datasets/1-get-text.py']) != 0:
            print('预处理 1-get-text 失败，中止')
            return 1
        # ★ 1-get-text 只写 2-name2text-<part>.txt，WebUI 会合并成 2-name2text.txt
        merged = os.path.join(EXP_DIR, '2-name2text.txt')
        allrows = []
        for fn in sorted(os.listdir(EXP_DIR)):
            if fn.startswith('2-name2text-') and fn.endswith('.txt'):
                with open(os.path.join(EXP_DIR, fn), encoding='utf-8') as f:
                    allrows += f.read().strip('\n').split('\n')
        with open(merged, 'w', encoding='utf-8') as f:
            f.write('\n'.join(allrows) + '\n')
        print('合并 -> %s (%d 行)' % (merged, len(allrows)))

        for tag, script in (('2hubert', 'GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py'),
                            ('3semantic', 'GPT_SoVITS/prepare_datasets/3-get-semantic.py')):
            if run(tag, [PY, '-u', script]) != 0:
                print('预处理 %s 失败，中止' % tag)
                return 1
        merge_semantic()

    # ---------- SoVITS (s2) ----------
    if 's2' in STEPS:
        with open(REPO + '/GPT_SoVITS/configs/s2.json', encoding='utf-8') as f:
            d = json.load(f)
        d['train'].update({
            'fp16_run': False,
            'batch_size': BATCH_S2,
            'epochs': S2_EPOCHS,
            'text_low_lr_rate': 0.4,
            'pretrained_s2G': S2G,
            'pretrained_s2D': S2D,
            'if_save_latest': True,
            'if_save_every_weights': True,
            'save_every_epoch': SAVE_EVERY,
            'gpu_numbers': '0',
            'grad_ckpt': False,
            'lora_rank': 32,
        })
        d['model']['version'] = VERSION
        d['data']['exp_dir'] = EXP_DIR
        d['s2_ckpt_dir'] = EXP_DIR
        d['save_weight_dir'] = 'SoVITS_weights_v2'
        d['name'] = EXP
        d['version'] = VERSION
        tmp = os.path.join(LOG_DIR, 'tmp_s2.json')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
        print('s2 配置: batch=%d epochs=%d fp16=%s' % (BATCH_S2, S2_EPOCHS, False))
        if run('s2', [PY, '-u', 'GPT_SoVITS/s2_train.py', '--config', tmp]) != 0:
            print('s2 训练失败')
            return 1

    # ---------- GPT (s1) ----------
    if 's1' in STEPS:
        import yaml
        merge_semantic()   # ★ 单独跑 s1 时的兜底（跳过 prep 时也得有合并文件）
        with open(REPO + '/GPT_SoVITS/configs/s1longer-v2.yaml', encoding='utf-8') as f:
            d = yaml.safe_load(f)
        d['train'].update({
            'precision': '32',
            'batch_size': BATCH_S1,
            'epochs': S1_EPOCHS,
            'save_every_n_epoch': SAVE_EVERY,
            'if_save_every_weights': True,
            'if_save_latest': True,
            'if_dpo': False,
            'half_weights_save_dir': 'GPT_weights_v2',
            'exp_name': EXP,
        })
        d['pretrained_s1'] = S1
        d['train_semantic_path'] = EXP_DIR + '/6-name2semantic.tsv'
        d['train_phoneme_path'] = EXP_DIR + '/2-name2text.txt'
        d['output_dir'] = EXP_DIR + '/logs_s1_v2'
        tmp = os.path.join(LOG_DIR, 'tmp_s1.yaml')
        with open(tmp, 'w', encoding='utf-8') as f:
            yaml.dump(d, f, default_flow_style=False, allow_unicode=True)
        print('s1 配置: batch=%d epochs=%d precision=32' % (BATCH_S1, S1_EPOCHS))
        if run('s1', [PY, '-u', 'GPT_SoVITS/s1_train.py', '--config_file', tmp]) != 0:
            print('s1 训练失败')
            return 1

    print('\n全部完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
