# -*- coding: utf-8 -*-
"""gsv5_ft_infer.py —— GPT-SoVITS v5turbo 微调后推理（克隆验证）。

与 gsv5_run.py 的唯一差别：vits / t2s 权重可指定（默认走官方零样本）。
  - --vits 指向 SoVITS_weights_v5turbo/mcconaughey_v5full_df3hp_e8_s928_l32.pth
  - --t2s  指向 GPT_weights_v5turbo/mcconaughey_v5full_df3hp-e15.ckpt
推理端 init_vits_weights() 会自动：读文件头 b"08" -> 判定 if_lora_v3=True
-> 加载官方底模 s2Gv5turbo.pth -> 挂同参 LoraConfig -> 载入 LoRA -> merge_and_unload()

用法：
  # 零样本基线
  python gsv5_ft_infer.py --tag base --out E:/tts-models/acpp/out/v5ft
  # 微调版
  python gsv5_ft_infer.py --tag ft \
      --vits SoVITS_weights_v5turbo/mcconaughey_v5full_df3hp_e8_s928_l32.pth \
      --t2s  GPT_weights_v5turbo/mcconaughey_v5full_df3hp-e15.ckpt \
      --out E:/tts-models/acpp/out/v5ft
"""
import os, sys, time, argparse
import numpy as np, soundfile as sf

REPO = r'G:/_setup/gsv5probe'
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'GPT_SoVITS'))
os.chdir(REPO)

os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

PM = 'GPT_SoVITS/pretrained_models'
_C = {
    'device': 'cpu',
    'is_half': False,
    'version': 'v5turbo',
    'bert_base_path': PM + '/chinese-roberta-wwm-ext-large',
    'cnhuhbert_base_path': PM + '/chinese-hubert-base',
    't2s_weights_path': PM + '/s1v3.ckpt',
    'vits_weights_path': PM + '/gsv-v5-pretrained/s2Gv5turbo.pth',
}
CFG = {'custom': _C}

# 默认素材（与零样本完全一致，保证同文同参考对比）
DEF_REF = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
DEF_REF_TEXT = 'called Sirius, is reaching Earth after traveling at 186,000 miles per second.'
DEF_TEXT = r'G:/_setup/scene_calmdeep.txt'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=r'E:/tts-models/acpp/out/v5ft')
    ap.add_argument('--text-file', default=DEF_TEXT)
    ap.add_argument('--ref', default=DEF_REF)
    ap.add_argument('--ref-text', default=DEF_REF_TEXT)
    ap.add_argument('--vits', default='', help='微调 SoVITS LoRA 权重（空=零样本）')
    ap.add_argument('--t2s', default='', help='微调 GPT 权重（空=官方 s1v3）')
    ap.add_argument('--speeds', default='1.0,0.88')
    ap.add_argument('--tag', default='ft')
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    text = open(a.text_file, encoding='utf-8').read().strip()
    print('[text] %d 词: %s' % (len(text.split()), text[:90] + '...'))
    print('[ref ] %s  (%.2fs)' % (os.path.basename(a.ref), sf.info(a.ref).duration))

    vits = a.vits or _C['vits_weights_path']
    t2s = a.t2s or _C['t2s_weights_path']
    print('[vits] %s' % vits)
    print('[t2s ] %s' % t2s)

    t0 = time.time()
    tts = TTS(TTS_Config(CFG))
    print('[load] TTS 初始化 %.1fs' % (time.time() - t0))

    t0 = time.time()
    tts.init_vits_weights(vits)
    tts.init_t2s_weights(t2s)
    print('[load] 权重加载 %.1fs' % (time.time() - t0))

    for spd in [float(x) for x in a.speeds.split(',')]:
        tag = '%s_%s' % (a.tag, ('%g' % spd).replace('.', 'p'))
        print('--- %s  speed_factor=%s ---' % (tag, spd))
        t0 = time.time()
        try:
            sr, audio = None, None
            for _out in tts.run({
                'text': text,
                'text_lang': 'en',
                'ref_audio_path': a.ref,
                'prompt_text': a.ref_text,
                'prompt_lang': 'en',
                'top_k': 15, 'top_p': 1, 'temperature': 1,
                'text_split_method': 'cut0',
                'batch_size': 1,
                'speed_factor': spd,
                'seed': 42,
                'parallel_infer': True,
                'repetition_penalty': 1.35,
                'use_cuda_graph': False,
                'use_flash_attention': False,
            }):
                if _out is not None:
                    sr, audio = _out
            if audio is None:
                raise RuntimeError('run() 未产出音频')
        except Exception as e:
            import traceback
            traceback.print_exc()
            print('[FAIL] %s: %s' % (tag, e))
            continue
        el = time.time() - t0
        p = os.path.join(a.out, tag + '.wav')
        sf.write(p, audio, sr)
        print('[ok] %s  sr=%d  dur=%.2fs  推理 %.1fs  -> %s'
              % (tag, sr, len(audio) / sr, el, p))

    print('[done]')


if __name__ == '__main__':
    main()
